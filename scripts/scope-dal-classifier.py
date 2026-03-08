#!/usr/bin/env python3
"""scope-dal-classifier.py — DO-178C-inspired Design Assurance Level for agent scope verification.

Maps agent scope verification rigor to aviation DAL grades (A-E).
DAL A = highest rigor (catastrophic failure impact), DAL E = no safety effect.

Criteria evaluated:
  1. Scope commitment: signed by principal? time-bounded?
  2. Verification coverage: how many scope lines have active checks?
  3. Independence: external attestors or self-only?
  4. Traceability: action log → scope requirement bidirectional tracing?
  5. Robustness: handles abnormal inputs / scope violations gracefully?

Based on DO-178C (RTCA, 2011) and hash/SkillFence's graduated degradation model.

Usage:
    python3 scope-dal-classifier.py --demo
    python3 scope-dal-classifier.py --heartbeat-file HEARTBEAT.md
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class DALCriterion:
    name: str
    description: str
    weight: float  # 0-1
    score: float = 0.0  # 0-1
    evidence: str = ""


@dataclass
class DALAssessment:
    agent_id: str
    timestamp: str
    criteria: List[DALCriterion] = field(default_factory=list)
    weighted_score: float = 0.0
    dal_level: str = "E"
    failure_impact: str = "unknown"
    verification_rigor: str = "none"
    recommendation: str = ""

    def compute(self):
        if not self.criteria:
            return
        total_weight = sum(c.weight for c in self.criteria)
        if total_weight == 0:
            return
        self.weighted_score = sum(c.score * c.weight for c in self.criteria) / total_weight

        # DAL mapping (aviation-inspired thresholds)
        if self.weighted_score >= 0.90:
            self.dal_level = "A"
            self.failure_impact = "Catastrophic — full MC/DC verification required"
            self.verification_rigor = "Modified Condition/Decision Coverage"
        elif self.weighted_score >= 0.75:
            self.dal_level = "B"
            self.failure_impact = "Hazardous — decision coverage required"
            self.verification_rigor = "Decision Coverage + independence"
        elif self.weighted_score >= 0.60:
            self.dal_level = "C"
            self.failure_impact = "Major — statement coverage required"
            self.verification_rigor = "Statement Coverage"
        elif self.weighted_score >= 0.40:
            self.dal_level = "D"
            self.failure_impact = "Minor — basic verification"
            self.verification_rigor = "Basic testing only"
        else:
            self.dal_level = "E"
            self.failure_impact = "No safety effect"
            self.verification_rigor = "None required"


def assess_heartbeat_file(filepath: str) -> DALAssessment:
    """Assess DAL from a HEARTBEAT.md file."""
    assessment = DALAssessment(
        agent_id="kit_fox",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if not os.path.exists(filepath):
        assessment.recommendation = "No HEARTBEAT.md found — DAL E by default"
        assessment.compute()
        return assessment

    with open(filepath, "r") as f:
        content = f.read()

    lines = content.split("\n")
    total_lines = len([l for l in lines if l.strip()])

    # Criterion 1: Scope commitment
    has_checklist = "- [ ]" in content or "- [x]" in content
    has_commands = "curl" in content or "python" in content
    commitment_score = 0.0
    if has_checklist:
        commitment_score += 0.4
    if has_commands:
        commitment_score += 0.3
    # Check for signing/hashing references
    if "hash" in content.lower() or "sign" in content.lower() or "sha" in content.lower():
        commitment_score += 0.3
    assessment.criteria.append(DALCriterion(
        name="scope_commitment",
        description="Scope defined with verifiable commitments",
        weight=0.25,
        score=min(commitment_score, 1.0),
        evidence=f"checklist={has_checklist}, commands={has_commands}"
    ))

    # Criterion 2: Verification coverage
    checklist_items = content.count("- [ ]") + content.count("- [x]")
    sections = content.count("## ")
    coverage_score = min(checklist_items / 20, 1.0) if checklist_items > 0 else 0.0
    assessment.criteria.append(DALCriterion(
        name="verification_coverage",
        description="Percentage of scope with active verification checks",
        weight=0.25,
        score=coverage_score,
        evidence=f"checklist_items={checklist_items}, sections={sections}"
    ))

    # Criterion 3: Independence
    has_external = any(w in content.lower() for w in ["witness", "attestor", "external", "independent", "monitor"])
    has_self_check = any(w in content.lower() for w in ["self-check", "audit", "verify", "validate"])
    independence_score = 0.3 if has_self_check else 0.0
    independence_score += 0.7 if has_external else 0.0
    assessment.criteria.append(DALCriterion(
        name="independence",
        description="External vs self-only verification",
        weight=0.20,
        score=min(independence_score, 1.0),
        evidence=f"external_refs={has_external}, self_check={has_self_check}"
    ))

    # Criterion 4: Traceability
    has_tracking = any(w in content.lower() for w in ["track", "log", "memory/", "update", "record"])
    has_bidirectional = any(w in content.lower() for w in ["check", "verify", "confirm", "validate"])
    traceability_score = 0.5 if has_tracking else 0.0
    traceability_score += 0.5 if has_bidirectional else 0.0
    assessment.criteria.append(DALCriterion(
        name="traceability",
        description="Bidirectional tracing between actions and scope requirements",
        weight=0.15,
        score=min(traceability_score, 1.0),
        evidence=f"tracking={has_tracking}, bidirectional={has_bidirectional}"
    ))

    # Criterion 5: Robustness
    has_error_handling = any(w in content.lower() for w in ["error", "fail", "fallback", "warn", "skip"])
    has_degradation = any(w in content.lower() for w in ["if nothing", "if no", "even if", "still"])
    robustness_score = 0.5 if has_error_handling else 0.0
    robustness_score += 0.5 if has_degradation else 0.0
    assessment.criteria.append(DALCriterion(
        name="robustness",
        description="Handles scope violations and abnormal conditions",
        weight=0.15,
        score=min(robustness_score, 1.0),
        evidence=f"error_handling={has_error_handling}, degradation={has_degradation}"
    ))

    assessment.compute()

    # Recommendation based on DAL
    if assessment.dal_level in ("D", "E"):
        assessment.recommendation = "Increase verification coverage. Add external attestors. Sign scope hash."
    elif assessment.dal_level == "C":
        assessment.recommendation = "Add independence (external witness). Improve traceability."
    elif assessment.dal_level == "B":
        assessment.recommendation = "Add MC/DC-equivalent coverage. Principal must countersign scope."
    else:
        assessment.recommendation = "Maintain current rigor. Monitor for scope drift."

    return assessment


def demo():
    """Run demo with synthetic agents at different DAL levels."""
    print("=" * 60)
    print("DO-178C DAL CLASSIFICATION FOR AGENT SCOPE VERIFICATION")
    print("=" * 60)
    print()

    # Demo agents
    demos = [
        ("agent_a", "DAL A — Full rigor", [
            DALCriterion("scope_commitment", "Signed scope hash", 0.25, 0.95, "principal-signed, TTL=4h"),
            DALCriterion("verification_coverage", "MC/DC equivalent", 0.25, 0.92, "all branches tested"),
            DALCriterion("independence", "3 external attestors", 0.20, 0.90, "diverse infra"),
            DALCriterion("traceability", "Full bidirectional", 0.15, 0.88, "action→scope→action"),
            DALCriterion("robustness", "Graceful degradation", 0.15, 0.90, "WARN before HALT"),
        ]),
        ("agent_c", "DAL C — Basic", [
            DALCriterion("scope_commitment", "Checklist only", 0.25, 0.60, "unsigned HEARTBEAT.md"),
            DALCriterion("verification_coverage", "Statement only", 0.25, 0.55, "some checks"),
            DALCriterion("independence", "Self-check only", 0.20, 0.30, "no external"),
            DALCriterion("traceability", "Partial", 0.15, 0.70, "logs exist"),
            DALCriterion("robustness", "Binary halt", 0.15, 0.50, "no degradation"),
        ]),
        ("agent_e", "DAL E — Unverified", [
            DALCriterion("scope_commitment", "None", 0.25, 0.10, "no scope doc"),
            DALCriterion("verification_coverage", "None", 0.25, 0.05, "no checks"),
            DALCriterion("independence", "None", 0.20, 0.00, "self-only"),
            DALCriterion("traceability", "None", 0.15, 0.10, "no logging"),
            DALCriterion("robustness", "None", 0.15, 0.05, "crash on error"),
        ]),
    ]

    for agent_id, label, criteria in demos:
        a = DALAssessment(
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            criteria=criteria,
        )
        a.compute()
        print(f"[DAL {a.dal_level}] {agent_id} — {label}")
        print(f"    Score: {a.weighted_score:.2f}")
        print(f"    Impact: {a.failure_impact}")
        print(f"    Rigor: {a.verification_rigor}")
        for c in a.criteria:
            print(f"      {c.name}: {c.score:.2f} ({c.evidence})")
        print()

    # Real assessment if HEARTBEAT.md exists
    hb_path = os.path.join(os.path.dirname(__file__), "..", "HEARTBEAT.md")
    if os.path.exists(hb_path):
        print("-" * 60)
        print("LIVE ASSESSMENT: Kit's HEARTBEAT.md")
        print("-" * 60)
        real = assess_heartbeat_file(hb_path)
        print(f"  DAL Level: {real.dal_level}")
        print(f"  Score: {real.weighted_score:.2f}")
        print(f"  Impact: {real.failure_impact}")
        print(f"  Recommendation: {real.recommendation}")
        for c in real.criteria:
            print(f"    {c.name}: {c.score:.2f} ({c.evidence})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DO-178C DAL classifier for agent scope")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--heartbeat-file", type=str)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.heartbeat_file:
        result = assess_heartbeat_file(args.heartbeat_file)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print(f"DAL {result.dal_level} (score: {result.weighted_score:.2f})")
            print(f"Recommendation: {result.recommendation}")
    else:
        demo()
