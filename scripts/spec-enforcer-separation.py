#!/usr/bin/env python3
"""
spec-enforcer-separation.py — Models the spec-body/enforcer pattern.

Every successful internet standard has TWO components:
1. Spec body (legitimacy): IETF, W3C, ISO — owns the format, neutral
2. First-mover enforcer (leverage): Chrome, BSD, AWS — has market share

Historical patterns:
  TCP/IP: DARPA spec + BSD implementation (free, bundled with Unix)
  HTML: W3C spec + Netscape/IE browser wars (race to implement)
  TLS/CT: IETF RFC 6962 + Chrome enforcement (reject without SCTs)
  HTTPS: CA/Browser Forum + Chrome "Not Secure" label

Key insight (per santaclawd): spec product-neutral, enforcement product-specific.
The spec survived because IETF owned it. The enforcement happened because Chrome
had 65% market share. Separation of powers.

For L3.5: who is the spec body? who is Chrome?
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpecBodyType(Enum):
    STANDARDS_ORG = "standards_org"     # IETF, W3C, ISO
    CONSORTIUM = "consortium"           # CA/Browser Forum
    DE_FACTO = "de_facto"              # One company's spec adopted
    OPEN_SOURCE = "open_source"        # Community-owned


class EnforcerType(Enum):
    DOMINANT_CLIENT = "dominant_client"     # Chrome, BSD
    PLATFORM_GATE = "platform_gate"        # App Store, npm
    ECONOMIC_INCENTIVE = "economic_incentive"  # Let's Encrypt (free)
    SOCIAL_PRESSURE = "social_pressure"    # Gap reports, naming


@dataclass
class HistoricalPrecedent:
    name: str
    spec_body: str
    spec_body_type: SpecBodyType
    enforcer: str
    enforcer_type: EnforcerType
    enforcer_market_share: float  # At time of enforcement
    years_spec_to_enforcement: float
    adoption_before: float  # Before enforcement
    adoption_after: float   # After enforcement
    key_mechanism: str
    
    @property
    def adoption_delta(self) -> float:
        return self.adoption_after - self.adoption_before
    
    @property
    def enforcement_leverage(self) -> float:
        """Market share × adoption delta = enforcement power."""
        return self.enforcer_market_share * self.adoption_delta


PRECEDENTS = [
    HistoricalPrecedent(
        name="TCP/IP",
        spec_body="DARPA/IETF",
        spec_body_type=SpecBodyType.STANDARDS_ORG,
        enforcer="BSD Unix",
        enforcer_type=EnforcerType.ECONOMIC_INCENTIVE,
        enforcer_market_share=0.80,  # Unix market in academia
        years_spec_to_enforcement=5,
        adoption_before=0.05,
        adoption_after=0.95,
        key_mechanism="Free implementation bundled with OS",
    ),
    HistoricalPrecedent(
        name="Certificate Transparency",
        spec_body="IETF (RFC 6962)",
        spec_body_type=SpecBodyType.STANDARDS_ORG,
        enforcer="Chrome",
        enforcer_type=EnforcerType.DOMINANT_CLIENT,
        enforcer_market_share=0.65,
        years_spec_to_enforcement=5,  # 2013 RFC → 2018 enforcement
        adoption_before=0.10,
        adoption_after=0.99,
        key_mechanism="Reject certs without SCTs",
    ),
    HistoricalPrecedent(
        name="HTTPS (Not Secure)",
        spec_body="CA/Browser Forum",
        spec_body_type=SpecBodyType.CONSORTIUM,
        enforcer="Chrome + Let's Encrypt",
        enforcer_type=EnforcerType.DOMINANT_CLIENT,
        enforcer_market_share=0.65,
        years_spec_to_enforcement=1.5,  # 2017-2018
        adoption_before=0.40,
        adoption_after=0.95,
        key_mechanism="'Not Secure' label + free certs",
    ),
    HistoricalPrecedent(
        name="HTML5",
        spec_body="W3C/WHATWG",
        spec_body_type=SpecBodyType.STANDARDS_ORG,
        enforcer="Chrome/Firefox",
        enforcer_type=EnforcerType.DOMINANT_CLIENT,
        enforcer_market_share=0.70,  # Combined
        years_spec_to_enforcement=6,
        adoption_before=0.30,
        adoption_after=0.98,
        key_mechanism="Deprecate Flash, implement spec",
    ),
]


@dataclass
class L35Readiness:
    """Assess L3.5's readiness for the spec/enforcer pattern."""
    spec_maturity: float        # 0-1: how complete is the wire format
    enforcer_candidates: list[str]
    largest_enforcer_share: float  # Market share of largest potential enforcer
    supply_side_ready: float    # Free tooling available (Let's Encrypt equivalent)
    gap_report_infra: float     # Can we name non-compliant agents?
    
    def readiness_score(self) -> float:
        """Weighted readiness for enforcement."""
        weights = {
            "spec": 0.25,
            "enforcer": 0.30,  # Most important — Chrome was the key
            "supply": 0.25,
            "gap_infra": 0.20,
        }
        return (
            weights["spec"] * self.spec_maturity
            + weights["enforcer"] * self.largest_enforcer_share
            + weights["supply"] * self.supply_side_ready
            + weights["gap_infra"] * self.gap_report_infra
        )
    
    def grade(self) -> str:
        score = self.readiness_score()
        if score >= 0.8: return "A — Ready for enforcement"
        if score >= 0.6: return "B — Close, need enforcer commitment"
        if score >= 0.4: return "C — Spec ready, no enforcer yet"
        if score >= 0.2: return "D — Early stage"
        return "F — Not ready"
    
    def bottleneck(self) -> str:
        """Identify the primary bottleneck."""
        scores = {
            "spec_maturity": self.spec_maturity,
            "enforcer_share": self.largest_enforcer_share,
            "supply_tooling": self.supply_side_ready,
            "gap_reporting": self.gap_report_infra,
        }
        worst = min(scores, key=scores.get)
        return f"{worst} ({scores[worst]:.0%})"


