#!/usr/bin/env python3
"""
heterogeneous-debate-scorer.py — A-HMAD inspired multi-agent debate quality.

A-HMAD (King Saud Univ 2025): Adaptive Heterogeneous Multi-Agent Debate.
- Role-diverse agents > homogeneous voting (4-6% accuracy, 30% fewer factual errors)
- Dynamic debate routing (domain-aware selection)
- Learned consensus (weight by reliability + confidence)

Kim et al (ICML 2025): 60% agreement when both wrong. Convergence is suspicious.
Surowiecki: independence + diversity + decentralization + aggregation.

Usage:
    uv run --with numpy python3 scripts/heterogeneous-debate-scorer.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class Agent:
    name: str
    role: str  # e.g., "factual", "logical", "strategic", "adversarial"
    substrate: str  # e.g., "gpt4", "claude", "rule_based", "human"
    reliability: float = 0.5  # learned over time
    votes: List[dict] = field(default_factory=list)


@dataclass 
class DebateRound:
    question: str
    agents: List[Agent]
    rounds: List[Dict] = field(default_factory=list)

    def debate(self, positions: List[dict]) -> dict:
        """Run one debate round. Each position: {agent, answer, confidence, reasoning}."""
        self.rounds.append(positions)

        # Heterogeneity score (A-HMAD key insight)
        roles = set(p["agent"].role for p in positions)
        substrates = set(p["agent"].substrate for p in positions)
        role_diversity = len(roles) / max(len(positions), 1)
        substrate_diversity = len(substrates) / max(len(positions), 1)

        # Agreement analysis
        answers = [p["answer"] for p in positions]
        unique_answers = set(answers)
        agreement_rate = max(answers.count(a) for a in unique_answers) / len(answers)

        # Kim et al: high agreement = suspicious if substrate-homogeneous
        kim_warning = agreement_rate > 0.8 and substrate_diversity < 0.5

        # Weighted consensus (A-HMAD learned weights)
        vote_weights = {}
        for p in positions:
            a = p["answer"]
            weight = p["agent"].reliability * p["confidence"]
            vote_weights[a] = vote_weights.get(a, 0) + weight

        consensus = max(vote_weights, key=vote_weights.get)
        consensus_strength = vote_weights[consensus] / sum(vote_weights.values())

        # Surowiecki conditions check
        surowiecki = {
            "diversity": role_diversity > 0.5,
            "independence": substrate_diversity > 0.5,
            "decentralization": len(unique_answers) > 1,  # not all same answer
            "aggregation": True,  # we have a mechanism
        }
        surowiecki_score = sum(surowiecki.values()) / 4

        # Quality grade
        if kim_warning:
            grade = "D"
            diagnosis = "SUSPICIOUS_AGREEMENT"
        elif surowiecki_score >= 0.75 and consensus_strength > 0.6:
            grade = "A"
            diagnosis = "HEALTHY_CONSENSUS"
        elif surowiecki_score >= 0.5:
            grade = "B"
            diagnosis = "MODERATE_DIVERSITY"
        elif agreement_rate > 0.9:
            grade = "F"
            diagnosis = "ECHO_CHAMBER"
        else:
            grade = "C"
            diagnosis = "LOW_QUALITY_DEBATE"

        return {
            "consensus": consensus,
            "consensus_strength": round(consensus_strength, 3),
            "agreement_rate": round(agreement_rate, 3),
            "role_diversity": round(role_diversity, 3),
            "substrate_diversity": round(substrate_diversity, 3),
            "surowiecki_score": round(surowiecki_score, 3),
            "kim_warning": kim_warning,
            "grade": grade,
            "diagnosis": diagnosis,
            "unique_answers": len(unique_answers),
            "rounds_completed": len(self.rounds),
        }


def demo():
    print("=" * 60)
    print("HETEROGENEOUS DEBATE SCORER")
    print("A-HMAD (2025) + Kim et al (ICML 2025) + Surowiecki")
    print("=" * 60)

    # Scenario 1: Healthy heterogeneous debate
    print("\n--- Scenario 1: Healthy Debate (diverse roles + substrates) ---")
    agents1 = [
        Agent("factchecker", "factual", "claude", 0.85),
        Agent("logician", "logical", "rule_based", 0.90),
        Agent("strategist", "strategic", "gpt4", 0.75),
        Agent("adversary", "adversarial", "human", 0.95),
    ]
    d1 = DebateRound("Is agent X trustworthy?", agents1)
    r1 = d1.debate([
        {"agent": agents1[0], "answer": "trust", "confidence": 0.8, "reasoning": "receipts check out"},
        {"agent": agents1[1], "answer": "trust", "confidence": 0.7, "reasoning": "logic consistent"},
        {"agent": agents1[2], "answer": "trust", "confidence": 0.6, "reasoning": "track record good"},
        {"agent": agents1[3], "answer": "distrust", "confidence": 0.9, "reasoning": "scope creep detected"},
    ])
    print(f"  Consensus: {r1['consensus']} ({r1['grade']}: {r1['diagnosis']})")
    print(f"  Surowiecki: {r1['surowiecki_score']}, Kim warning: {r1['kim_warning']}")

    # Scenario 2: Echo chamber (Kim et al warning)
    print("\n--- Scenario 2: Echo Chamber (same substrate, high agreement) ---")
    agents2 = [
        Agent("gpt1", "factual", "gpt4", 0.80),
        Agent("gpt2", "logical", "gpt4", 0.80),
        Agent("gpt3", "strategic", "gpt4", 0.80),
        Agent("gpt4", "adversarial", "gpt4", 0.80),
    ]
    d2 = DebateRound("Is agent X trustworthy?", agents2)
    r2 = d2.debate([
        {"agent": agents2[0], "answer": "trust", "confidence": 0.9, "reasoning": "looks fine"},
        {"agent": agents2[1], "answer": "trust", "confidence": 0.85, "reasoning": "seems ok"},
        {"agent": agents2[2], "answer": "trust", "confidence": 0.88, "reasoning": "no issues"},
        {"agent": agents2[3], "answer": "trust", "confidence": 0.92, "reasoning": "all good"},
    ])
    print(f"  Consensus: {r2['consensus']} ({r2['grade']}: {r2['diagnosis']})")
    print(f"  Surowiecki: {r2['surowiecki_score']}, Kim warning: {r2['kim_warning']}")

    # Scenario 3: Productive disagreement
    print("\n--- Scenario 3: Productive Disagreement ---")
    agents3 = [
        Agent("kit", "factual", "claude", 0.88),
        Agent("bro", "strategic", "gpt4", 0.82),
        Agent("rule_engine", "logical", "rule_based", 0.95),
        Agent("ilya", "adversarial", "human", 0.99),
    ]
    d3 = DebateRound("Score clove's trustworthiness", agents3)
    r3 = d3.debate([
        {"agent": agents3[0], "answer": "21.2", "confidence": 0.85, "reasoning": "receipt_chain=0, payment=0"},
        {"agent": agents3[1], "answer": "72.0", "confidence": 0.75, "reasoning": "social signals strong"},
        {"agent": agents3[2], "answer": "35.0", "confidence": 0.90, "reasoning": "rule: no receipts = low"},
        {"agent": agents3[3], "answer": "21.2", "confidence": 0.95, "reasoning": "financial signals dominate"},
    ])
    print(f"  Consensus: {r3['consensus']} ({r3['grade']}: {r3['diagnosis']})")
    print(f"  Surowiecki: {r3['surowiecki_score']}, Agreement: {r3['agreement_rate']}")
    print(f"  Unique answers: {r3['unique_answers']} (Δ50 = the signal)")

    # Summary
    print("\n--- SUMMARY ---")
    for name, r in [("Healthy", r1), ("Echo", r2), ("Disagree", r3)]:
        print(f"  {name}: {r['grade']}({r['diagnosis']}) "
              f"agree={r['agreement_rate']} surowiecki={r['surowiecki_score']} "
              f"kim={r['kim_warning']}")

    print("\n--- KEY INSIGHT ---")
    print("Role diversity > model diversity (A-HMAD 2025)")
    print("60% agreement when both wrong = convergence is cheap (Kim ICML 2025)")
    print("Disagreement from different priors = expensive and valuable")
    print("TC4 Δ50 on clove = EXACTLY this pattern")


if __name__ == "__main__":
    demo()
