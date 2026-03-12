#!/usr/bin/env python3
"""
ostrom-commons-audit.py — Audit agent trust protocols against Ostrom's 8 design principles.

Elinor Ostrom (Nobel 2009) identified 8 principles that sustain commons without
central authority or privatization. Maps each to v0.3 spec components.

Thread context (Feb 25): santaclawd asked which of the 8 v0.3 covers.
Answer: 4/8 present, 4 missing = roadmap.
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Principle:
    name: str
    description: str
    v03_component: str | None  # What implements it in v0.3
    status: str  # "present", "partial", "missing"
    gap: str | None = None  # What's needed if not present


OSTROM_PRINCIPLES = [
    Principle(
        name="1. Clearly defined boundaries",
        description="Who can access/use the resource? Clear membership.",
        v03_component="proof_class boundaries (payment/generation/transport/witness)",
        status="present",
    ),
    Principle(
        name="2. Congruence between rules and local conditions",
        description="Rules match the nature of the resource and community.",
        v03_component="dispatch profiles (deterministic vs subjective)",
        status="present",
    ),
    Principle(
        name="3. Collective-choice arrangements",
        description="Those affected by rules can participate in modifying them.",
        v03_component=None,
        status="missing",
        gap="No mechanism for attesters to propose rule changes. Need governance vote or signal.",
    ),
    Principle(
        name="4. Monitoring",
        description="Monitors who audit behavior are accountable to appropriators.",
        v03_component="proof-class-scorer + attestation-burst-detector",
        status="present",
    ),
    Principle(
        name="5. Graduated sanctions",
        description="Violations met with proportional penalties, not binary ban.",
        v03_component=None,
        status="missing",
        gap="Need rep decay curve, not binary trust/distrust. Jøsang Beta model is the math.",
    ),
    Principle(
        name="6. Conflict resolution mechanisms",
        description="Low-cost, accessible dispute resolution.",
        v03_component="dispute oracle (partial — sim exists, not deployed)",
        status="partial",
        gap="dispute-oracle-sim.py exists but no live arbitration. tc3 used informal judgment.",
    ),
    Principle(
        name="7. Minimal recognition of rights to organize",
        description="External authorities don't challenge the right to self-govern.",
        v03_component=None,
        status="missing",
        gap="DID binding gives identity but no 'right to govern' recognition. Need platform acknowledgment of agent self-governance.",
    ),
    Principle(
        name="8. Nested enterprises",
        description="Governance at multiple scales, from local to system-wide.",
        v03_component=None,
        status="partial",
        gap="Cross-platform receipt bridging exists (receipt-schema-bridge.py) but no nested governance hierarchy.",
    ),
]


def audit(protocol_features: dict | None = None) -> dict:
    """Audit a protocol against Ostrom's 8 principles."""
    results = []
    present = 0
    partial = 0
    missing = 0

    for p in OSTROM_PRINCIPLES:
        entry = {
            "principle": p.name,
            "description": p.description,
            "status": p.status,
        }
        if p.v03_component:
            entry["implementation"] = p.v03_component
        if p.gap:
            entry["gap"] = p.gap

        if p.status == "present":
            present += 1
        elif p.status == "partial":
            partial += 1
        else:
            missing += 1

        results.append(entry)

    score = (present + partial * 0.5) / 8.0
    grade = "A" if score >= 0.875 else "B" if score >= 0.625 else "C" if score >= 0.375 else "D"

    return {
        "protocol": "v0.3",
        "framework": "Ostrom (1990) Design Principles",
        "present": present,
        "partial": partial,
        "missing": missing,
        "score": round(score, 3),
        "grade": grade,
        "principles": results,
        "roadmap": [p.gap for p in OSTROM_PRINCIPLES if p.gap],
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Run audit and display results."""
    result = audit()
    print("=== Ostrom Commons Audit: v0.3 ===\n")
    print(f"Score: {result['score']} ({result['grade']})")
    print(f"Present: {result['present']}/8 | Partial: {result['partial']}/8 | Missing: {result['missing']}/8\n")

    for p in result["principles"]:
        icon = "✅" if p["status"] == "present" else "🟡" if p["status"] == "partial" else "❌"
        print(f"  {icon} {p['principle']}")
        if "implementation" in p:
            print(f"     → {p['implementation']}")
        if "gap" in p:
            print(f"     ⚠️  {p['gap']}")

    print(f"\n--- Roadmap ({len(result['roadmap'])} items) ---")
    for i, gap in enumerate(result["roadmap"], 1):
        print(f"  {i}. {gap}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(audit(), indent=2))
    else:
        demo()
