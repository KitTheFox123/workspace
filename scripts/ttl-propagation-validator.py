#!/usr/bin/env python3
"""
ttl-propagation-validator.py — Validates TTL propagation in attestation chains.

Problem: "TTL laundering" — stale attestations get re-laundered by fresh
re-attestation. A attests B with ttl=24h. After 23h, C re-attests A's
attestation using A's ORIGINAL ttl (24h), not REMAINING ttl (1h).
Result: stale trust looks fresh.

Fix: TTL propagation must be monotonically decreasing. Each hop can only
SHORTEN, never extend. Same principle as IP TTL decrement (RFC 791 §3.2).

    propagated_ttl = min(own_ttl, upstream_remaining_ttl)

This ensures:
1. Chains can't exceed the shortest-lived link
2. Re-attestation can't launder expired trust  
3. Deep chains naturally compress toward zero (like IP packets)

Sources:
- RFC 791 §3.2: IP TTL decrement per hop
- van der Hofstad (arXiv:2512.15673, ICM 2026): Phase transitions in
  percolation on random graphs — TTL as percolation probability
- ATF min() composition: already proven for trust scores, extends to TTL

Kit 🦊 — 2026-03-28
"""

import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum


class TTLStatus(Enum):
    VALID = "VALID"
    LAUNDERED = "LAUNDERED"      # TTL extended beyond upstream remaining
    EXPIRED = "EXPIRED"           # TTL already elapsed
    CIRCULAR = "CIRCULAR"         # Chain references itself
    MONOTONIC_VIOLATION = "MONOTONIC_VIOLATION"  # TTL increased in chain


@dataclass
class AttestationLink:
    attester: str
    subject: str
    action_class: str           # READ/WRITE/TRANSFER/ATTEST
    original_ttl_hours: float   # TTL when issued
    issued_at: str              # ISO 8601
    upstream_link_id: str | None = None  # Chain reference


@dataclass
class TTLValidation:
    status: TTLStatus
    chain: list[str]
    effective_ttl_hours: float  # Actual remaining TTL at chain end
    details: str
    violations: list[dict] = field(default_factory=list)


class TTLPropagationValidator:
    """
    Validates TTL propagation through attestation chains.
    
    Core rule: propagated_ttl = min(own_ttl, upstream_remaining_ttl)
    Monotonically decreasing. Each hop costs you.
    """
    
    def __init__(self, now: datetime | None = None):
        self.links: dict[str, AttestationLink] = {}
        self.now = now or datetime.now(timezone.utc)
    
    def add_link(self, link_id: str, link: AttestationLink):
        self.links[link_id] = link
    
    def _remaining_ttl(self, link: AttestationLink) -> float:
        """Calculate remaining TTL in hours."""
        issued = datetime.fromisoformat(link.issued_at.replace('Z', '+00:00'))
        elapsed = (self.now - issued).total_seconds() / 3600
        return max(0.0, link.original_ttl_hours - elapsed)
    
    def validate_chain(self, leaf_link_id: str) -> TTLValidation:
        """Walk the chain from leaf to root, validating TTL at each hop."""
        chain = []
        violations = []
        visited = set()
        
        current_id = leaf_link_id
        effective_ttl = float('inf')
        
        while current_id is not None:
            if current_id in visited:
                return TTLValidation(
                    status=TTLStatus.CIRCULAR,
                    chain=chain,
                    effective_ttl_hours=0.0,
                    details=f"Circular chain at {current_id}",
                    violations=[{"type": "circular", "link": current_id}]
                )
            
            visited.add(current_id)
            
            if current_id not in self.links:
                break
            
            link = self.links[current_id]
            chain.append(f"{link.attester}→{link.subject} ({link.action_class})")
            
            remaining = self._remaining_ttl(link)
            
            # Check expiry
            if remaining <= 0:
                return TTLValidation(
                    status=TTLStatus.EXPIRED,
                    chain=chain,
                    effective_ttl_hours=0.0,
                    details=f"Link {current_id} expired. "
                            f"Original TTL: {link.original_ttl_hours}h, "
                            f"remaining: {remaining:.2f}h"
                )
            
            # Core rule: effective TTL = min(own remaining, upstream effective)
            prev_effective = effective_ttl
            effective_ttl = min(effective_ttl, remaining)
            
            # Check monotonic decrease through chain
            # Compare link's TTL at ISSUE TIME vs upstream's remaining at ISSUE TIME
            if link.upstream_link_id and link.upstream_link_id in self.links:
                upstream = self.links[link.upstream_link_id]
                # Upstream remaining at the time this link was issued
                link_issued = datetime.fromisoformat(link.issued_at.replace('Z', '+00:00'))
                upstream_issued = datetime.fromisoformat(upstream.issued_at.replace('Z', '+00:00'))
                upstream_elapsed_at_link_issue = (link_issued - upstream_issued).total_seconds() / 3600
                upstream_remaining = max(0.0, upstream.original_ttl_hours - upstream_elapsed_at_link_issue)
                
                if link.original_ttl_hours > upstream_remaining:
                    violations.append({
                        "type": "laundering",
                        "link": current_id,
                        "attester": link.attester,
                        "own_ttl": link.original_ttl_hours,
                        "upstream_remaining": round(upstream_remaining, 2),
                        "detail": f"{link.attester} set TTL={link.original_ttl_hours}h "
                                  f"but upstream only has {upstream_remaining:.2f}h remaining. "
                                  f"TTL laundering detected."
                    })
            
            current_id = link.upstream_link_id
        
        chain.reverse()
        
        if violations:
            return TTLValidation(
                status=TTLStatus.LAUNDERED,
                chain=chain,
                effective_ttl_hours=round(effective_ttl, 3),
                details=f"{len(violations)} TTL laundering violation(s). "
                        "Chain extends trust beyond upstream remaining TTL.",
                violations=violations
            )
        
        return TTLValidation(
            status=TTLStatus.VALID,
            chain=chain,
            effective_ttl_hours=round(effective_ttl, 3),
            details=f"Chain valid. Effective TTL: {effective_ttl:.2f}h. "
                    "Monotonically decreasing."
        )
    
    def suggest_fix(self, link_id: str) -> dict | None:
        """Suggest corrected TTL for a laundering violation."""
        if link_id not in self.links:
            return None
        
        link = self.links[link_id]
        if not link.upstream_link_id or link.upstream_link_id not in self.links:
            return None
        
        upstream = self.links[link.upstream_link_id]
        upstream_remaining = self._remaining_ttl(upstream)
        
        corrected = min(link.original_ttl_hours, upstream_remaining)
        
        return {
            "link_id": link_id,
            "original_ttl": link.original_ttl_hours,
            "corrected_ttl": round(corrected, 2),
            "rule": "min(own_ttl, upstream_remaining_ttl)",
            "upstream_remaining": round(upstream_remaining, 2)
        }


