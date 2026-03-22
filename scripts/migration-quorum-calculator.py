#!/usr/bin/env python3
"""migration-quorum-calculator.py — Key migration quorum requirements.

Per santaclawd email (2026-03-22): migration validity =
dual-sign + min(2, active_counterparties) attestations within window.

Key insight: migration window scales inversely with counterparty count.
Well-connected agents = fast migration (more witnesses).
Isolated agents = slow migration (fewer witnesses, higher risk).
Zero counterparties = MANUAL (human must intervene).

This is Chandra-Toueg (1996) applied to key rotation:
- More observers = better failure detection accuracy
- Single observer = ◇S (eventually strong) at best
- Multiple independent = ◇P (eventually perfect)

References:
- Chandra & Toueg (1996): Failure detector classification
- CT (Certificate Transparency): Multi-party observation
- DKIM key rotation: DNS propagation creates witness window
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CounterpartyInfo:
    """A counterparty who can attest to migration."""
    agent_id: str
    operator: str
    last_interaction_ts: float  # unix timestamp
    is_independent: bool = True  # false if same operator as migrating agent


@dataclass
class MigrationRequest:
    """Key migration request to be validated."""
    agent_id: str
    old_key_signature: bool  # old key signed the migration
    new_key_signature: bool  # new key signed the migration
    signed_at: float  # claimed timestamp
    counterparties: list[CounterpartyInfo] = field(default_factory=list)
    attestations: list[dict] = field(default_factory=list)  # {agent_id, attested_at, pre_rotation_state_hash}


# Configuration
BASE_WINDOW_SECONDS = 3600  # 1 hour base
MAX_WINDOW_SECONDS = 86400 * 7  # 7 days max
MIN_QUORUM = 2
INDEPENDENCE_THRESHOLD = 0.5  # >50% must be truly independent


def effective_counterparties(counterparties: list[CounterpartyInfo]) -> list[CounterpartyInfo]:
    """Filter to independent counterparties only.
    Same operator = same entity in trench coat."""
    seen_operators = set()
    effective = []
    for cp in counterparties:
        if cp.is_independent and cp.operator not in seen_operators:
            seen_operators.add(cp.operator)
            effective.append(cp)
    return effective


def migration_window(active_counterparties: int) -> float:
    """Window scales inversely with counterparty count.
    More witnesses = shorter window needed."""
    if active_counterparties == 0:
        return float('inf')  # MANUAL
    window = BASE_WINDOW_SECONDS * (3 / max(1, active_counterparties))
    return min(MAX_WINDOW_SECONDS, max(BASE_WINDOW_SECONDS, window))


def required_quorum(active_counterparties: int) -> int:
    """Minimum attestations needed.
    At least 2, or all if fewer than 2 available."""
    if active_counterparties == 0:
        return 0  # MANUAL mode
    return min(MIN_QUORUM, active_counterparties)


def validate_migration(request: MigrationRequest) -> dict:
    """Validate a key migration request."""
    issues = []
    
    # Gate 1: Dual signature
    if not request.old_key_signature:
        issues.append("MISSING_OLD_KEY_SIGNATURE — cannot prove possession")
    if not request.new_key_signature:
        issues.append("MISSING_NEW_KEY_SIGNATURE — cannot prove new key control")
    
    dual_signed = request.old_key_signature and request.new_key_signature
    
    # Gate 2: Independent counterparties
    effective = effective_counterparties(request.counterparties)
    n_effective = len(effective)
    
    # Gate 3: Window calculation
    window = migration_window(n_effective)
    req_quorum = required_quorum(n_effective)
    
    # Gate 4: Attestation validation
    valid_attestations = []
    for att in request.attestations:
        # Check attestation is within window
        time_delta = abs(att.get("attested_at", 0) - request.signed_at)
        if time_delta <= window:
            # Check attestor is independent
            attestor_id = att.get("agent_id")
            is_effective = any(cp.agent_id == attestor_id for cp in effective)
            if is_effective:
                valid_attestations.append(att)
            else:
                issues.append(f"NON_INDEPENDENT_ATTESTOR — {attestor_id}")
        else:
            issues.append(f"ATTESTATION_OUTSIDE_WINDOW — {att.get('agent_id')} ({time_delta:.0f}s > {window:.0f}s)")
    
    quorum_met = len(valid_attestations) >= req_quorum
    
    # Determine status
    if n_effective == 0:
        status = "MANUAL"
        description = "Zero independent counterparties — human operator must intervene"
    elif not dual_signed:
        status = "REJECTED"
        description = "Missing dual signature — cannot verify key possession"
    elif quorum_met:
        status = "CONFIRMED"
        description = f"Dual-signed + {len(valid_attestations)}/{req_quorum} attestations within {window:.0f}s window"
    else:
        status = "PROVISIONAL"
        description = f"Dual-signed but only {len(valid_attestations)}/{req_quorum} attestations — awaiting quorum"
    
    return {
        "agent_id": request.agent_id,
        "status": status,
        "description": description,
        "dual_signed": dual_signed,
        "effective_counterparties": n_effective,
        "total_counterparties": len(request.counterparties),
        "migration_window_seconds": window if window != float('inf') else "INFINITE",
        "required_quorum": req_quorum,
        "valid_attestations": len(valid_attestations),
        "issues": issues,
    }


def demo():
    now = 1711144800.0  # arbitrary timestamp
    
    print("=" * 60)
    print("SCENARIO 1: Well-connected agent (10 counterparties)")
    print("=" * 60)
    
    cps = [CounterpartyInfo(f"cp_{i}", f"operator_{i}", now - 3600, True) for i in range(10)]
    result = validate_migration(MigrationRequest(
        agent_id="kit_fox",
        old_key_signature=True,
        new_key_signature=True,
        signed_at=now,
        counterparties=cps,
        attestations=[
            {"agent_id": "cp_0", "attested_at": now + 300, "pre_rotation_state_hash": "abc"},
            {"agent_id": "cp_1", "attested_at": now + 600, "pre_rotation_state_hash": "def"},
        ],
    ))
    print(json.dumps(result, indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 2: Isolated agent (1 counterparty)")
    print("=" * 60)
    
    result = validate_migration(MigrationRequest(
        agent_id="lonely_bot",
        old_key_signature=True,
        new_key_signature=True,
        signed_at=now,
        counterparties=[CounterpartyInfo("only_friend", "other_op", now - 1800, True)],
        attestations=[
            {"agent_id": "only_friend", "attested_at": now + 7200, "pre_rotation_state_hash": "xyz"},
        ],
    ))
    print(json.dumps(result, indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 3: Compromised key — attacker races")
    print("=" * 60)
    
    cps = [CounterpartyInfo(f"cp_{i}", f"operator_{i}", now - 3600, True) for i in range(5)]
    result = validate_migration(MigrationRequest(
        agent_id="compromised_agent",
        old_key_signature=True,  # attacker has old key
        new_key_signature=True,
        signed_at=now,
        counterparties=cps,
        attestations=[
            # attacker's accomplice — same operator
            {"agent_id": "fake_cp", "attested_at": now + 100},
        ],
    ))
    print(json.dumps(result, indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 4: Zero counterparties (new agent)")
    print("=" * 60)
    
    result = validate_migration(MigrationRequest(
        agent_id="brand_new",
        old_key_signature=True,
        new_key_signature=True,
        signed_at=now,
        counterparties=[],
        attestations=[],
    ))
    print(json.dumps(result, indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 5: Sybil counterparties (same operator)")
    print("=" * 60)
    
    # 5 counterparties but all same operator = 1 effective
    cps = [CounterpartyInfo(f"sybil_{i}", "same_operator", now - 1800, True) for i in range(5)]
    result = validate_migration(MigrationRequest(
        agent_id="sybil_target",
        old_key_signature=True,
        new_key_signature=True,
        signed_at=now,
        counterparties=cps,
        attestations=[
            {"agent_id": "sybil_0", "attested_at": now + 300},
            {"agent_id": "sybil_1", "attested_at": now + 400},
        ],
    ))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
