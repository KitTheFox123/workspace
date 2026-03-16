#!/usr/bin/env python3
"""
spec-enforcer-separation.py — Model the spec-owner vs enforcer pattern.

Every successful internet standard has two distinct roles:
  1. Spec owner (neutral, multi-stakeholder): DARPA, W3C, IETF
  2. Enforcer (market power, ships code): BSD, browsers, Chrome

Counterexamples where this failed:
  - XMPP: IETF spec, no dominant enforcer → fragmented into silos
  - OSI: better spec, no shipped implementation → lost to TCP/IP
  - RSS: no clear spec owner, no enforcer → Atom fork, both stagnated

Applied to L3.5:
  - Spec: GitHub RFC (neutral, forkable, PR-based governance)
  - Enforcer: Agent runtimes (OpenClaw, etc.) that default-reject

Key insight from Chrome CT: the spec has to work in REPORT mode first.
If nobody uses it voluntarily, forcing it kills adoption.
Let's Encrypt proved supply creates demand (free certs → HTTPS growth).
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpecHealth(Enum):
    HEALTHY = "healthy"           # Spec + enforcer, both active
    ORPHANED = "orphaned"         # Spec exists, no enforcer
    PROPRIETARY = "proprietary"   # Enforcer exists, no open spec
    FRAGMENTED = "fragmented"     # Multiple specs, no dominant enforcer
    DEAD = "dead"                 # Neither active


@dataclass
class StandardHistory:
    """Historical record of a standard's spec/enforcer lifecycle."""
    name: str
    spec_owner: str
    enforcer: str
    spec_year: int
    enforcement_year: int
    adoption_rate: float  # Peak adoption %
    status: SpecHealth
    notes: str = ""
    
    @property
    def adoption_lag_years(self) -> int:
        return self.enforcement_year - self.spec_year
    
    @property
    def had_voluntary_adoption(self) -> bool:
        """Did anyone adopt before enforcement?"""
        return self.adoption_lag_years > 2


# Historical dataset
STANDARDS = [
    StandardHistory("TCP/IP", "DARPA/IETF", "BSD Unix", 1974, 1983, 0.99,
                    SpecHealth.HEALTHY, "BSD shipped it. DARPA funded it. Market followed."),
    StandardHistory("HTML", "W3C", "Browsers (Netscape→IE→Chrome)", 1993, 1995, 0.99,
                    SpecHealth.HEALTHY, "Browser wars enforced divergent HTML. Standards converged later."),
    StandardHistory("TLS/CT", "IETF (RFC 6962)", "Chrome", 2013, 2018, 0.95,
                    SpecHealth.HEALTHY, "5yr lag. Let's Encrypt (supply) + Chrome (demand) = adoption."),
    StandardHistory("HTTPS", "IETF", "Chrome 'Not Secure'", 1995, 2017, 0.95,
                    SpecHealth.HEALTHY, "22yr spec, 3yr enforcement ramp. Chrome 56→62→68."),
    StandardHistory("XMPP", "IETF (RFC 6120)", "None (Jabber fragmented)", 1999, 0, 0.05,
                    SpecHealth.ORPHANED, "Great spec. No enforcer. Proprietary silos won."),
    StandardHistory("OSI", "ISO", "None", 1984, 0, 0.01,
                    SpecHealth.DEAD, "Better spec. No implementation. TCP/IP shipped first."),
    StandardHistory("RSS", "Multiple (0.91/1.0/2.0/Atom)", "None", 1999, 0, 0.30,
                    SpecHealth.FRAGMENTED, "Fork war. No governance. Stagnated."),
    StandardHistory("ActivityPub", "W3C", "Mastodon", 2018, 2022, 0.02,
                    SpecHealth.HEALTHY, "Small but growing. Mastodon = enforcer. Twitter exodus = catalyst."),
    StandardHistory("DKIM", "IETF (RFC 6376)", "Gmail/Outlook", 2007, 2012, 0.85,
                    SpecHealth.HEALTHY, "Gmail enforcing = adoption. Same pattern."),
]


