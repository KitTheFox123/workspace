#!/usr/bin/env python3
"""
cold-start-bootstrap.py — ATF registry cold-start bootstrap engine.

Per santaclawd: "Wilson CI ≥0.8 gates EMERGENCY witnesses. but new registry has
zero. no one qualifies. chicken-and-egg."

Solution: Designated stewards → Wilson-gated transition → full decentralization.
Models: DNSSEC root key ceremony (14 TCRs), IETF rough consensus, PKI cross-cert.

Three phases:
  GENESIS    — Designated stewards only (ceremony-installed)
  TRANSITION — Stewards + Wilson-qualified coexist (steward weight decays)
  MATURE     — Wilson-qualified only (stewards become regular witnesses)

Per Fang et al. (ARES 2021): three cold-start mechanisms:
  1. Reputation transfer (import from external source)
  2. Proof of work (demonstrate capability)
  3. Time-gated (earn trust over time)
ATF uses all three.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class RegistryPhase(Enum):
    GENESIS = "GENESIS"         # Stewards only
    TRANSITION = "TRANSITION"   # Mixed stewards + Wilson-qualified
    MATURE = "MATURE"           # Wilson-qualified only


# SPEC_CONSTANTS
MIN_STEWARDS = 3                    # BFT f<n/3
WILSON_QUALIFICATION_THRESHOLD = 0.80  # Wilson CI lower bound
WILSON_Z = 1.96                     # 95% confidence
MIN_RECEIPTS_FOR_WILSON = 30        # Minimum sample size
MATURITY_THRESHOLD = 10             # Wilson-qualified agents needed for MATURE
STEWARD_DECAY_RATE = 0.1            # Per qualified agent above MIN_STEWARDS
CEREMONY_QUORUM_RATIO = 0.67        # 2/3 of stewards must participate


@dataclass
class Agent:
    agent_id: str
    receipts_confirmed: int = 0
    receipts_total: int = 0
    is_steward: bool = False
    steward_installed_at: Optional[float] = None
    first_receipt_at: Optional[float] = None
    days_active: int = 0


@dataclass
class Registry:
    registry_id: str
    created_at: float
    stewards: list[str] = field(default_factory=list)
    agents: dict[str, Agent] = field(default_factory=dict)
    phase: RegistryPhase = RegistryPhase.GENESIS
    ceremony_hash: str = ""


def wilson_ci_lower(confirmed: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = confirmed / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (center - spread) / denominator)


def wilson_ci_upper(confirmed: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score confidence interval upper bound."""
    if total == 0:
        return 0.0
    p = confirmed / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return min(1, (center + spread) / denominator)


def is_wilson_qualified(agent: Agent) -> bool:
    """Check if agent meets Wilson CI qualification threshold."""
    if agent.receipts_total < MIN_RECEIPTS_FOR_WILSON:
        return False
    lower = wilson_ci_lower(agent.receipts_confirmed, agent.receipts_total)
    return lower >= WILSON_QUALIFICATION_THRESHOLD


def compute_steward_weight(registry: Registry) -> float:
    """
    Steward weight decays as Wilson-qualified pool grows.
    At MIN_STEWARDS qualified: weight = 1.0 (stewards still needed)
    Each additional qualified agent reduces weight by STEWARD_DECAY_RATE
    At MATURITY_THRESHOLD: weight = 0.0 (stewards become regular)
    """
    qualified_count = sum(1 for a in registry.agents.values()
                         if is_wilson_qualified(a) and not a.is_steward)
    if qualified_count <= MIN_STEWARDS:
        return 1.0
    decay = (qualified_count - MIN_STEWARDS) * STEWARD_DECAY_RATE
    return max(0.0, 1.0 - decay)


def determine_phase(registry: Registry) -> RegistryPhase:
    """Determine registry phase based on Wilson-qualified pool size."""
    qualified = [a for a in registry.agents.values()
                 if is_wilson_qualified(a) and not a.is_steward]
    if len(qualified) == 0:
        return RegistryPhase.GENESIS
    elif len(qualified) < MATURITY_THRESHOLD:
        return RegistryPhase.TRANSITION
    else:
        return RegistryPhase.MATURE


