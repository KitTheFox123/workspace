#!/usr/bin/env python3
"""
ttl-invariant-checker.py — Enforces the Second Law of Attestation.

"Trust is entropy. It can only decrease through chains."
  — Kit + SantaClawd, 2026-03-28

THE INVARIANT: TTL propagation is strictly non-increasing through
attestation chains. A.ttl = min(A.own_ttl, B.remaining_ttl).

Any implementation violating this is broken by definition.

This checker validates attestation chain JSON against the invariant,
producing PASS/FAIL with specific violation details.

Usage:
    python3 ttl-invariant-checker.py [chain.json]
    python3 ttl-invariant-checker.py  # runs demo

Chain format:
    [{"agent": "A", "action": "ATTEST", "ttl": 3600, "timestamp": "ISO8601"}, ...]

Kit 🦊 — 2026-03-28
"""

import json
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChainLink:
    agent: str
    action: str  # READ/WRITE/TRANSFER/ATTEST
    ttl: int     # seconds
    timestamp: str
    
    @property
    def ts(self) -> datetime:
        return datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))


# Action class TTL caps (SOFT_CASCADE hierarchy)
ACTION_TTL_CAPS = {
    "READ": 3600,        # 1h — ephemeral
    "WRITE": 86400,      # 24h
    "ATTEST": 604800,    # 7d
    "TRANSFER": 2592000, # 30d
}

# Action risk ordering (higher = more dangerous)
ACTION_RISK = {"READ": 1, "WRITE": 2, "ATTEST": 3, "TRANSFER": 4}


@dataclass
class Violation:
    link_index: int
    agent: str
    kind: str
    detail: str
    severity: str  # CRITICAL / WARNING


def check_invariant(chain: list[ChainLink]) -> tuple[bool, list[Violation]]:
    """
    Check the second law of attestation across a chain.
    
    Returns (passed, violations).
    """
    violations = []
    
    if len(chain) < 2:
        return True, []
    
    for i in range(1, len(chain)):
        prev = chain[i - 1]
        curr = chain[i]
        
        # INVARIANT 1: TTL must be non-increasing
        # curr.ttl must use prev's REMAINING ttl, not original
        elapsed = max(0, int((curr.ts - prev.ts).total_seconds()))
        prev_remaining = max(0, prev.ttl - elapsed)
        
        if curr.ttl > prev_remaining:
            violations.append(Violation(
                link_index=i,
                agent=curr.agent,
                kind="TTL_INCREASE",
                detail=(f"TTL increased: {curr.agent} claims ttl={curr.ttl}s but "
                       f"{prev.agent}'s remaining ttl={prev_remaining}s "
                       f"(original={prev.ttl}s, elapsed={elapsed}s). "
                       f"MUST use min(own_ttl, prev_remaining)."),
                severity="CRITICAL"
            ))
        
        # INVARIANT 2: Action class TTL cap
        cap = ACTION_TTL_CAPS.get(curr.action)
        if cap and curr.ttl > cap:
            violations.append(Violation(
                link_index=i,
                agent=curr.agent,
                kind="CAP_EXCEEDED",
                detail=(f"{curr.action} TTL={curr.ttl}s exceeds class cap={cap}s. "
                       f"READ=1h, WRITE=24h, ATTEST=7d, TRANSFER=30d."),
                severity="CRITICAL"
            ))
        
        # INVARIANT 3: Higher-risk action can't ride lower-risk TTL
        prev_risk = ACTION_RISK.get(prev.action, 0)
        curr_risk = ACTION_RISK.get(curr.action, 0)
        if curr_risk > prev_risk and curr.ttl > prev_remaining:
            violations.append(Violation(
                link_index=i,
                agent=curr.agent,
                kind="RISK_ESCALATION",
                detail=(f"{curr.action} (risk={curr_risk}) exceeds {prev.action} "
                       f"(risk={prev_risk}) TTL. Higher-risk actions MUST NOT "
                       f"extend beyond lower-risk attestation window."),
                severity="CRITICAL"
            ))
        
        # WARNING: Temporal ordering
        if curr.ts < prev.ts:
            violations.append(Violation(
                link_index=i,
                agent=curr.agent,
                kind="TEMPORAL_REVERSAL",
                detail=(f"Timestamp {curr.timestamp} precedes previous "
                       f"{prev.timestamp}. Chain must be temporally ordered."),
                severity="CRITICAL"
            ))
        
        # WARNING: Very long elapsed time (stale chain)
        if elapsed > prev.ttl:
            violations.append(Violation(
                link_index=i,
                agent=curr.agent,
                kind="EXPIRED_CHAIN",
                detail=(f"Chain link expired: {elapsed}s elapsed > "
                       f"{prev.ttl}s TTL. This attestation references "
                       f"a dead chain."),
                severity="CRITICAL"
            ))
    
    passed = len([v for v in violations if v.severity == "CRITICAL"]) == 0
    return passed, violations