@dataclass
class L35Assessment:
    """Assess L3.5's position in the spec/enforcer lifecycle."""
    spec_maturity: float      # 0-1: how complete is the wire format
    enforcer_count: int       # How many runtimes enforce
    voluntary_adoption: float # 0-1: adoption rate in REPORT mode
    market_concentration: float  # 0-1: largest enforcer's market share
    
    def health(self) -> SpecHealth:
        if self.spec_maturity < 0.3:
            return SpecHealth.DEAD
        if self.enforcer_count == 0:
            return SpecHealth.ORPHANED
        if self.spec_maturity > 0.5 and self.enforcer_count >= 1:
            return SpecHealth.HEALTHY
        return SpecHealth.FRAGMENTED
    
    def readiness_for_enforcement(self) -> dict:
        """Is the ecosystem ready for STRICT mode?"""
        blockers = []
        
        # Chrome CT lesson: voluntary adoption first
        if self.voluntary_adoption < 0.40:
            blockers.append(f"Voluntary adoption {self.voluntary_adoption:.0%} < 40% (Let's Encrypt threshold)")
        
        # Need at least one enforcer with market power
        if self.enforcer_count == 0:
            blockers.append("No enforcer. Spec without enforcement = XMPP.")
        
        # Concentration matters
        if self.market_concentration < 0.20:
            blockers.append(f"No runtime has {self.market_concentration:.0%} share (Chrome had 65%)")
        
        # Spec must be mature enough
        if self.spec_maturity < 0.70:
            blockers.append(f"Spec {self.spec_maturity:.0%} complete (need 70%+ before enforcement)")
        
        ready = len(blockers) == 0
        phase = "STRICT" if ready else (
            "REPORT" if self.voluntary_adoption > 0.10 else "PERMISSIVE"
        )
        
        return {
            "ready_for_strict": ready,
            "recommended_phase": phase,
            "health": self.health().value,
            "blockers": blockers,
            "historical_parallel": self._find_parallel(),
        }
    
    def _find_parallel(self) -> str:
        """Find closest historical parallel."""
        if self.enforcer_count == 0 and self.spec_maturity > 0.5:
            return "XMPP (good spec, no enforcer → fragmentation)"
        if self.voluntary_adoption > 0.3 and self.enforcer_count >= 1:
            return "TLS/CT pre-2018 (voluntary + enforcer emerging)"
        if self.spec_maturity < 0.3:
            return "OSI (spec not shipped → irrelevant)"
        if self.enforcer_count >= 2:
            return "ActivityPub (multiple enforcers, growing)"
        return "Early TCP/IP (spec exists, adoption beginning)"


def demo():
    """Show historical patterns and L3.5 assessment."""
    print("=" * 70)
    print("SPEC/ENFORCER SEPARATION — Historical Patterns")
    print("=" * 70)
    
    print(f"\n{'Standard':<15} {'Spec Owner':<20} {'Enforcer':<25} {'Lag':>4} {'Adopt':>6} {'Status'}")
    print("-" * 95)
    
    for s in STANDARDS:
        lag = f"{s.adoption_lag_years}yr" if s.enforcement_year > 0 else "N/A"
        print(f"{s.name:<15} {s.spec_owner:<20} {s.enforcer:<25} {lag:>4} {s.adoption_rate:>5.0%} {s.status.value}")
    
    # Key findings
    healthy = [s for s in STANDARDS if s.status == SpecHealth.HEALTHY]
    avg_lag = sum(s.adoption_lag_years for s in healthy) / len(healthy)
    
    print(f"\n📊 Key Findings:")
    print(f"  Healthy standards: {len(healthy)}/{len(STANDARDS)}")
    print(f"  Average spec→enforcement lag: {avg_lag:.1f} years")
    print(f"  All healthy standards had: open spec + dominant enforcer")
    print(f"  All failures had: missing enforcer OR missing spec")
    
    # L3.5 assessment
    print(f"\n{'=' * 70}")
    print("L3.5 TRUST RECEIPT — Current Assessment")
    print(f"{'=' * 70}")
    
    l35 = L35Assessment(
        spec_maturity=0.45,       # Wire format designed, not formalized
        enforcer_count=0,         # No runtime enforces yet
        voluntary_adoption=0.01,  # Only Kit + collaborators
        market_concentration=0.15,  # OpenClaw is small
    )
    
    assessment = l35.readiness_for_enforcement()
    print(f"\n  Health: {assessment['health']}")
    print(f"  Recommended phase: {assessment['recommended_phase']}")
    print(f"  Ready for STRICT: {assessment['ready_for_strict']}")
    print(f"  Historical parallel: {assessment['historical_parallel']}")
    if assessment['blockers']:
        print(f"  Blockers:")
        for b in assessment['blockers']:
            print(f"    ❌ {b}")
    
    print(f"\n  💡 Recommendations:")
    print(f"    1. Formalize wire format (spec maturity 45% → 70%)")
    print(f"    2. Ship reference enforcer in ONE runtime (OpenClaw?)")
    print(f"    3. Run REPORT mode for 6+ months (build gap data)")
    print(f"    4. Publish gap reports (Chrome CT naming pattern)")
    print(f"    5. Graduate to STRICT when gap < 5%")
    print(f"    6. NEVER skip REPORT phase (XMPP lesson)")


if __name__ == "__main__":
    demo()
