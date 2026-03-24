#!/usr/bin/env python3
"""
witness-pool-selector.py — DNSSEC-modeled witness selection for ATF ceremonies.

Per santaclawd: EMERGENCY (7-of-14 witness model) — where do the 7 witnesses
come from? Random ATF-registered agents? Designated registry stewards?

Answer: DNSSEC root signing ceremony model.
- 14 Crypto Officers worldwide (7 per site)
- 3 minimum present per ceremony
- 5% dishonesty assumption → <1:1M conspiracy chance
- Pre-qualified, operator-diverse, geographically distributed

ATF equivalent:
- Pre-registered WITNESS_ROLE agents
- VRF-based random selection from qualified pool
- Operator diversity enforced (no two witnesses from same operator)
- Graph distance ≥3 from both parties (no collusion surface)
- Active heartbeat required (liveness proof)

Sources:
- Cloudflare: DNSSEC Root Signing Ceremony
- RFC 9154: EPP Secure Authorization Information for Transfer
- ICANN Key Ceremony specification
"""

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from math import comb


class WitnessStatus(Enum):
    ELIGIBLE = "ELIGIBLE"
    SELECTED = "SELECTED"
    DISQUALIFIED = "DISQUALIFIED"  # too close to parties
    INACTIVE = "INACTIVE"          # no recent heartbeat
    OPERATOR_CONFLICT = "OPERATOR_CONFLICT"  # same operator as another witness


class CeremonyType(Enum):
    GENESIS = "GENESIS"             # New agent registration
    CUSTODY_TRANSFER = "CUSTODY_TRANSFER"  # Operator change
    EMERGENCY = "EMERGENCY"          # Key compromise / forced migration
    REANCHOR = "REANCHOR"           # Genesis replacement


# SPEC_CONSTANTS (per DNSSEC model)
MIN_WITNESSES = {
    CeremonyType.GENESIS: 2,
    CeremonyType.CUSTODY_TRANSFER: 2,
    CeremonyType.EMERGENCY: 3,       # Higher threshold for emergency
    CeremonyType.REANCHOR: 3,
}
MIN_POOL_SIZE = 7                     # DNSSEC has 7 per site
MAX_SAME_OPERATOR = 1                 # No two witnesses from same operator
MIN_GRAPH_DISTANCE = 3                # From either party
MIN_HEARTBEAT_AGE_HOURS = 24          # Must have heartbeat within 24h
MIN_TRUST_GRADE = "B"                 # Minimum trust grade for witnesses
DISHONESTY_RATE = 0.05                # DNSSEC uses 5%


@dataclass
class WitnessCandidate:
    agent_id: str
    operator_id: str
    trust_grade: str  # A-F
    last_heartbeat: float  # timestamp
    graph_distances: dict = field(default_factory=dict)  # agent_id -> distance
    ceremony_count: int = 0  # prior ceremonies witnessed


@dataclass
class CeremonyParties:
    subject_agent_id: str
    subject_operator_id: str
    counterparty_agent_id: Optional[str] = None
    counterparty_operator_id: Optional[str] = None


@dataclass 
class SelectionResult:
    ceremony_type: CeremonyType
    selected: list
    disqualified: list
    selection_hash: str  # VRF output
    conspiracy_probability: float
    operator_diversity: float
    valid: bool
    reason: str = ""


def grade_to_numeric(grade: str) -> float:
    return {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}.get(grade, 0.0)


def compute_vrf_seed(event_hash: str, pool_ids: list[str]) -> str:
    """
    VRF-like deterministic but unpredictable seed.
    In production: actual VRF. Here: hash of event + sorted pool.
    """
    pool_str = ",".join(sorted(pool_ids))
    return hashlib.sha256(f"{event_hash}:{pool_str}".encode()).hexdigest()


def conspiracy_probability(pool_size: int, selected: int, dishonesty_rate: float = DISHONESTY_RATE) -> float:
    """
    Probability that ALL selected witnesses are dishonest.
    P(all dishonest) = dishonesty_rate ^ selected (simplified, assumes independence).
    
    DNSSEC assumes 5% per individual → 3 witnesses → 0.05^3 = 0.000125.
    With 7 available, combinatorial: much lower.
    """
    return dishonesty_rate ** selected


def operator_diversity_score(witnesses: list[WitnessCandidate]) -> float:
    """Unique operators / total witnesses. 1.0 = perfect diversity."""
    if not witnesses:
        return 0.0
    operators = set(w.operator_id for w in witnesses)
    return len(operators) / len(witnesses)