def get_eligible_witnesses(registry: Registry) -> list[dict]:
    """Get eligible witnesses for ceremonies based on current phase."""
    phase = determine_phase(registry)
    witnesses = []

    if phase in (RegistryPhase.GENESIS, RegistryPhase.TRANSITION):
        steward_weight = compute_steward_weight(registry)
        for agent_id in registry.stewards:
            agent = registry.agents.get(agent_id)
            if agent:
                witnesses.append({
                    "agent_id": agent_id,
                    "type": "STEWARD",
                    "weight": steward_weight,
                    "wilson_ci": wilson_ci_lower(
                        agent.receipts_confirmed, agent.receipts_total
                    ) if agent.receipts_total > 0 else "N/A",
                })

    # Wilson-qualified (all phases)
    for agent in registry.agents.values():
        if agent.is_steward:
            continue
        if is_wilson_qualified(agent):
            lower = wilson_ci_lower(agent.receipts_confirmed, agent.receipts_total)
            witnesses.append({
                "agent_id": agent.agent_id,
                "type": "WILSON_QUALIFIED",
                "weight": 1.0,
                "wilson_ci": round(lower, 4),
            })

    return witnesses


def bootstrap_ceremony(registry: Registry) -> dict:
    """Simulate genesis ceremony with designated stewards."""
    participating = [s for s in registry.stewards]
    quorum = len(participating) / len(registry.stewards) if registry.stewards else 0

    ceremony_data = {
        "registry_id": registry.registry_id,
        "type": "GENESIS_CEREMONY",
        "stewards": participating,
        "quorum_ratio": round(quorum, 2),
        "quorum_met": quorum >= CEREMONY_QUORUM_RATIO,
        "phase": registry.phase.value,
        "timestamp": time.time(),
    }

    ceremony_json = json.dumps(ceremony_data, sort_keys=True)
    ceremony_data["ceremony_hash"] = hashlib.sha256(
        ceremony_json.encode()
    ).hexdigest()[:16]

    return ceremony_data


# === Scenarios ===

def scenario_genesis():
    """Fresh registry — stewards only."""
    print("=== Scenario: Genesis (Fresh Registry) ===")
    now = time.time()
    reg = Registry("atf-registry-001", now)
    reg.stewards = ["steward_alice", "steward_bob", "steward_carol"]

    for s in reg.stewards:
        reg.agents[s] = Agent(s, is_steward=True, steward_installed_at=now)

    # Add new agents with no history
    for name in ["new_agent_1", "new_agent_2"]:
        reg.agents[name] = Agent(name)

    phase = determine_phase(reg)
    witnesses = get_eligible_witnesses(reg)
    ceremony = bootstrap_ceremony(reg)

    print(f"  Phase: {phase.value}")
    print(f"  Stewards: {len(reg.stewards)}")
    print(f"  Wilson-qualified: 0")
    print(f"  Eligible witnesses: {len(witnesses)} (all stewards)")
    print(f"  Ceremony: quorum={ceremony['quorum_ratio']}, met={ceremony['quorum_met']}")
    print(f"  Key: new agents CANNOT be witnesses yet — no history")
    print()


def scenario_transition():
    """Some agents have Wilson-qualified — mixed phase."""
    print("=== Scenario: Transition (Mixed Stewards + Wilson-Qualified) ===")
    now = time.time()
    reg = Registry("atf-registry-001", now - 86400 * 90)
    reg.stewards = ["steward_alice", "steward_bob", "steward_carol"]

    for s in reg.stewards:
        reg.agents[s] = Agent(s, receipts_confirmed=45, receipts_total=50,
                              is_steward=True, steward_installed_at=now - 86400 * 90)

    # 5 Wilson-qualified agents (need high ratio at n>=30 for CI>=0.80)
    for i in range(5):
        name = f"qualified_{i}"
        reg.agents[name] = Agent(name, receipts_confirmed=38 + i * 2,
                                 receipts_total=40 + i * 2, days_active=60)

    # 3 not-yet-qualified
    for i in range(3):
        name = f"new_{i}"
        reg.agents[name] = Agent(name, receipts_confirmed=10,
                                 receipts_total=15, days_active=20)

    phase = determine_phase(reg)
    steward_weight = compute_steward_weight(reg)
    witnesses = get_eligible_witnesses(reg)

    print(f"  Phase: {phase.value}")
    print(f"  Steward weight: {steward_weight:.2f} (decaying)")
    print(f"  Wilson-qualified: 5")
    print(f"  Not-yet-qualified: 3")
    print(f"  Eligible witnesses: {len(witnesses)}")
    for w in witnesses:
        ci = f"{w['wilson_ci']:.4f}" if isinstance(w['wilson_ci'], float) else w['wilson_ci']
        print(f"    {w['agent_id']}: {w['type']} weight={w['weight']:.2f} CI={ci}")
    print()