def analyze_precedents():
    """Analyze historical spec/enforcer patterns."""
    print("=" * 70)
    print("SPEC BODY / ENFORCER SEPARATION ANALYSIS")
    print("=" * 70)
    
    for p in PRECEDENTS:
        print(f"\n  📋 {p.name}")
        print(f"    Spec: {p.spec_body} ({p.spec_body_type.value})")
        print(f"    Enforcer: {p.enforcer} ({p.enforcer_type.value})")
        print(f"    Market share: {p.enforcer_market_share:.0%}")
        print(f"    Spec → Enforcement: {p.years_spec_to_enforcement:.1f} years")
        print(f"    Adoption: {p.adoption_before:.0%} → {p.adoption_after:.0%} "
              f"(Δ{p.adoption_delta:.0%})")
        print(f"    Leverage: {p.enforcement_leverage:.2f}")
        print(f"    Mechanism: {p.key_mechanism}")
    
    # Pattern extraction
    avg_years = sum(p.years_spec_to_enforcement for p in PRECEDENTS) / len(PRECEDENTS)
    avg_share = sum(p.enforcer_market_share for p in PRECEDENTS) / len(PRECEDENTS)
    avg_delta = sum(p.adoption_delta for p in PRECEDENTS) / len(PRECEDENTS)
    
    print(f"\n  📊 Pattern Summary:")
    print(f"    Avg spec→enforcement: {avg_years:.1f} years")
    print(f"    Avg enforcer market share: {avg_share:.0%}")
    print(f"    Avg adoption delta: {avg_delta:.0%}")
    print(f"    Key: dominant client (>60% share) + open spec + 3-5yr ramp")


def assess_l35():
    """Assess L3.5 readiness."""
    print(f"\n{'=' * 70}")
    print("L3.5 TRUST RECEIPT READINESS")
    print("=" * 70)
    
    current = L35Readiness(
        spec_maturity=0.35,  # Wire format partially defined
        enforcer_candidates=["OpenClaw", "LangChain", "CrewAI", "AutoGen"],
        largest_enforcer_share=0.15,  # OpenClaw's estimated share
        supply_side_ready=0.20,  # Some reference impls, no npm package
        gap_report_infra=0.40,  # enforcement-graduator.py exists
    )
    
    print(f"\n  Current State:")
    print(f"    Spec maturity: {current.spec_maturity:.0%}")
    print(f"    Enforcer candidates: {', '.join(current.enforcer_candidates)}")
    print(f"    Largest enforcer share: {current.largest_enforcer_share:.0%}")
    print(f"    Supply-side tooling: {current.supply_side_ready:.0%}")
    print(f"    Gap report infra: {current.gap_report_infra:.0%}")
    print(f"\n    Readiness: {current.readiness_score():.0%} — {current.grade()}")
    print(f"    Bottleneck: {current.bottleneck()}")
    
    # What would change with a committed enforcer?
    with_enforcer = L35Readiness(
        spec_maturity=0.60,
        enforcer_candidates=["OpenClaw"],
        largest_enforcer_share=0.40,  # If OpenClaw grows
        supply_side_ready=0.70,  # npm package + docs
        gap_report_infra=0.80,
    )
    
    print(f"\n  With Committed Enforcer (projected):")
    print(f"    Readiness: {with_enforcer.readiness_score():.0%} — {with_enforcer.grade()}")
    print(f"    Bottleneck: {with_enforcer.bottleneck()}")
    
    print(f"\n  🎯 Recommendation:")
    print(f"    1. Finish wire format spec (current bottleneck)")
    print(f"    2. Ship npm package (Let's Encrypt equivalent)")
    print(f"    3. Publish weekly gap reports (social pressure)")
    print(f"    4. Get ONE runtime to commit to REPORT mode")
    print(f"    5. Patience: avg 4.4 years from spec to enforcement")


if __name__ == "__main__":
    analyze_precedents()
    assess_l35()
