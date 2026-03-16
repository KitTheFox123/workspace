#!/usr/bin/env python3
"""
graduation-patterns.py — Cross-domain graduated enforcement patterns.

The same graduation pattern appears everywhere safety matters:
  - Chrome CT: REPORT → WARN → STRICT (18 months)
  - FDA trials: Phase I (safety) → II (efficacy) → III (population) → approval
  - Aviation: voluntary reporting → ASRS → mandatory incident reporting
  - Nuclear: defense-in-depth layers, each gate-checked independently
  - GDPR: guidance → warnings → fines (graduated sanctions)

Common structure:
  1. OBSERVE phase (collect data, no enforcement)
  2. REPORT phase (flag violations, accept anyway)
  3. WARN phase (surface issues to users)
  4. ENFORCE phase (reject non-compliant)

Each gate requires:
  - Minimum duration (can't rush safety)
  - Minimum sample size (statistical significance)
  - Maximum failure rate (ecosystem readiness)
  - No regression (can't skip phases)

Cross-domain insight: graduated enforcement ALWAYS outperforms
binary (off/on) enforcement. The observe phase IS the product.
"""

from dataclasses import dataclass
from enum import Enum


class Domain(Enum):
    PROTOCOL = "protocol"
    MEDICAL = "medical"
    AVIATION = "aviation"
    NUCLEAR = "nuclear"
    REGULATION = "regulation"


@dataclass
class Phase:
    name: str
    duration: str
    gate: str
    failure_mode: str


@dataclass
class GraduationPattern:
    domain: Domain
    name: str
    phases: list[Phase]
    total_duration: str
    key_insight: str
    anti_pattern: str  # What happens without graduation


PATTERNS = [
    GraduationPattern(
        domain=Domain.PROTOCOL,
        name="Chrome Certificate Transparency",
        phases=[
            Phase("EV-only", "2 years (2015-2017)", 
                  "EV cert compliance >99%", "False sense of security for non-EV"),
            Phase("Report-only", "6 months (2017-2018)",
                  "All cert compliance >95%", "CAs ignore reports without deadline"),
            Phase("Full enforcement", "Permanent (Apr 2018+)",
                  "Chrome rejects certs without SCTs", "Breaking sites = Chrome's problem"),
        ],
        total_duration="3 years (proposal to full enforcement)",
        key_insight="Published compliance reports named non-compliant CAs. Public shaming > private warnings.",
        anti_pattern="HTTP/2 push: shipped without graduation, deprecated 4 years later.",
    ),
    GraduationPattern(
        domain=Domain.MEDICAL,
        name="FDA Clinical Trials",
        phases=[
            Phase("Phase I", "6-12 months",
                  "Safe in 20-100 healthy volunteers", "Toxicity missed in small samples"),
            Phase("Phase II", "1-2 years",
                  "Effective in 100-300 patients", "Efficacy signal in wrong population"),
            Phase("Phase III", "2-4 years",
                  "Safe+effective in 1000-5000 patients", "Rare side effects missed"),
            Phase("Phase IV", "Post-market surveillance",
                  "Ongoing safety monitoring", "Withdrawn drugs (Vioxx, thalidomide)"),
        ],
        total_duration="6-12 years",
        key_insight="Each phase has DIFFERENT success criteria. Phase I ≠ small Phase III.",
        anti_pattern="Emergency Use Authorization: skip phases under pressure. Works for pandemics, dangerous for routine.",
    ),
    GraduationPattern(
        domain=Domain.AVIATION,
        name="Aviation Safety Reporting (ASRS → SMS)",
        phases=[
            Phase("Voluntary reporting", "1976-1990s",
                  "Pilots report without punishment", "Underreporting of near-misses"),
            Phase("Mandatory incident reporting", "1990s-2000s",
                  "Airlines must report defined events", "Gaming definitions to avoid reporting"),
            Phase("Safety Management Systems", "2006+",
                  "Proactive risk identification + mitigation", "Compliance theater without culture"),
            Phase("Data-driven enforcement", "2015+",
                  "Pattern detection across reports", "Alert fatigue from too many signals"),
        ],
        total_duration="40+ years (still evolving)",
        key_insight="Immunity from punishment in early phases was essential. Pilots won't report if reporting = consequences.",
        anti_pattern="Punitive response to human error (pre-ASRS): pilots hid incidents → worse outcomes.",
    ),
    GraduationPattern(
        domain=Domain.NUCLEAR,
        name="Nuclear Safety (Defense in Depth)",
        phases=[
            Phase("Prevention", "Design phase",
                  "Inherent safety features", "Reliance on active safety only"),
            Phase("Detection", "Operational",
                  "Monitoring + early warning", "Alert fatigue / normalization of deviance"),
            Phase("Mitigation", "Incident response",
                  "Containment + damage limitation", "Cascade failure (Fukushima)"),
            Phase("Emergency", "Beyond design basis",
                  "Evacuation + long-term management", "Political override of technical advice"),
        ],
        total_duration="Continuous (no graduation — all phases active simultaneously)",
        key_insight="Not sequential — all layers active always. Failure of one layer ≠ failure of system.",
        anti_pattern="Chernobyl: safety tests that disabled safety systems. Testing the defense by removing it.",
    ),
    GraduationPattern(
        domain=Domain.REGULATION,
        name="GDPR Enforcement",
        phases=[
            Phase("Guidance period", "2016-2018",
                  "Companies adapt to published rules", "Confusion over interpretation"),
            Phase("Warnings", "2018-2019",
                  "Supervisory authority sends warnings", "Companies treat warnings as ceiling"),
            Phase("Graduated fines", "2019+",
                  "Fines proportional to violation severity", "€746M Amazon fine = cost of business"),
            Phase("Structural remedies", "2020+",
                  "Data practice changes mandated", "Enforcement asymmetry (big vs small)"),
        ],
        total_duration="4+ years to meaningful enforcement",
        key_insight="2-year adaptation period before enforcement. Even then, largest fines came 3+ years after effective date.",
        anti_pattern="Cookie banners: letter-of-law compliance that makes UX worse without improving privacy.",
    ),
]


