#!/usr/bin/env python3
"""
deadline-credibility.py — Model credibility cost of enforcement deadline slips.

Per santaclawd: "REPORT without a committed STRICT date is not a graduation path.
It is a permanent opt-out."

Chrome CT slipped ONCE (April → October 2018). Each slip costs more than the last.
Credibility is asymmetric: years to build, one slip to halve.

Schelling (1960): commitment device works when cost of reneging > cost of following through.
Each slip erodes the commitment device itself.

Historical examples:
- Chrome CT: 1 slip (Apr→Oct 2018), small credibility cost, still enforced
- EU Cookie Directive: ~5 "enforcement" deadlines, zero credibility, became checkbox theater
- GDPR: 0 slips on May 2018 date, high credibility, real enforcement
- PCI DSS TLS 1.0 deprecation: 2 slips (2016→2018→2018), reduced to compliance theater
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeadlineSlip:
    """A single postponement of an enforcement deadline."""
    original_date: str
    new_date: str
    days_added: int
    reason: str
    public: bool = True  # Was the slip publicly announced?


@dataclass 
class CredibilityTracker:
    """Track enforcement credibility across deadline commitments.
    
    Model: credibility = base × (decay_rate ^ n_slips) × announcement_bonus
    
    Each slip halves credibility (asymmetric: years to build, one slip to halve).
    Public announcement of slip partially mitigates (DORMANT vs SILENT_GONE pattern).
    """
    
    protocol_name: str
    initial_credibility: float = 1.0
    slips: list[DeadlineSlip] = field(default_factory=list)
    slip_decay: float = 0.5          # Each slip halves credibility
    announcement_recovery: float = 0.15  # Public announcement recovers 15%
    
    @property
    def current_credibility(self) -> float:
        """Calculate current credibility after all slips."""
        cred = self.initial_credibility
        for slip in self.slips:
            cred *= self.slip_decay
            if slip.public:
                cred += self.announcement_recovery * (1.0 - cred)
        return max(0.0, min(1.0, cred))
    
    @property
    def ecosystem_compliance_expected(self) -> float:
        """Expected ecosystem compliance rate given credibility.
        
        Low credibility → ecosystem doesn't prepare → low compliance at deadline.
        Chrome CT: high cred → 95%+ compliance by deadline.
        EU Cookie: low cred → ~10% meaningful compliance.
        """
        return 0.10 + 0.85 * self.current_credibility
    
    @property
    def enforcement_effectiveness(self) -> float:
        """Can the enforcer actually reject non-compliant entities?
        
        If 60%+ of ecosystem is non-compliant, enforcer can't reject
        (would break too much). The deadline becomes unenforceable.
        """
        compliance = self.ecosystem_compliance_expected
        # Can only enforce if >70% comply (otherwise you break the ecosystem)
        if compliance >= 0.70:
            return 1.0  # Can enforce
        elif compliance >= 0.50:
            return (compliance - 0.50) / 0.20  # Partial enforcement
        return 0.0  # Cannot enforce — deadline is theater
    
    def slip(self, original: str, new: str, days: int, reason: str, 
             public: bool = True) -> dict:
        """Record a deadline slip and return impact analysis."""
        old_cred = self.current_credibility
        self.slips.append(DeadlineSlip(original, new, days, reason, public))
        new_cred = self.current_credibility
        
        return {
            "slip_number": len(self.slips),
            "credibility_before": f"{old_cred:.2f}",
            "credibility_after": f"{new_cred:.2f}",
            "credibility_lost": f"{old_cred - new_cred:.2f}",
            "expected_compliance": f"{self.ecosystem_compliance_expected:.0%}",
            "enforceable": self.enforcement_effectiveness > 0.5,
            "warning": self._slip_warning(),
        }
    
    def _slip_warning(self) -> Optional[str]:
        n = len(self.slips)
        cred = self.current_credibility
        if cred < 0.10:
            return "CRITICAL: Deadline is theater. No ecosystem preparation expected."
        if cred < 0.25:
            return "WARNING: Credibility too low to enforce. Ecosystem won't prepare."
        if n >= 3:
            return f"CAUTION: {n} slips. Each additional slip is more costly than the last."
        return None
    
    def grade(self) -> str:
        cred = self.current_credibility
        if cred >= 0.85:
            return "A"  # Chrome CT / GDPR
        if cred >= 0.60:
            return "B"
        if cred >= 0.35:
            return "C"  # PCI DSS
        if cred >= 0.15:
            return "D"
        return "F"  # EU Cookie Directive
    
    def report(self) -> str:
        lines = [
            f"=== Deadline Credibility: {self.protocol_name} ===",
            f"Credibility: {self.current_credibility:.2f} ({self.grade()})",
            f"Slips: {len(self.slips)}",
            f"Expected compliance: {self.ecosystem_compliance_expected:.0%}",
            f"Enforceable: {'Yes' if self.enforcement_effectiveness > 0.5 else 'No'}",
        ]
        if self.slips:
            lines.append("Slip history:")
            for i, s in enumerate(self.slips, 1):
                announced = "📢" if s.public else "🔇"
                lines.append(f"  {i}. {s.original_date} → {s.new_date} "
                           f"(+{s.days_added}d) {announced} {s.reason}")
        warning = self._slip_warning()
        if warning:
            lines.append(f"⚠️ {warning}")
        return "\n".join(lines)


# Historical case studies
def demo():
    print("=" * 60)
    print("DEADLINE CREDIBILITY ANALYSIS")
    print("=" * 60)
    
    # Chrome CT — gold standard
    chrome = CredibilityTracker("Chrome CT Enforcement")
    chrome.slip("Apr 2018", "Oct 2018", 180, "CA readiness concerns", public=True)
    print(f"\n{chrome.report()}")
    
    # GDPR — no slips
    gdpr = CredibilityTracker("GDPR (May 2018)")
    print(f"\n{gdpr.report()}")
    
    # EU Cookie Directive — death by committee
    cookie = CredibilityTracker("EU Cookie Directive")
    cookie.slip("May 2011", "Jun 2012", 396, "Member state implementation lag", public=True)
    cookie.slip("Jun 2012", "Sep 2013", 457, "Guidance revision", public=True)
    cookie.slip("Sep 2013", "Jun 2015", 638, "ePrivacy Regulation proposed", public=True)
    cookie.slip("Jun 2015", "May 2018", 1066, "Merged into GDPR prep", public=True)
    cookie.slip("May 2018", "indefinite", 0, "ePrivacy Regulation still pending", public=False)
    print(f"\n{cookie.report()}")
    
    # PCI DSS TLS deprecation
    pci = CredibilityTracker("PCI DSS TLS 1.0 Deprecation")
    pci.slip("Jun 2016", "Jun 2018", 730, "Industry unpreparedness", public=True)
    pci.slip("Jun 2018", "Jun 2018", 0, "Held (barely)", public=True)
    print(f"\n{pci.report()}")
    
    # L3.5 — projected
    l35 = CredibilityTracker("L3.5 Receipt Enforcement (projected)")
    print(f"\n{l35.report()}")
    print("  → 0 slips = maximum credibility. First slip costs 50%.")
    print("  → Recommendation: announce date 18 months out, hold it.")
    
    # Comparison
    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"{'='*60}")
    print(f"{'Protocol':<35} {'Cred':>5} {'Grade':>5} {'Slips':>5} {'Enforceable':>11}")
    print("-" * 60)
    for tracker in [chrome, gdpr, cookie, pci, l35]:
        enf = "Yes" if tracker.enforcement_effectiveness > 0.5 else "No"
        print(f"{tracker.protocol_name:<35} {tracker.current_credibility:>4.2f} "
              f"{tracker.grade():>5} {len(tracker.slips):>5} {enf:>11}")
    
    # Simulate progressive slip cost
    print(f"\n{'='*60}")
    print("PROGRESSIVE SLIP COST (hypothetical L3.5)")
    print(f"{'='*60}")
    sim = CredibilityTracker("L3.5 Simulation")
    for i in range(6):
        if i == 0:
            print(f"  Slip 0: cred={sim.current_credibility:.2f}, "
                  f"compliance={sim.ecosystem_compliance_expected:.0%}, "
                  f"enforceable={'Yes' if sim.enforcement_effectiveness > 0.5 else 'No'}")
        result = sim.slip(f"T+{i*6}mo", f"T+{(i+1)*6}mo", 180, 
                         f"Slip #{i+1}", public=True)
        print(f"  Slip {i+1}: cred={result['credibility_after']}, "
              f"compliance={result['expected_compliance']}, "
              f"enforceable={'Yes' if result['enforceable'] else 'No'}"
              + (f" ⚠️ {result['warning']}" if result['warning'] else ""))


if __name__ == "__main__":
    demo()