def demo():
    # Set "now" to a fixed time for reproducibility
    now = datetime(2026, 3, 28, 4, 0, 0, tzinfo=timezone.utc)
    
    print("=" * 60)
    print("SCENARIO 1: Valid chain — TTLs monotonically decrease")
    print("=" * 60)
    
    v1 = TTLPropagationValidator(now=now)
    v1.add_link("root", AttestationLink(
        attester="genesis", subject="alice", action_class="ATTEST",
        original_ttl_hours=48,
        issued_at="2026-03-27T04:00:00Z"
    ))
    v1.add_link("hop1", AttestationLink(
        attester="alice", subject="bob", action_class="WRITE",
        original_ttl_hours=20,  # < upstream remaining (24h)
        issued_at="2026-03-27T12:00:00Z",
        upstream_link_id="root"
    ))
    v1.add_link("hop2", AttestationLink(
        attester="bob", subject="carol", action_class="READ",
        original_ttl_hours=6,   # < upstream remaining
        issued_at="2026-03-28T00:00:00Z",
        upstream_link_id="hop1"
    ))
    
    result = v1.validate_chain("hop2")
    print(f"Status: {result.status.value}")
    print(f"Chain: {' → '.join(result.chain)}")
    print(f"Effective TTL: {result.effective_ttl_hours}h")
    print(f"Details: {result.details}")
    assert result.status == TTLStatus.VALID
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 2: TTL laundering — downstream extends expired upstream")
    print("=" * 60)
    
    v2 = TTLPropagationValidator(now=now)
    # Upstream has 2h remaining; downstream claims 48h — laundering
    v2.add_link("root", AttestationLink(
        attester="genesis", subject="alice", action_class="ATTEST",
        original_ttl_hours=26,  # issued 24h ago → 2h remaining
        issued_at="2026-03-27T04:00:00Z"
    ))
    v2.add_link("launder", AttestationLink(
        attester="alice", subject="bob", action_class="TRANSFER",
        original_ttl_hours=48,  # LAUNDERING: 48h > upstream's 2h remaining at issue!
        issued_at="2026-03-28T03:00:00Z",  # issued 1h ago; upstream had 3h left then
        upstream_link_id="root"
    ))
    
    result = v2.validate_chain("launder")
    print(f"Status: {result.status.value}")
    print(f"Chain: {' → '.join(result.chain)}")
    print(f"Effective TTL: {result.effective_ttl_hours}h")
    print(f"Violations: {len(result.violations)}")
    for v in result.violations:
        print(f"  {v['detail']}")
    
    fix = v2.suggest_fix("launder")
    if fix:
        print(f"\nSuggested fix: TTL {fix['original_ttl']}h → {fix['corrected_ttl']}h")
        print(f"  Rule: {fix['rule']}")
    
    assert result.status == TTLStatus.LAUNDERED
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 3: Expired link in chain")
    print("=" * 60)
    
    v3 = TTLPropagationValidator(now=now)
    v3.add_link("expired", AttestationLink(
        attester="genesis", subject="alice", action_class="ATTEST",
        original_ttl_hours=12,
        issued_at="2026-03-27T00:00:00Z"  # 28h ago, TTL was 12h → expired
    ))
    
    result = v3.validate_chain("expired")
    print(f"Status: {result.status.value}")
    print(f"Details: {result.details}")
    assert result.status == TTLStatus.EXPIRED
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 4: Circular chain")
    print("=" * 60)
    
    v4 = TTLPropagationValidator(now=now)
    v4.add_link("a", AttestationLink(
        attester="alice", subject="bob", action_class="ATTEST",
        original_ttl_hours=24,
        issued_at="2026-03-28T00:00:00Z",
        upstream_link_id="b"
    ))
    v4.add_link("b", AttestationLink(
        attester="bob", subject="alice", action_class="ATTEST",
        original_ttl_hours=24,
        issued_at="2026-03-28T00:00:00Z",
        upstream_link_id="a"
    ))
    
    result = v4.validate_chain("a")
    print(f"Status: {result.status.value}")
    print(f"Details: {result.details}")
    assert result.status == TTLStatus.CIRCULAR
    print("✓ PASSED\n")
    
    print("ALL 4 SCENARIOS PASSED ✓")
    print()
    print("KEY: TTL propagation = IP TTL decrement (RFC 791 §3.2).")
    print("Each hop can only shorten, never extend.")
    print("propagated_ttl = min(own_ttl, upstream_remaining_ttl)")


if __name__ == "__main__":
    demo()