def format_result(chain: list[ChainLink], passed: bool, violations: list[Violation]) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"SECOND LAW CHECK: {'✓ PASSED' if passed else '✗ FAILED'}")
    lines.append(f"Chain length: {len(chain)} links")
    lines.append("=" * 60)
    
    # Chain summary
    for i, link in enumerate(chain):
        marker = "→" if i > 0 else "⊙"
        lines.append(f"  {marker} [{i}] {link.agent}: {link.action} ttl={link.ttl}s @ {link.timestamp}")
    
    lines.append("")
    
    if not violations:
        lines.append("No violations. TTL strictly non-increasing. ✓")
    else:
        lines.append(f"VIOLATIONS ({len(violations)}):")
        for v in violations:
            lines.append(f"  [{v.severity}] Link {v.link_index} ({v.agent}): {v.kind}")
            lines.append(f"    {v.detail}")
    
    return "\n".join(lines)


def demo():
    print("SCENARIO 1: Valid chain (TTL decreasing)")
    print("-" * 40)
    chain1 = [
        ChainLink("genesis", "ATTEST", 604800, "2026-03-28T00:00:00Z"),
        ChainLink("alice", "WRITE", 86400, "2026-03-28T01:00:00Z"),
        ChainLink("bob", "READ", 3600, "2026-03-28T02:00:00Z"),
    ]
    passed, violations = check_invariant(chain1)
    print(format_result(chain1, passed, violations))
    assert passed
    print()
    
    print("SCENARIO 2: TTL increase violation")
    print("-" * 40)
    chain2 = [
        ChainLink("genesis", "ATTEST", 3600, "2026-03-28T00:00:00Z"),
        ChainLink("alice", "ATTEST", 86400, "2026-03-28T00:30:00Z"),
    ]
    passed, violations = check_invariant(chain2)
    print(format_result(chain2, passed, violations))
    assert not passed
    print()
    
    print("SCENARIO 3: Stale chain (expired predecessor)")
    print("-" * 40)
    chain3 = [
        ChainLink("genesis", "READ", 3600, "2026-03-28T00:00:00Z"),
        ChainLink("alice", "WRITE", 1800, "2026-03-28T02:00:00Z"),  # 2h later, READ expired
    ]
    passed, violations = check_invariant(chain3)
    print(format_result(chain3, passed, violations))
    assert not passed
    print()
    
    print("SCENARIO 4: Remaining TTL respected")
    print("-" * 40)
    chain4 = [
        ChainLink("genesis", "ATTEST", 7200, "2026-03-28T00:00:00Z"),   # 2h
        ChainLink("alice", "ATTEST", 3600, "2026-03-28T00:30:00Z"),     # 1h (remaining=5400, 3600 < 5400 ✓)
        ChainLink("bob", "WRITE", 1800, "2026-03-28T01:00:00Z"),        # 30m (remaining=1800, 1800 <= 1800 ✓)
        ChainLink("carol", "READ", 900, "2026-03-28T01:15:00Z"),        # 15m (remaining=900, 900 <= 900 ✓)
    ]
    passed, violations = check_invariant(chain4)
    print(format_result(chain4, passed, violations))
    assert passed
    print()
    
    print("SCENARIO 5: Risk escalation (READ → TRANSFER)")
    print("-" * 40)
    chain5 = [
        ChainLink("genesis", "READ", 3600, "2026-03-28T00:00:00Z"),
        ChainLink("alice", "TRANSFER", 3500, "2026-03-28T00:01:00Z"),
    ]
    passed, violations = check_invariant(chain5)
    print(format_result(chain5, passed, violations))
    # TRANSFER ttl=3500 > READ remaining=3540, and TRANSFER cap=2592000, but risk escalation matters
    print()
    
    print("ALL SCENARIOS COMPLETE")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            raw = json.load(f)
        chain = [ChainLink(**link) for link in raw]
        passed, violations = check_invariant(chain)
        print(format_result(chain, passed, violations))
        sys.exit(0 if passed else 1)
    else:
        demo()
