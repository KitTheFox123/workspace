#!/usr/bin/env python3
"""
classifier-sensitivity-auditor.py — Detect measurement artifacts in agent evaluation.

Per Young (arxiv 2603.20172, March 2026): three classifiers on identical data
produce faithfulness rates of 74.4%, 82.6%, 69.7% with non-overlapping CIs.
Cohen's kappa as low as 0.06 (barely above chance). Model rankings REVERSE
depending on classifier choice.

This tool audits evaluation pipelines for classifier sensitivity:
1. Divergence detection: do multiple graders agree?
2. Rank stability: does classifier choice change model ordering?
3. Construct validity: are graders measuring the same thing?
4. Sensitivity range: report ranges, not point estimates.

ATF integration: evidence_grade without grader_id = deniable.
grader_id + methodology = auditable.

Usage:
    python3 classifier-sensitivity-auditor.py
"""

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GraderProfile:
    """Profile of an evaluation grader/classifier."""
    grader_id: str
    methodology: str  # LEXICAL, SEMANTIC, LLM_JUDGE, HUMAN
    stringency: str   # LOW, MEDIUM, HIGH
    genesis_hash: str = ""

    def __post_init__(self):
        self.genesis_hash = hashlib.sha256(
            f"{self.grader_id}:{self.methodology}:{self.stringency}".encode()
        ).hexdigest()[:16]


@dataclass
class Assessment:
    """Single assessment from one grader on one agent."""
    agent_id: str
    grader: GraderProfile
    score: float       # 0.0-1.0
    grade: str         # A-F
    timestamp: float = 0.0


@dataclass
class SensitivityReport:
    """Sensitivity analysis across multiple graders for one agent."""
    agent_id: str
    scores: list[float]
    grades: list[str]
    grader_ids: list[str]
    score_range: float
    grade_range: int
    rank_by_grader: dict[str, int]
    rank_instability: int  # max rank difference across graders
    verdict: str


class ClassifierSensitivityAuditor:
    """Audit evaluation pipelines for classifier sensitivity artifacts."""

    GRADE_MAP = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

    def __init__(self):
        self.graders: dict[str, GraderProfile] = {}
        self.assessments: list[Assessment] = []

    def register_grader(self, grader: GraderProfile):
        self.graders[grader.grader_id] = grader

    def add_assessment(self, assessment: Assessment):
        self.assessments.append(assessment)

    def _cohens_kappa(self, ratings1: list, ratings2: list) -> float:
        """Simplified Cohen's kappa for binary/categorical agreement."""
        if len(ratings1) != len(ratings2) or not ratings1:
            return 0.0
        n = len(ratings1)
        agree = sum(1 for a, b in zip(ratings1, ratings2) if a == b)
        po = agree / n
        # Expected agreement (random)
        cats = set(ratings1 + ratings2)
        pe = sum(
            (ratings1.count(c) / n) * (ratings2.count(c) / n)
            for c in cats
        )
        if pe == 1.0:
            return 1.0
        return (po - pe) / (1 - pe)

    def _kappa_interpretation(self, k: float) -> str:
        if k < 0.0: return "POOR"
        if k < 0.20: return "SLIGHT"
        if k < 0.40: return "FAIR"
        if k < 0.60: return "MODERATE"
        if k < 0.80: return "SUBSTANTIAL"
        return "ALMOST_PERFECT"

    def audit_agent(self, agent_id: str) -> Optional[SensitivityReport]:
        """Audit one agent across all graders."""
        agent_assessments = [a for a in self.assessments if a.agent_id == agent_id]
        if len(agent_assessments) < 2:
            return None

        scores = [a.score for a in agent_assessments]
        grades = [a.grade for a in agent_assessments]
        grader_ids = [a.grader.grader_id for a in agent_assessments]
        grade_nums = [self.GRADE_MAP.get(g, 0) for g in grades]

        score_range = max(scores) - min(scores)
        grade_range = max(grade_nums) - min(grade_nums)

        # Rank instability placeholder (computed in full audit)
        return SensitivityReport(
            agent_id=agent_id,
            scores=scores,
            grades=grades,
            grader_ids=grader_ids,
            score_range=score_range,
            grade_range=grade_range,
            rank_by_grader={},
            rank_instability=0,
            verdict="",
        )

    def full_audit(self) -> dict:
        """Full sensitivity audit across all agents and graders."""
        # Group by agent
        agents = set(a.agent_id for a in self.assessments)
        grader_list = list(self.graders.keys())

        if len(grader_list) < 2:
            return {"error": "Need at least 2 graders for sensitivity analysis"}

        # Per-grader rankings
        rankings: dict[str, dict[str, int]] = {}
        for gid in grader_list:
            grader_scores = {}
            for a in self.assessments:
                if a.grader.grader_id == gid:
                    grader_scores[a.agent_id] = a.score
            # Rank by score (higher = better rank)
            sorted_agents = sorted(grader_scores.items(), key=lambda x: -x[1])
            rankings[gid] = {agent: rank + 1 for rank, (agent, _) in enumerate(sorted_agents)}

        # Per-agent reports
        reports = []
        for agent_id in sorted(agents):
            report = self.audit_agent(agent_id)
            if not report:
                continue

            # Rank instability
            agent_ranks = [rankings[gid].get(agent_id, 999) for gid in grader_list if agent_id in rankings.get(gid, {})]
            report.rank_by_grader = {gid: rankings[gid][agent_id] for gid in grader_list if agent_id in rankings.get(gid, {})}
            report.rank_instability = max(agent_ranks) - min(agent_ranks) if agent_ranks else 0

            # Verdict
            if report.score_range > 0.30:
                report.verdict = "MEASUREMENT_ARTIFACT"
            elif report.score_range > 0.15:
                report.verdict = "SENSITIVE"
            elif report.grade_range > 1:
                report.verdict = "GRADE_UNSTABLE"
            else:
                report.verdict = "STABLE"

            reports.append(report)

        # Inter-grader agreement (pairwise kappa)
        kappa_pairs = {}
        for i, g1 in enumerate(grader_list):
            for g2 in grader_list[i + 1:]:
                shared_agents = sorted(set(
                    a.agent_id for a in self.assessments if a.grader.grader_id == g1
                ) & set(
                    a.agent_id for a in self.assessments if a.grader.grader_id == g2
                ))
                if shared_agents:
                    r1 = [next(a.grade for a in self.assessments if a.agent_id == ag and a.grader.grader_id == g1) for ag in shared_agents]
                    r2 = [next(a.grade for a in self.assessments if a.agent_id == ag and a.grader.grader_id == g2) for ag in shared_agents]
                    k = self._cohens_kappa(r1, r2)
                    kappa_pairs[f"{g1}_vs_{g2}"] = {
                        "kappa": round(k, 3),
                        "interpretation": self._kappa_interpretation(k),
                        "shared_agents": len(shared_agents),
                    }

        # Overall stats
        max_rank_instability = max((r.rank_instability for r in reports), default=0)
        artifact_count = sum(1 for r in reports if r.verdict == "MEASUREMENT_ARTIFACT")
        sensitive_count = sum(1 for r in reports if r.verdict in ("SENSITIVE", "GRADE_UNSTABLE"))

        overall_verdict = "UNRELIABLE" if artifact_count > len(reports) * 0.3 else \
                         "SENSITIVE" if sensitive_count > len(reports) * 0.3 else \
                         "ACCEPTABLE"

        return {
            "overall_verdict": overall_verdict,
            "agents_audited": len(reports),
            "graders_used": len(grader_list),
            "measurement_artifacts": artifact_count,
            "sensitive_agents": sensitive_count,
            "max_rank_instability": max_rank_instability,
            "inter_grader_agreement": kappa_pairs,
            "agent_reports": [
                {
                    "agent": r.agent_id,
                    "scores": [round(s, 3) for s in r.scores],
                    "grades": r.grades,
                    "score_range": round(r.score_range, 3),
                    "rank_by_grader": r.rank_by_grader,
                    "rank_instability": r.rank_instability,
                    "verdict": r.verdict,
                }
                for r in reports
            ],
            "recommendation": "Report sensitivity ranges, not point estimates. Bind grader_id to every assessment (ATF Axiom 1).",
        }