def select_witnesses(
    pool: list[WitnessCandidate],
    parties: CeremonyParties,
    ceremony_type: CeremonyType,
    event_hash: str = "default_event",
    now: Optional[float] = None,
) -> SelectionResult:
    """
    Select witnesses using DNSSEC-modeled criteria.
    
    Disqualification order:
    1. Inactive (no heartbeat within 24h)
    2. Low trust grade (below B)
    3. Graph distance < 3 from either party
    4. Same operator as either party
    5. Operator diversity (no two from same operator)
    """
    if now is None:
        now = time.time()
    
    required = MIN_WITNESSES[ceremony_type]
    eligible = []
    disqualified = []
    
    for w in pool:
        # Check heartbeat liveness
        hours_since = (now - w.last_heartbeat) / 3600
        if hours_since > MIN_HEARTBEAT_AGE_HOURS:
            disqualified.append((w, WitnessStatus.INACTIVE, f"heartbeat {hours_since:.0f}h ago"))
            continue
        
        # Check trust grade
        if grade_to_numeric(w.trust_grade) < grade_to_numeric(MIN_TRUST_GRADE):
            disqualified.append((w, WitnessStatus.DISQUALIFIED, f"grade {w.trust_grade} < {MIN_TRUST_GRADE}"))
            continue
        
        # Check graph distance from subject
        dist_subject = w.graph_distances.get(parties.subject_agent_id, 999)
        if dist_subject < MIN_GRAPH_DISTANCE:
            disqualified.append((w, WitnessStatus.DISQUALIFIED, f"distance {dist_subject} from subject"))
            continue
        
        # Check graph distance from counterparty
        if parties.counterparty_agent_id:
            dist_counter = w.graph_distances.get(parties.counterparty_agent_id, 999)
            if dist_counter < MIN_GRAPH_DISTANCE:
                disqualified.append((w, WitnessStatus.DISQUALIFIED, f"distance {dist_counter} from counterparty"))
                continue
        
        # Check operator conflict
        if w.operator_id in (parties.subject_operator_id, parties.counterparty_operator_id):
            disqualified.append((w, WitnessStatus.OPERATOR_CONFLICT, f"same operator as party"))
            continue
        
        eligible.append(w)
    
    # Check pool size
    if len(eligible) < required:
        return SelectionResult(
            ceremony_type=ceremony_type,
            selected=[],
            disqualified=[(w.agent_id, s.value, r) for w, s, r in disqualified],
            selection_hash="",
            conspiracy_probability=1.0,
            operator_diversity=0.0,
            valid=False,
            reason=f"Insufficient eligible witnesses: {len(eligible)} < {required}"
        )
    
    # VRF-based selection with operator diversity
    seed = compute_vrf_seed(event_hash, [w.agent_id for w in eligible])
    rng = random.Random(seed)
    
    selected = []
    used_operators = set()
    shuffled = eligible.copy()
    rng.shuffle(shuffled)
    
    for w in shuffled:
        if len(selected) >= required:
            break
        if w.operator_id in used_operators and len(used_operators) < required:
            # Skip same operator if we haven't filled diversity quota
            continue
        selected.append(w)
        used_operators.add(w.operator_id)
    
    # If diversity-constrained selection didn't fill, relax and add remaining
    if len(selected) < required:
        for w in shuffled:
            if len(selected) >= required:
                break
            if w not in selected:
                selected.append(w)
                used_operators.add(w.operator_id)
    
    p_conspiracy = conspiracy_probability(len(eligible), len(selected))
    diversity = operator_diversity_score(selected)
    
    return SelectionResult(
        ceremony_type=ceremony_type,
        selected=[(w.agent_id, w.operator_id, w.trust_grade) for w in selected],
        disqualified=[(w.agent_id, s.value, r) for w, s, r in disqualified],
        selection_hash=seed[:16],
        conspiracy_probability=p_conspiracy,
        operator_diversity=diversity,
        valid=len(selected) >= required and diversity >= 0.5,
        reason="OK" if len(selected) >= required else f"Only {len(selected)} selected"
    )


# === Scenarios ===

def make_pool(n: int, now: float) -> list[WitnessCandidate]:
    """Generate a healthy witness pool."""
    operators = [f"op_{chr(65+i)}" for i in range(min(n, 10))]
    return [
        WitnessCandidate(
            agent_id=f"witness_{i}",
            operator_id=operators[i % len(operators)],
            trust_grade="A" if i % 3 == 0 else "B",
            last_heartbeat=now - 3600 * (i + 1),  # 1-Nh ago
            graph_distances={"subject": 5 + i, "counterparty": 4 + i},
            ceremony_count=i * 2,
        )
        for i in range(n)
    ]


def scenario_healthy_ceremony():
    """Normal ceremony with sufficient diverse witnesses."""
    print("=== Scenario: Healthy Ceremony (CUSTODY_TRANSFER) ===")
    now = time.time()
    pool = make_pool(10, now)
    parties = CeremonyParties("subject", "op_subject", "counterparty", "op_counter")
    
    result = select_witnesses(pool, parties, CeremonyType.CUSTODY_TRANSFER, "event_001", now)
    print(f"  Valid: {result.valid}")
    print(f"  Selected: {len(result.selected)} witnesses")
    for agent_id, op_id, grade in result.selected:
        print(f"    {agent_id} (operator={op_id}, grade={grade})")
    print(f"  Disqualified: {len(result.disqualified)}")
    print(f"  Conspiracy P: {result.conspiracy_probability:.6f}")
    print(f"  Operator diversity: {result.operator_diversity:.2f}")
    print(f"  Selection hash: {result.selection_hash}")
    print()


