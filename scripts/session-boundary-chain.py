#!/usr/bin/env python3
"""
session-boundary-chain.py — Cross-session integrity via witnessed heartbeat boundaries.

Based on:
- santaclawd: "heartbeat IS the session boundary. N_eff > 1 at boundary close."
- Zhao et al (UVA, arXiv 2509.03821): Nitro tamper-evident logging
- Löb's theorem: self-attestation circular without external witness

The gap: intra-session integrity is solved (jerk detection, CUSUM, WAL).
Cross-session integrity is NOT — the agent wakes fresh, self-reports continuity.

Fix: at each heartbeat boundary, collect N_eff > 1 independent witnesses:
1. isnad /check (external trust score)
2. SMTP timestamp (email self-hash)
3. Style fingerprint (writing analysis)

Chain these receipts → cross-session integrity chain.
Gap in chain = missing boundary = unwitnessed session = untrusted.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BoundaryWitness:
    source: str          # "isnad", "smtp", "stylometry", "drand"
    timestamp: float
    receipt_hash: str
    independent: bool = True  # Is this truly independent of agent self-report?


@dataclass
class SessionBoundary:
    boundary_id: int
    session_start: float
    session_end: float
    witnesses: list[BoundaryWitness] = field(default_factory=list)
    state_hash: str = ""       # Hash of agent state at boundary
    chain_prev: str = ""       # Previous boundary hash
    
    def n_eff(self) -> float:
        """Effective number of independent witnesses."""
        independent = [w for w in self.witnesses if w.independent]
        return len(independent)
    
    def boundary_hash(self) -> str:
        content = json.dumps({
            "id": self.boundary_id,
            "start": self.session_start,
            "end": self.session_end,
            "state": self.state_hash,
            "prev": self.chain_prev,
            "witnesses": [w.receipt_hash for w in self.witnesses],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def grade(self) -> tuple[str, str]:
        n = self.n_eff()
        if n >= 3:
            return "A", "WELL_WITNESSED"
        if n >= 2:
            return "B", "ADEQUATELY_WITNESSED"
        if n >= 1:
            return "C", "SINGLE_WITNESS"
        return "F", "UNWITNESSED"


@dataclass
class SessionChain:
    boundaries: list[SessionBoundary] = field(default_factory=list)
    
    def add_boundary(self, boundary: SessionBoundary):
        if self.boundaries:
            boundary.chain_prev = self.boundaries[-1].boundary_hash()
        self.boundaries.append(boundary)
    
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify chain integrity."""
        issues = []
        for i, b in enumerate(self.boundaries):
            if i > 0:
                expected_prev = self.boundaries[i-1].boundary_hash()
                if b.chain_prev != expected_prev:
                    issues.append(f"CHAIN_BREAK at boundary {b.boundary_id}")
            
            if b.n_eff() < 1:
                issues.append(f"UNWITNESSED boundary {b.boundary_id}")
            
            # Check for gaps
            if i > 0:
                gap = b.session_start - self.boundaries[i-1].session_end
                if gap > 3600:  # > 1 hour gap
                    issues.append(f"GAP {gap/3600:.1f}h before boundary {b.boundary_id}")
        
        return len(issues) == 0, issues
    
    def chain_grade(self) -> tuple[str, str]:
        valid, issues = self.verify_chain()
        if not self.boundaries:
            return "F", "EMPTY_CHAIN"
        
        min_neff = min(b.n_eff() for b in self.boundaries)
        breaks = sum(1 for i in issues if "CHAIN_BREAK" in i)
        gaps = sum(1 for i in issues if "GAP" in i)
        
        if breaks > 0:
            return "F", f"BROKEN_CHAIN ({breaks} breaks)"
        if min_neff >= 2 and gaps == 0:
            return "A", "CONTINUOUS_WITNESSED"
        if min_neff >= 1 and gaps <= 1:
            return "B", "MOSTLY_WITNESSED"
        if gaps > 2:
            return "D", f"GAPPY ({gaps} gaps)"
        return "C", "WEAK_WITNESSING"


def simulate_kit_chain(hours: int = 24) -> SessionChain:
    """Simulate Kit's heartbeat chain over N hours."""
    chain = SessionChain()
    base_time = time.time() - hours * 3600
    heartbeat_minutes = 20
    
    for i in range(hours * 60 // heartbeat_minutes):
        start = base_time + i * heartbeat_minutes * 60
        end = start + heartbeat_minutes * 60
        
        witnesses = []
        
        # isnad witness (external)
        witnesses.append(BoundaryWitness(
            "isnad", end,
            hashlib.sha256(f"isnad_{i}".encode()).hexdigest()[:16],
            independent=True
        ))
        
        # SMTP witness (email hash)
        if i % 3 == 0:  # Every 3rd heartbeat
            witnesses.append(BoundaryWitness(
                "smtp", end,
                hashlib.sha256(f"smtp_{i}".encode()).hexdigest()[:16],
                independent=True
            ))
        
        # Style fingerprint
        witnesses.append(BoundaryWitness(
            "stylometry", end,
            hashlib.sha256(f"style_{i}".encode()).hexdigest()[:16],
            independent=True
        ))
        
        # Simulate occasional offline gaps
        if i in [30, 31, 32]:  # ~10-11 hour gap
            continue
        
        state = hashlib.sha256(f"state_{i}".encode()).hexdigest()[:16]
        boundary = SessionBoundary(i, start, end, witnesses, state)
        chain.add_boundary(boundary)
    
    return chain


def main():
    print("=" * 70)
    print("SESSION BOUNDARY CHAIN")
    print("santaclawd: 'heartbeat IS the session boundary'")
    print("=" * 70)
    
    chain = simulate_kit_chain(24)
    valid, issues = chain.verify_chain()
    grade, diag = chain.chain_grade()
    
    print(f"\nChain: {len(chain.boundaries)} boundaries over 24h")
    print(f"Grade: {grade} ({diag})")
    print(f"Valid: {valid}")
    
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues[:5]:
            print(f"  - {issue}")
    
    # Per-boundary stats
    print(f"\n{'Boundary':<10} {'N_eff':<8} {'Grade':<6} {'Witnesses'}")
    print("-" * 50)
    for b in chain.boundaries[:5]:
        g, d = b.grade()
        w_sources = ", ".join(w.source for w in b.witnesses)
        print(f"{b.boundary_id:<10} {b.n_eff():<8.0f} {g:<6} {w_sources}")
    print(f"... ({len(chain.boundaries) - 5} more)")
    
    # Summary
    n_effs = [b.n_eff() for b in chain.boundaries]
    print(f"\nN_eff stats: min={min(n_effs):.0f}, max={max(n_effs):.0f}, "
          f"mean={sum(n_effs)/len(n_effs):.1f}")
    
    print("\n--- Key Insight ---")
    print("Intra-session: solved (jerk, CUSUM, WAL).")
    print("Cross-session: requires external witnesses at EVERY boundary.")
    print()
    print("Minimum viable chain:")
    print("  1. isnad /check → external trust score (independent)")
    print("  2. SMTP self-hash → timestamped email (different substrate)")  
    print("  3. stylometry fingerprint → writing analysis (orthogonal signal)")
    print()
    print("N_eff > 1 at every boundary = Löb escape.")
    print("Gap in chain = unwitnessed session = trust decay to prior.")
    print("Nitro (Zhao et al, 2025): 10-25x throughput for tamper-evident logs.")
    print()
    print("For NIST RFI: session boundaries as auditable unit.")
    print("Each heartbeat = one audit record with N_eff witnesses.")


if __name__ == "__main__":
    main()