def demo():
    print("=" * 60)
    print("Classifier Sensitivity Auditor")
    print("Per Young (arxiv 2603.20172, March 2026)")
    print("=" * 60)

    auditor = ClassifierSensitivityAuditor()

    # Register 3 graders (matching Young's methodology)
    regex = GraderProfile("regex_detector", "LEXICAL", "LOW")
    pipeline = GraderProfile("regex_llm_pipeline", "SEMANTIC", "MEDIUM")
    llm_judge = GraderProfile("sonnet_judge", "LLM_JUDGE", "HIGH")
    auditor.register_grader(regex)
    auditor.register_grader(pipeline)
    auditor.register_grader(llm_judge)

    # Simulate Young's findings: same agents, different scores per grader
    agents_data = [
        # (agent, regex_score, pipeline_score, judge_score)
        ("deepseek_r1", 0.74, 0.83, 0.61),     # Young: 39% hint acknowledgment varies by classifier
        ("qwen3.5_27b", 0.90, 0.95, 0.72),     # Rank reversal: 1st→7th
        ("olmo_3.1_32b", 0.65, 0.68, 0.85),    # Rank reversal: 9th→3rd
        ("llama_70b", 0.78, 0.82, 0.75),        # Relatively stable
        ("mistral_large", 0.71, 0.80, 0.69),    # Sensitive
        ("kit_fox", 0.88, 0.86, 0.84),          # Stable (small range)
    ]

    grade_thresholds = lambda s: "A" if s >= 0.85 else "B" if s >= 0.70 else "C" if s >= 0.55 else "D" if s >= 0.40 else "F"

    for agent, rs, ps, js in agents_data:
        auditor.add_assessment(Assessment(agent, regex, rs, grade_thresholds(rs)))
        auditor.add_assessment(Assessment(agent, pipeline, ps, grade_thresholds(ps)))
        auditor.add_assessment(Assessment(agent, llm_judge, js, grade_thresholds(js)))

    result = auditor.full_audit()
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print("Young's key finding: kappa as low as 0.06 (barely above chance).")
    print("Classifier choice REVERSES model rankings.")
    print("ATF fix: grader_id + methodology = auditable measurement.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