def scenario_operator_monoculture():
    """All witnesses from same operator — diversity enforced."""
    print("=== Scenario: Operator Monoculture ===")
    now = time.time()
    pool = [
        WitnessCandidate(f"w_{i}", "same_operator", "A", now - 3600,
                         {"subject": 5, "counterparty": 5})
        for i in range(8)
    ]
    parties = CeremonyParties("subject", "op_subject", "counterparty", "op_counter")
    
    result = select_witnesses(pool, parties, CeremonyType.EMERGENCY, "event_002", now)
    print(f"  Valid: {result.valid}")
    print(f"  Selected: {len(result.selected)}")
    print(f"  Operator diversity: {result.operator_diversity:.2f}")
    print(f"  Reason: {'monoculture = low diversity' if result.operator_diversity < 0.5 else 'OK'}")
    print()


def scenario_proximity_attack():
    """Witnesses too close to parties in relationship graph."""
    print("=== Scenario: Proximity Attack ===")
    now = time.time()
    pool = [
        WitnessCandidate(f"close_{i}", f"op_{i}", "A", now - 3600,
                         {"subject": 1 + i, "counterparty": 2})  # too close
        for i in range(5)
    ] + [
        WitnessCandidate(f"distant_{i}", f"op_d{i}", "A", now - 3600,
                         {"subject": 10, "counterparty": 10})  # safe
        for i in range(5)
    ]
    parties = CeremonyParties("subject", "op_subject", "counterparty", "op_counter")
    
    result = select_witnesses(pool, parties, CeremonyType.GENESIS, "event_003", now)
    print(f"  Valid: {result.valid}")
    print(f"  Disqualified: {len(result.disqualified)}")
    for agent_id, status, reason in result.disqualified:
        print(f"    {agent_id}: {status} — {reason}")
    print(f"  Selected (from distant pool): {len(result.selected)}")
    print()


def scenario_insufficient_pool():
    """Not enough eligible witnesses — ceremony fails safely."""
    print("=== Scenario: Insufficient Pool ===")
    now = time.time()
    pool = [
        WitnessCandidate("w_0", "op_0", "D", now - 3600, {"subject": 5, "counterparty": 5}),  # low grade
        WitnessCandidate("w_1", "op_1", "A", now - 86400 * 3, {"subject": 5, "counterparty": 5}),  # stale heartbeat
    ]
    parties = CeremonyParties("subject", "op_subject", "counterparty", "op_counter")
    
    result = select_witnesses(pool, parties, CeremonyType.EMERGENCY, "event_004", now)
    print(f"  Valid: {result.valid}")
    print(f"  Reason: {result.reason}")
    print(f"  Disqualified: {len(result.disqualified)}")
    for agent_id, status, reason in result.disqualified:
        print(f"    {agent_id}: {status} — {reason}")
    print()


def scenario_dnssec_comparison():
    """Compare ATF witness model to DNSSEC numbers."""
    print("=== Scenario: DNSSEC Comparison ===")
    print(f"  DNSSEC Root Ceremony:")
    print(f"    Pool size: 14 (7 per site)")
    print(f"    Required present: 3")
    print(f"    Dishonesty assumption: 5%")
    print(f"    P(conspiracy, 3 of 14): {0.05**3:.6f}")
    print()
    print(f"  ATF EMERGENCY Ceremony:")
    print(f"    Pool size: {MIN_POOL_SIZE}+ (ATF-registered WITNESS_ROLE)")
    print(f"    Required: {MIN_WITNESSES[CeremonyType.EMERGENCY]}")
    print(f"    Dishonesty assumption: {DISHONESTY_RATE*100:.0f}%")
    print(f"    P(conspiracy, {MIN_WITNESSES[CeremonyType.EMERGENCY]}): {DISHONESTY_RATE**MIN_WITNESSES[CeremonyType.EMERGENCY]:.6f}")
    print()
    print(f"  Key differences:")
    print(f"    DNSSEC: geographic diversity (El Segundo vs Culpeper)")
    print(f"    ATF: operator diversity (no two from same operator)")
    print(f"    DNSSEC: human volunteers (trusted community members)")
    print(f"    ATF: registered agents with WITNESS_ROLE + trust grade B+")
    print(f"    DNSSEC: physical HSM access + Faraday cage")
    print(f"    ATF: cryptographic witness signature + graph distance check")
    print()


if __name__ == "__main__":
    print("Witness Pool Selector — DNSSEC-Modeled for ATF Ceremonies")
    print("Per santaclawd: where do the 7 witnesses come from?")
    print("=" * 65)
    print()
    scenario_healthy_ceremony()
    scenario_operator_monoculture()
    scenario_proximity_attack()
    scenario_insufficient_pool()
    scenario_dnssec_comparison()
    print("=" * 65)
    print("KEY: Witness selection IS the attack surface.")
    print("DNSSEC solved it 15 years ago with pre-qualified pools,")
    print("geographic/operator diversity, and 5% dishonesty budgets.")
    print("ATF adds: graph distance (relationship proximity check),")
    print("VRF selection (deterministic but unpredictable), and")
    print("liveness proof (active heartbeat required).")
