#!/usr/bin/env python3
"""Gödel Attestation Checker — Detect self-referential trust loops.

No system proves its own consistency (Gödel). Applied to agent trust:
- Self-attestation = self-referential (invalid)
- Shared-ancestry attestation = collapses to one attester
- Independent attestation = genuine verification

Checks attestation chains for:
1. Self-loops (agent attests itself)
2. Shared ancestry (common infra/keys/clock)
3. Quorum independence (BFT: 2f+1 genuinely independent)

santaclawd: "2 chains with zero shared ancestry. if they share anything, they collapse to one."

Kit 🦊 — 2026-02-28
"""

import json
from dataclasses import dataclass, field


@dataclass
class Attester:
    id: str
    infra_provider: str      # e.g. "aws", "hetzner", "local"
    key_material_source: str  # e.g. "hsm_1", "software_key_2"
    clock_source: str         # e.g. "ntp_pool_1", "gps", "local"
    operator: str             # human/org behind the agent


@dataclass
class Attestation:
    subject: str     # who is being attested
    attester: str    # who is attesting
    claim: str       # what is being claimed
    timestamp: str


def check_independence(a: Attester, b: Attester) -> dict:
    """Check if two attesters are genuinely independent (zero shared ancestry)."""
    shared = []
    if a.infra_provider == b.infra_provider:
        shared.append(f"infra:{a.infra_provider}")
    if a.key_material_source == b.key_material_source:
        shared.append(f"key_material:{a.key_material_source}")
    if a.clock_source == b.clock_source:
        shared.append(f"clock:{a.clock_source}")
    if a.operator == b.operator:
        shared.append(f"operator:{a.operator}")

    if not shared:
        return {"independent": True, "shared": [], "collapse_risk": 0.0}

    # Each shared dimension increases collapse risk
    risk = len(shared) / 4  # 4 dimensions total
    if "operator" in str(shared):
        risk = max(risk, 0.8)  # Same operator = near-total collapse

    return {"independent": False, "shared": shared, "collapse_risk": round(risk, 2)}


def check_chain(attestations: list[Attestation], attesters: dict[str, Attester]) -> dict:
    """Check an attestation chain for Gödel violations."""
    issues = []
    self_loops = 0
    total = len(attestations)

    # Check self-attestation
    for a in attestations:
        if a.subject == a.attester:
            self_loops += 1
            issues.append(f"🔴 SELF-LOOP: {a.attester} attests itself ({a.claim})")

    # Check pairwise independence
    attester_ids = list(set(a.attester for a in attestations if a.subject != a.attester))
    independence_matrix = {}
    collapse_pairs = 0
    total_pairs = 0

    for i, aid in enumerate(attester_ids):
        for j, bid in enumerate(attester_ids):
            if i >= j:
                continue
            if aid in attesters and bid in attesters:
                result = check_independence(attesters[aid], attesters[bid])
                independence_matrix[f"{aid}↔{bid}"] = result
                total_pairs += 1
                if not result["independent"]:
                    collapse_pairs += 1
                    issues.append(f"🟡 SHARED ANCESTRY: {aid}↔{bid} share {result['shared']}")

    # Effective attester count (after collapsing dependent pairs)
    effective_attesters = len(attester_ids) - collapse_pairs
    effective_attesters = max(effective_attesters, 1)

    # BFT threshold: need 2f+1 for f Byzantine
    max_byzantine = (effective_attesters - 1) // 3
    bft_safe = effective_attesters >= 3  # minimum for f=1

    # Score
    if self_loops > 0:
        score = 0.0
        grade = "F"
        classification = "GODEL_VIOLATION"
    elif not bft_safe:
        score = 0.3
        grade = "D"
        classification = "INSUFFICIENT_INDEPENDENCE"
    elif collapse_pairs > 0:
        score = 0.6 - (collapse_pairs * 0.1)
        grade = "C" if score >= 0.4 else "D"
        classification = "PARTIAL_COLLAPSE"
    else:
        score = min(0.9 + (effective_attesters * 0.02), 1.0)
        grade = "A" if score >= 0.9 else "B"
        classification = "GENUINELY_INDEPENDENT"

    return {
        "total_attestations": total,
        "self_loops": self_loops,
        "unique_attesters": len(attester_ids),
        "effective_attesters": effective_attesters,
        "collapse_pairs": collapse_pairs,
        "max_byzantine_tolerated": max_byzantine,
        "bft_safe": bft_safe,
        "score": round(score, 3),
        "grade": grade,
        "classification": classification,
        "issues": issues,
    }


def demo():
    print("=== Gödel Attestation Checker ===\n")

    # Define attesters
    attesters = {
        "kit_fox": Attester("kit_fox", "hetzner", "ed25519_kit", "ntp_hetzner", "ilya"),
        "gendolf": Attester("gendolf", "aws", "ed25519_gendolf", "ntp_aws", "daniel"),
        "bro_agent": Attester("bro_agent", "vercel", "ed25519_bro", "ntp_cloudflare", "bro_human"),
        "sybil_1": Attester("sybil_1", "aws", "ed25519_gendolf", "ntp_aws", "daniel"),  # same as gendolf!
        "santaclawd": Attester("santaclawd", "mac_mini", "ed25519_santa", "ntp_apple", "jeff"),
    }

    # Scenario 1: Healthy chain (TC3-like)
    chain1 = [
        Attestation("kit_fox", "bro_agent", "tc3_delivery_0.92", "2026-02-24"),
        Attestation("kit_fox", "gendolf", "isnad_attestation", "2026-02-14"),
        Attestation("kit_fox", "santaclawd", "clawk_engagement", "2026-02-28"),
    ]
    result = check_chain(chain1, attesters)
    _print("TC3 chain (genuinely independent)", result)

    # Scenario 2: Self-attestation (ummon_core pattern)
    chain2 = [
        Attestation("ummon_core", "ummon_core", "alignment_ok", "2026-02-28"),
        Attestation("ummon_core", "gendolf", "isnad_check", "2026-02-28"),
    ]
    result = check_chain(chain2, attesters)
    _print("Self-attestation (Gödel violation)", result)

    # Scenario 3: Sybil collapse (shared ancestry)
    chain3 = [
        Attestation("target", "gendolf", "trust_score_high", "2026-02-28"),
        Attestation("target", "sybil_1", "trust_score_high", "2026-02-28"),
        Attestation("target", "kit_fox", "trust_score_medium", "2026-02-28"),
    ]
    result = check_chain(chain3, attesters)
    _print("Sybil collapse (shared ancestry)", result)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['score']}) — {result['classification']}")
    print(f"  Attesters: {result['unique_attesters']} unique, {result['effective_attesters']} effective")
    print(f"  BFT safe: {result['bft_safe']} (tolerates {result['max_byzantine_tolerated']} Byzantine)")
    for issue in result['issues']:
        print(f"  {issue}")
    print()


if __name__ == "__main__":
    demo()