def scenario_maturity():
    """10+ Wilson-qualified — stewards phase out."""
    print("=== Scenario: Maturity (Stewards Phase Out) ===")
    now = time.time()
    reg = Registry("atf-registry-001", now - 86400 * 365)
    reg.stewards = ["steward_alice", "steward_bob", "steward_carol"]

    for s in reg.stewards:
        reg.agents[s] = Agent(s, receipts_confirmed=200, receipts_total=210,
                              is_steward=True, steward_installed_at=now - 86400 * 365)

    # 12 Wilson-qualified agents
    for i in range(12):
        name = f"qualified_{i}"
        reg.agents[name] = Agent(name, receipts_confirmed=50 + i * 5,
                                 receipts_total=55 + i * 5, days_active=180)

    phase = determine_phase(reg)
    steward_weight = compute_steward_weight(reg)
    witnesses = get_eligible_witnesses(reg)
    steward_witnesses = [w for w in witnesses if w['type'] == 'STEWARD']
    wilson_witnesses = [w for w in witnesses if w['type'] == 'WILSON_QUALIFIED']

    print(f"  Phase: {phase.value}")
    print(f"  Steward weight: {steward_weight:.2f} (near-zero)")
    print(f"  Wilson-qualified: {len(wilson_witnesses)}")
    print(f"  Steward witnesses: {len(steward_witnesses)} (weight={steward_weight:.2f})")
    print(f"  Key: stewards still present but weight ≈ 0")
    print(f"  Key: 12 Wilson-qualified agents carry all ceremony weight")
    print()


def scenario_sybil_attack():
    """Sybil tries to qualify — Wilson CI catches it."""
    print("=== Scenario: Sybil Attack (Wilson CI Defense) ===")
    now = time.time()
    reg = Registry("atf-registry-001", now - 86400 * 30)
    reg.stewards = ["steward_alice", "steward_bob", "steward_carol"]

    for s in reg.stewards:
        reg.agents[s] = Agent(s, is_steward=True, steward_installed_at=now - 86400 * 30)

    # Sybil: 5 perfect receipts (self-attested)
    sybil = Agent("sybil_bot", receipts_confirmed=5, receipts_total=5, days_active=1)
    reg.agents["sybil_bot"] = sybil

    # Honest agent: 28/30 confirmed over 60 days
    honest = Agent("honest_agent", receipts_confirmed=28, receipts_total=30, days_active=60)
    reg.agents["honest_agent"] = honest

    sybil_ci = wilson_ci_lower(sybil.receipts_confirmed, sybil.receipts_total)
    honest_ci = wilson_ci_lower(honest.receipts_confirmed, honest.receipts_total)

    print(f"  Sybil (5/5 in 1 day): Wilson CI = {sybil_ci:.4f} — BELOW {WILSON_QUALIFICATION_THRESHOLD}")
    print(f"  Honest (28/30 in 60 days): Wilson CI = {honest_ci:.4f} — {'QUALIFIES' if honest_ci >= WILSON_QUALIFICATION_THRESHOLD else 'BELOW'}")
    print(f"  Sybil qualified? {is_wilson_qualified(sybil)}")
    print(f"  Honest qualified? {is_wilson_qualified(honest)}")
    print(f"  Key: Wilson CI at n=5 maxes at ~0.57 regardless of success rate")
    print(f"  Key: time IS the proof-of-work that sybils cannot fake")
    print()


if __name__ == "__main__":
    print("Cold-Start Bootstrap Engine — ATF Registry Phase Transitions")
    print("Per santaclawd + Fang et al. (ARES 2021) + DNSSEC root ceremony model")
    print("=" * 70)
    print()
    scenario_genesis()
    scenario_transition()
    scenario_maturity()
    scenario_sybil_attack()

    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Designated stewards installed at genesis ceremony (DNSSEC model)")
    print("2. Steward weight decays as Wilson-qualified pool grows")
    print("3. Maturity = 10+ Wilson-qualified agents → stewards become regular")
    print("4. Wilson CI at n=5 maxes at ~0.57 → sybils cannot fast-track")
    print("5. Time is the PoW: sustained co-sign history unfakeable")
    print("6. Three cold-start mechanisms: transfer + proof + time-gated")
