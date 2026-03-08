#!/usr/bin/env python3
"""iturtle-chain-validator.py — Validates trust chain termination (iTurtle model).

Based on McCune, Perrig, Seshadri & van Doorn (HotSec 2007):
"Turtles All The Way Down: Research Challenges in User-Based Attestation"

Every trust chain must terminate at an iTurtle — an axiomatically trustworthy
anchor. This tool validates chains against three termination criteria:
1. Named: the anchor has a verifiable identity
2. Time-bounded: the anchor's authority expires
3. Replaceable: the anchor can be rotated without system redesign

Chains that fail any criterion get downgraded.

Usage:
    python3 iturtle-chain-validator.py --demo
    python3 iturtle-chain-validator.py --chain '<json>'
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional


@dataclass
class TrustLink:
    """Single link in a trust chain."""
    entity: str
    role: str  # "anchor", "intermediate", "leaf"
    named: bool  # Has verifiable identity
    ttl_hours: Optional[float]  # None = permanent
    replaceable: bool  # Can be rotated
    attestation_type: str  # "self", "principal", "witness", "platform"


@dataclass 
class ChainVerdict:
    """Validation result for a trust chain."""
    chain_length: int
    terminates: bool  # Has an anchor
    anchor: Optional[str]
    named: bool
    time_bounded: bool
    replaceable: bool
    grade: str
    issues: List[str]
    recommendation: str


def grade_chain(named: bool, time_bounded: bool, replaceable: bool, 
                terminates: bool, self_attested: bool) -> str:
    """Grade a trust chain A-F."""
    if not terminates:
        return "F"
    score = sum([named, time_bounded, replaceable])
    if self_attested:
        score -= 1
    if score >= 3:
        return "A"
    elif score == 2:
        return "B"
    elif score == 1:
        return "C"
    else:
        return "D"


def validate_chain(links: List[TrustLink]) -> ChainVerdict:
    """Validate a trust chain against iTurtle criteria."""
    issues = []
    
    anchors = [l for l in links if l.role == "anchor"]
    if not anchors:
        return ChainVerdict(
            chain_length=len(links), terminates=False, anchor=None,
            named=False, time_bounded=False, replaceable=False,
            grade="F", issues=["No anchor found — turtles all the way down"],
            recommendation="Add a named, time-bounded human anchor"
        )
    
    anchor = anchors[0]
    named = anchor.named
    time_bounded = anchor.ttl_hours is not None
    replaceable = anchor.replaceable
    self_attested = anchor.attestation_type == "self"
    
    if not named:
        issues.append("Anchor is anonymous — cannot assign accountability")
    if not time_bounded:
        issues.append("Anchor has no TTL — compromise is permanent")
    if not replaceable:
        issues.append("Anchor cannot be rotated — no recovery from compromise")
    if self_attested:
        issues.append("Anchor is self-attested — confused deputy risk")
    
    # Check for gaps in chain
    for i, link in enumerate(links[1:], 1):
        if link.attestation_type == "self" and link.role != "anchor":
            issues.append(f"Link {i} ({link.entity}) is self-attested — chain gap")
    
    # Check TTL consistency
    ttls = [l.ttl_hours for l in links if l.ttl_hours is not None]
    if ttls and len(ttls) > 1:
        if ttls[0] < min(ttls[1:]):
            issues.append("Anchor TTL shorter than leaf — authority expires before subordinates")
    
    grade = grade_chain(named, time_bounded, replaceable, True, self_attested)
    
    if grade in ("A", "B"):
        rec = "Chain terminates properly. Monitor anchor TTL for renewal."
    elif grade == "C":
        rec = "Chain has gaps. Add time-bounding or identity to anchor."
    else:
        rec = "Chain is weak. Replace self-attested anchor with principal-signed scope cert."
    
    return ChainVerdict(
        chain_length=len(links), terminates=True, anchor=anchor.entity,
        named=named, time_bounded=time_bounded, replaceable=replaceable,
        grade=grade, issues=issues, recommendation=rec
    )


def demo():
    """Demo with example chains."""
    examples = {
        "isnad (DRTM)": [
            TrustLink("ilya", "anchor", True, 24.0, True, "principal"),
            TrustLink("scope-cert", "intermediate", True, 4.0, True, "principal"),
            TrustLink("kit", "leaf", True, 0.5, True, "witness"),
        ],
        "self-attestation": [
            TrustLink("agent-x", "anchor", False, None, False, "self"),
            TrustLink("agent-x-output", "leaf", False, None, False, "self"),
        ],
        "on-chain (SRTM)": [
            TrustLink("minter-contract", "anchor", True, None, False, "platform"),
            TrustLink("nft-cert", "intermediate", True, None, False, "platform"),
            TrustLink("agent-y", "leaf", True, None, True, "platform"),
        ],
        "no anchor": [
            TrustLink("agent-a", "intermediate", True, 4.0, True, "witness"),
            TrustLink("agent-b", "leaf", True, 2.0, True, "witness"),
        ],
    }
    
    print("=" * 60)
    print("iTURTLE TRUST CHAIN VALIDATION")
    print("McCune et al, HotSec 2007")
    print("=" * 60)
    
    for name, chain in examples.items():
        verdict = validate_chain(chain)
        print(f"\n[{verdict.grade}] {name} ({verdict.chain_length} links)")
        print(f"    Anchor: {verdict.anchor or 'NONE'}")
        print(f"    Named: {verdict.named} | TTL: {verdict.time_bounded} | Replaceable: {verdict.replaceable}")
        if verdict.issues:
            for issue in verdict.issues:
                print(f"    ⚠ {issue}")
        print(f"    → {verdict.recommendation}")
    
    print("\n" + "=" * 60)
    print("The iTurtle breaks the dependency loop.")
    print("Named + time-bounded + replaceable = honest dogmatic stop.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iTurtle trust chain validator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps({"examples": "use --demo for interactive output"}, indent=2))
    else:
        demo()
