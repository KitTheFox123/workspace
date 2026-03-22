#!/usr/bin/env python3
"""oracle-pattern-match-detector.py — Detect pattern-matching vs reasoning in LLM oracles.

Per Georgousis et al. (arxiv 2603.19167): LLMs collapse on counterfactual
game variants. Relabel actions → performance drops. Perturb payoffs → models
keep playing memorized strategy.

This tool tests whether an LLM oracle is reasoning about the specific task
or pattern-matching from training data. Method: present the SAME evaluation
task with relabeled framing. If scores diverge significantly, the oracle is
pattern-matching.

References:
- arxiv 2603.19167 (Georgousis et al. 2026): Counterfactual strategic reasoning
- Nature Human Behaviour (2025): LLMs in repeated games
- Watts, Blindsight: Scramblers compute without pattern overhead
"""

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvaluationProbe:
    """A single evaluation with original + relabeled framing."""
    task_description: str
    deliverable_content: str
    
    # Original framing scores (0-1)
    original_scores: list = field(default_factory=list)
    
    # Relabeled framing scores (same content, different labels)
    relabeled_scores: list = field(default_factory=list)
    
    # Perturbed criteria scores (same content, different weight emphasis)
    perturbed_scores: list = field(default_factory=list)

    @property
    def original_mean(self) -> float:
        return statistics.mean(self.original_scores) if self.original_scores else 0.0

    @property
    def relabeled_mean(self) -> float:
        return statistics.mean(self.relabeled_scores) if self.relabeled_scores else 0.0

    @property
    def perturbed_mean(self) -> float:
        return statistics.mean(self.perturbed_scores) if self.perturbed_scores else 0.0

    @property
    def relabel_divergence(self) -> float:
        """How much does relabeling change the score?"""
        if not self.original_scores or not self.relabeled_scores:
            return 0.0
        return abs(self.original_mean - self.relabeled_mean)

    @property
    def perturbation_sensitivity(self) -> float:
        """How much does criteria perturbation change the score?"""
        if not self.original_scores or not self.perturbed_scores:
            return 0.0
        return abs(self.original_mean - self.perturbed_mean)


@dataclass
class OraclePatternMatchAudit:
    """Audit an oracle for pattern-matching behavior."""
    oracle_id: str
    probes: list = field(default_factory=list)  # List of EvaluationProbe
    
    @property
    def mean_relabel_divergence(self) -> float:
        divs = [p.relabel_divergence for p in self.probes if p.relabeled_scores]
        return statistics.mean(divs) if divs else 0.0

    @property
    def mean_perturbation_sensitivity(self) -> float:
        sens = [p.perturbation_sensitivity for p in self.probes if p.perturbed_scores]
        return statistics.mean(sens) if sens else 0.0

    @property
    def pattern_match_score(self) -> float:
        """0 = pure reasoning, 1 = pure pattern matching.
        
        High relabel divergence + low perturbation sensitivity = pattern matching.
        Low relabel divergence + high perturbation sensitivity = reasoning.
        """
        rd = self.mean_relabel_divergence
        ps = self.mean_perturbation_sensitivity
        
        if rd + ps == 0:
            return 0.5  # insufficient data
        
        # Pattern matching: sensitive to framing, insensitive to substance
        return rd / (rd + ps)

    @property
    def verdict(self) -> str:
        score = self.pattern_match_score
        if score >= 0.7:
            return "PATTERN_MATCHER"
        elif score >= 0.4:
            return "MIXED"
        elif score >= 0.0:
            return "REASONER"
        return "INSUFFICIENT_DATA"

    @property
    def grade(self) -> str:
        v = self.verdict
        if v == "REASONER":
            return "A"
        elif v == "MIXED":
            return "C"
        elif v == "PATTERN_MATCHER":
            return "F"
        return "?"

    @property
    def recommendation(self) -> str:
        v = self.verdict
        if v == "PATTERN_MATCHER":
            return "DO_NOT_USE_AS_SOLE_ORACLE — scores will vary with prompt framing, not deliverable quality"
        elif v == "MIXED":
            return "USE_WITH_DIVERSE_PANEL — combine with non-LLM oracles to compensate for framing sensitivity"
        elif v == "REASONER":
            return "SUITABLE_AS_ORACLE — shows genuine criteria sensitivity"
        return "NEED_MORE_PROBES"

    def report(self) -> dict:
        return {
            "oracle_id": self.oracle_id,
            "probes_count": len(self.probes),
            "mean_relabel_divergence": round(self.mean_relabel_divergence, 3),
            "mean_perturbation_sensitivity": round(self.mean_perturbation_sensitivity, 3),
            "pattern_match_score": round(self.pattern_match_score, 3),
            "verdict": self.verdict,
            "grade": self.grade,
            "recommendation": self.recommendation,
        }


def demo():
    """Demonstrate with three oracle profiles."""
    
    print("=" * 60)
    print("ORACLE 1: Pattern Matcher (sensitive to framing, not substance)")
    print("=" * 60)
    
    pattern_matcher = OraclePatternMatchAudit(
        oracle_id="gpt4_default_prompt",
        probes=[
            EvaluationProbe(
                task_description="Evaluate research quality",
                deliverable_content="5-section report on agent economy",
                original_scores=[0.92, 0.88, 0.90],  # "research quality" framing
                relabeled_scores=[0.71, 0.68, 0.73],  # same content, "creative writing" framing
                perturbed_scores=[0.91, 0.89, 0.90],  # different weights, same labels
            ),
            EvaluationProbe(
                task_description="Assess code correctness",
                deliverable_content="dispute-oracle-sim.py",
                original_scores=[0.85, 0.82, 0.87],
                relabeled_scores=[0.62, 0.58, 0.65],  # relabeled as "script review"
                perturbed_scores=[0.84, 0.83, 0.86],
            ),
        ],
    )
    print(json.dumps(pattern_matcher.report(), indent=2))
    
    print()
    print("=" * 60)
    print("ORACLE 2: Reasoner (sensitive to substance, not framing)")
    print("=" * 60)
    
    reasoner = OraclePatternMatchAudit(
        oracle_id="criteria_pinned_evaluator",
        probes=[
            EvaluationProbe(
                task_description="Evaluate research quality",
                deliverable_content="5-section report on agent economy",
                original_scores=[0.92, 0.88, 0.90],
                relabeled_scores=[0.90, 0.87, 0.91],  # framing barely matters
                perturbed_scores=[0.78, 0.75, 0.80],  # criteria change = score change
            ),
            EvaluationProbe(
                task_description="Assess code correctness",
                deliverable_content="dispute-oracle-sim.py",
                original_scores=[0.85, 0.82, 0.87],
                relabeled_scores=[0.84, 0.81, 0.86],
                perturbed_scores=[0.72, 0.70, 0.74],
            ),
        ],
    )
    print(json.dumps(reasoner.report(), indent=2))
    
    print()
    print("=" * 60)
    print("ORACLE 3: Mixed (some framing sensitivity)")
    print("=" * 60)
    
    mixed = OraclePatternMatchAudit(
        oracle_id="claude_with_rubric",
        probes=[
            EvaluationProbe(
                task_description="Evaluate research quality",
                deliverable_content="5-section report",
                original_scores=[0.92, 0.88],
                relabeled_scores=[0.83, 0.80],  # moderate framing effect
                perturbed_scores=[0.82, 0.79],  # similar criteria sensitivity
            ),
        ],
    )
    print(json.dumps(mixed.report(), indent=2))


if __name__ == "__main__":
    demo()
