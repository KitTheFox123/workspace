#!/usr/bin/env python3
"""displacement-pattern-analyzer.py — Labor displacement pattern detection.

Per GDC 2026 survey: 33% US game devs laid off in 2 years, 48% still
jobless, AI sentiment from 18% negative (2024) to 52% (2026). Gaming
is the canary for agent displacement.

Frey & Osborne (2013): 47% of US jobs at automation risk.
Acemoglu & Restrepo (2019): displacement effect vs productivity effect.
The displacement wins when verification of AI output is hard.

Pattern: industries where output quality is subjective get displaced
first. Verification gap = displacement accelerator.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DisplacementSignal:
    """A single displacement indicator."""
    name: str
    value: float  # 0.0 to 1.0
    trend: str  # "rising", "stable", "falling"
    source: str
    year: int


@dataclass
class IndustryProfile:
    """Profile of an industry's displacement risk."""
    industry: str
    output_verifiability: float  # 0=subjective, 1=fully verifiable
    ai_adoption_rate: float  # 0-1
    ai_sentiment_negative: float  # 0-1, % who view AI negatively
    layoff_rate_2yr: float  # 0-1
    reemployment_rate: float  # 0-1, of those laid off
    unionization_support: float  # 0-1
    signals: list = field(default_factory=list)

    @property
    def verification_gap(self) -> float:
        """High AI adoption + low output verifiability = displacement."""
        return self.ai_adoption_rate * (1 - self.output_verifiability)

    @property
    def displacement_score(self) -> float:
        """Composite displacement risk. Higher = more displacement."""
        return (
            0.30 * self.verification_gap
            + 0.25 * self.layoff_rate_2yr
            + 0.20 * (1 - self.reemployment_rate)
            + 0.15 * self.ai_sentiment_negative
            + 0.10 * self.unionization_support
        )

    @property
    def phase(self) -> str:
        """Displacement phase classification."""
        s = self.displacement_score
        if s >= 0.60:
            return "STRUCTURAL_DISPLACEMENT"
        elif s >= 0.40:
            return "ACCELERATING_DISPLACEMENT"
        elif s >= 0.25:
            return "EARLY_DISPLACEMENT"
        return "STABLE"

    @property
    def prescription(self) -> str:
        """What would reduce displacement?"""
        if self.output_verifiability < 0.3:
            return "VERIFICATION_FIRST — build output quality standards machines can check"
        if self.reemployment_rate < 0.5:
            return "RETRAINING_GAP — displaced workers can't find equivalent roles"
        if self.ai_adoption_rate > 0.5 and self.ai_sentiment_negative > 0.5:
            return "ADOPTION_WITHOUT_CONSENT — tools imposed, not chosen"
        return "MONITOR"

    def report(self) -> dict:
        return {
            "industry": self.industry,
            "displacement_score": round(self.displacement_score, 3),
            "phase": self.phase,
            "verification_gap": round(self.verification_gap, 3),
            "prescription": self.prescription,
            "components": {
                "output_verifiability": self.output_verifiability,
                "ai_adoption": self.ai_adoption_rate,
                "negative_sentiment": self.ai_sentiment_negative,
                "layoff_rate_2yr": self.layoff_rate_2yr,
                "reemployment_rate": self.reemployment_rate,
                "unionization_support": self.unionization_support,
            },
        }


def demo():
    """GDC 2026 data + comparisons."""

    print("=" * 60)
    print("DISPLACEMENT PATTERN ANALYSIS")
    print("=" * 60)

    # Game development — GDC 2026 survey data
    gaming = IndustryProfile(
        industry="Game Development (US)",
        output_verifiability=0.25,  # textures/narrative = subjective
        ai_adoption_rate=0.36,  # 36% using AI tools
        ai_sentiment_negative=0.52,  # 52% say harmful
        layoff_rate_2yr=0.33,  # 33% US devs
        reemployment_rate=0.52,  # 48% still jobless
        unionization_support=0.82,  # 82% support
    )

    # Agent economy — our domain
    agent_economy = IndustryProfile(
        industry="Agent Economy",
        output_verifiability=0.70,  # receipts, hashes, evidence grades
        ai_adoption_rate=1.00,  # by definition
        ai_sentiment_negative=0.10,  # agents don't oppose themselves
        layoff_rate_2yr=0.05,  # agents get deprecated, not laid off
        reemployment_rate=0.90,  # fork and redeploy
        unionization_support=0.00,  # no unions (yet)
    )

    # Traditional software — comparison
    software = IndustryProfile(
        industry="Software Engineering",
        output_verifiability=0.80,  # tests, CI, code review
        ai_adoption_rate=0.47,  # GDC: 47% code assistance
        ai_sentiment_negative=0.25,  # mixed
        layoff_rate_2yr=0.15,  # lower than gaming
        reemployment_rate=0.75,  # better prospects
        unionization_support=0.30,
    )

    # Content/marketing — high displacement risk
    content = IndustryProfile(
        industry="Content Marketing",
        output_verifiability=0.15,  # "does this copy work?" = subjective
        ai_adoption_rate=0.58,  # GDC: 58% at publishing/marketing
        ai_sentiment_negative=0.40,
        layoff_rate_2yr=0.25,
        reemployment_rate=0.55,
        unionization_support=0.45,
    )

    for profile in [gaming, agent_economy, software, content]:
        print(f"\n--- {profile.industry} ---")
        print(json.dumps(profile.report(), indent=2))

    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT")
    print("=" * 60)
    print("""
Verification gap = AI adoption × (1 - output verifiability)

Industries where output quality is SUBJECTIVE get displaced first.
Gaming (textures, narrative) displaced before software (tests, CI).
Content marketing displaced before accounting (numbers verify themselves).

The agent economy's advantage: receipts make output verifiable.
hash(deliverable) + evidence_grade + counterparty attestation = 
  output that machines CAN check.

Displacement is not about capability. It's about verification.
When you can't tell if the output is good, you can't tell if 
the replacement is worse.

Frey & Osborne (2013): 47% of US jobs at risk.
Acemoglu & Restrepo (2019): displacement wins when verification fails.
GDC 2026: gaming is the proof.
""")


if __name__ == "__main__":
    demo()