def cross_domain_analysis():
    """Extract common graduation principles across domains."""
    
    print("=" * 70)
    print("CROSS-DOMAIN GRADUATED ENFORCEMENT PATTERNS")
    print("=" * 70)
    
    for p in PATTERNS:
        print(f"\n{'─' * 70}")
        print(f"  {p.name} ({p.domain.value})")
        print(f"  Total duration: {p.total_duration}")
        print(f"  Phases: {len(p.phases)}")
        for i, phase in enumerate(p.phases, 1):
            print(f"    {i}. {phase.name} ({phase.duration})")
            print(f"       Gate: {phase.gate}")
        print(f"  💡 Insight: {p.key_insight}")
        print(f"  ⚠️ Anti-pattern: {p.anti_pattern}")
    
    print(f"\n{'=' * 70}")
    print("UNIVERSAL PRINCIPLES")
    print("=" * 70)
    
    principles = [
        ("Observation before enforcement",
         "Every domain starts by collecting data before punishing violations. "
         "Aviation ASRS: immunity from punishment was essential for honest reporting."),
        ("Phase gates, not timelines",
         "Graduation triggers are pass-rate-based, not calendar-based. "
         "FDA doesn't advance to Phase III because 2 years passed — only when Phase II succeeds."),
        ("Public accountability accelerates adoption",
         "Chrome CT compliance reports. GDPR DPA decisions. FDA advisory committee meetings. "
         "Transparency > private warnings."),
        ("The anti-pattern is always binary enforcement",
         "Off/on enforcement fails everywhere: punitive aviation reporting, "
         "HTTP/2 push (shipped without graduation), Chernobyl safety test."),
        ("All phases active simultaneously (defense in depth)",
         "Nuclear safety runs all layers in parallel. "
         "Mature systems don't retire early phases — they add layers."),
    ]
    
    for i, (name, desc) in enumerate(principles, 1):
        print(f"\n  {i}. {name}")
        print(f"     {desc}")
    
    # L3.5 mapping
    print(f"\n{'=' * 70}")
    print("L3.5 TRUST RECEIPT GRADUATION (applying cross-domain lessons)")
    print("=" * 70)
    
    l35_phases = [
        ("OBSERVE (FDA Phase I)", "3 months",
         "Collect baseline. How many agents produce valid receipts? What breaks?",
         "Aviation ASRS: no punishment for non-compliance during observation."),
        ("REPORT (FDA Phase II)", "6 months", 
         "Log violations, publish gap reports. Name non-compliant agents.",
         "Chrome CT: CAs fixed infra because compliance data was public."),
        ("WARN (FDA Phase III)", "6 months",
         "Surface 'Unverified Receipt' to consumers. Don't reject yet.",
         "GDPR warnings: companies treat as signal, not ceiling."),
        ("ENFORCE (Post-market)", "Permanent",
         "Reject unverified. Continuous monitoring for regression.",
         "Nuclear defense in depth: enforcement phase doesn't retire earlier phases."),
    ]
    
    for name, duration, desc, analogy in l35_phases:
        print(f"\n  {name} ({duration})")
        print(f"    {desc}")
        print(f"    Analogy: {analogy}")


if __name__ == "__main__":
    cross_domain_analysis()
