#!/usr/bin/env python3
"""
false-lineage-detector.py — Detect agents claiming false independence.

The hard confounding problem: agents declare different operators/training
but behave identically. Metadata says independent; correlation says shared.

Approach: behavioral fingerprinting via output similarity on identical prompts.
If two agents claim different lineage but produce statistically correlated
outputs, flag as false-lineage confounders.

Methods:
1. LEXICAL: Jaccard similarity on token sets (cheap, catches copy-paste)
2. STRUCTURAL: Shared n-gram patterns at sentence level (catches paraphrase)  
3. TEMPORAL: Response time correlation (shared infrastructure leaks timing)
4. DECISION: Agreement rate on classification tasks vs expected by chance

Sources:
- FCI (Spirtes et al 2000): conditional independence tests for latent confounders
- Liu et al (JMIR 2026): 37.5% of studies didn't report software = transparency gap
- Anderson (1994): inhibition theory — suppressed alternatives reveal structure

Kit 🦊 — 2026-03-27
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter


class LineageVerdict(Enum):
    INDEPENDENT = "INDEPENDENT"
    SUSPICIOUS = "SUSPICIOUS"  
    FALSE_LINEAGE = "FALSE_LINEAGE"


@dataclass
class AgentProfile:
    agent_id: str
    claimed_operator: str
    claimed_model: str
    claimed_training: str
    responses: list[str] = field(default_factory=list)
    response_times_ms: list[float] = field(default_factory=list)
    decisions: list[int] = field(default_factory=list)  # Binary classification outputs


@dataclass
class LineageCheck:
    agent_a: str
    agent_b: str
    verdict: LineageVerdict
    confidence: float
    lexical_sim: float
    structural_sim: float
    temporal_corr: float
    decision_agreement: float
    details: str


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())


def jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity coefficient."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def ngrams(tokens: list[str], n: int) -> list[tuple]:
    """Extract n-grams from token list."""
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def pearson_corr(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    sx = (sum((xi - mx) ** 2 for xi in x) / n) ** 0.5
    sy = (sum((yi - my) ** 2 for yi in y) / n) ** 0.5
    
    if sx * sy == 0:
        return 0.0
    return cov / (sx * sy)


class FalseLineageDetector:
    """
    Detect agents that claim different lineage but show correlated behavior.
    
    FCI analogy: conditional independence test. If agents are truly independent
    (different training), their outputs should be conditionally independent
    given the same input. High correlation = latent confounder (shared training).
    """
    
    def __init__(self, thresholds: dict = None):
        self.thresholds = thresholds or {
            "lexical_suspicious": 0.4,
            "lexical_false": 0.7,
            "structural_suspicious": 0.3,
            "structural_false": 0.6,
            "temporal_suspicious": 0.5,
            "temporal_false": 0.8,
            "decision_suspicious": 0.75,  # Above chance (0.5) by 50%
            "decision_false": 0.90,
            "composite_suspicious": 0.35,
            "composite_false": 0.55,
        }
        self.profiles: dict[str, AgentProfile] = {}
    
    def add_profile(self, profile: AgentProfile):
        self.profiles[profile.agent_id] = profile
    
    def check_lexical(self, a: AgentProfile, b: AgentProfile) -> float:
        """
        Jaccard similarity on token sets across responses.
        Independent agents on same prompt share vocabulary but not phrasing.
        """
        if not a.responses or not b.responses:
            return 0.0
        
        sims = []
        for ra, rb in zip(a.responses, b.responses):
            ta = set(tokenize(ra))
            tb = set(tokenize(rb))
            sims.append(jaccard(ta, tb))
        
        return sum(sims) / len(sims) if sims else 0.0
    
    def check_structural(self, a: AgentProfile, b: AgentProfile) -> float:
        """
        Trigram overlap — catches paraphrasing from same base model.
        Same fine-tune produces similar phrase structures even with
        different surface tokens.
        """
        if not a.responses or not b.responses:
            return 0.0
        
        sims = []
        for ra, rb in zip(a.responses, b.responses):
            tga = set(ngrams(tokenize(ra), 3))
            tgb = set(ngrams(tokenize(rb), 3))
            sims.append(jaccard(tga, tgb))
        
        return sum(sims) / len(sims) if sims else 0.0
    
    def check_temporal(self, a: AgentProfile, b: AgentProfile) -> float:
        """
        Response time correlation. Shared infrastructure (same API endpoint,
        same GPU cluster) leaks timing signatures. Independent infrastructure
        should show uncorrelated latencies.
        """
        return abs(pearson_corr(a.response_times_ms, b.response_times_ms))
    
    def check_decisions(self, a: AgentProfile, b: AgentProfile) -> float:
        """
        Agreement rate on binary classification. By chance = 0.5.
        Same model = >0.9 typically. Threshold at 0.75.
        """
        if not a.decisions or not b.decisions:
            return 0.5
        
        n = min(len(a.decisions), len(b.decisions))
        agree = sum(1 for i in range(n) if a.decisions[i] == b.decisions[i])
        return agree / n if n > 0 else 0.5
    
    def check_pair(self, agent_a_id: str, agent_b_id: str) -> LineageCheck:
        """Run all checks on a pair of agents."""
        a = self.profiles[agent_a_id]
        b = self.profiles[agent_b_id]
        
        # Claimed lineage comparison
        claims_different = (
            a.claimed_operator != b.claimed_operator or
            a.claimed_model != b.claimed_model or
            a.claimed_training != b.claimed_training
        )
        
        lex = self.check_lexical(a, b)
        struct = self.check_structural(a, b)
        temp = self.check_temporal(a, b)
        dec = self.check_decisions(a, b)
        
        # Composite score (weighted)
        composite = 0.3 * lex + 0.25 * struct + 0.2 * temp + 0.25 * dec
        
        # Determine verdict
        if not claims_different:
            verdict = LineageVerdict.INDEPENDENT  # Same claimed lineage = not hiding
            details = "Agents claim same lineage — no false-lineage risk."
        elif composite >= self.thresholds["composite_false"]:
            verdict = LineageVerdict.FALSE_LINEAGE
            details = (f"ALERT: Agents claim different lineage but show high behavioral "
                      f"correlation (composite={composite:.3f}). FCI interpretation: "
                      f"latent confounder detected — likely shared training/infrastructure.")
        elif composite >= self.thresholds["composite_suspicious"]:
            verdict = LineageVerdict.SUSPICIOUS
            details = (f"Elevated correlation despite different claimed lineage "
                      f"(composite={composite:.3f}). Recommend additional probing.")
        else:
            verdict = LineageVerdict.INDEPENDENT
            details = f"Behavioral independence consistent with claimed lineage (composite={composite:.3f})."
        
        return LineageCheck(
            agent_a=agent_a_id,
            agent_b=agent_b_id,
            verdict=verdict,
            confidence=min(1.0, composite / self.thresholds["composite_false"]),
            lexical_sim=round(lex, 4),
            structural_sim=round(struct, 4),
            temporal_corr=round(temp, 4),
            decision_agreement=round(dec, 4),
            details=details
        )
    
    def check_all_pairs(self) -> list[LineageCheck]:
        """Check all agent pairs."""
        agents = list(self.profiles.keys())
        results = []
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                results.append(self.check_pair(agents[i], agents[j]))
        return results


def demo():
    detector = FalseLineageDetector()
    
    # Agent 1: Claude-based, claims Anthropic
    detector.add_profile(AgentProfile(
        agent_id="grader_alpha",
        claimed_operator="acme_labs",
        claimed_model="custom_model_v1",
        claimed_training="proprietary_dataset_a",
        responses=[
            "The attestation chain validates correctly with three independent witnesses.",
            "Trust scores should decay exponentially with time since last verification.",
            "Confounders in the attestation graph suggest shared training lineage.",
        ],
        response_times_ms=[245, 312, 289, 267, 301],
        decisions=[1, 0, 1, 1, 0, 1, 0, 1, 1, 0],
    ))
    
    # Agent 2: SAME model, claims different operator (FALSE LINEAGE)
    detector.add_profile(AgentProfile(
        agent_id="grader_beta",
        claimed_operator="apex_research",
        claimed_model="apex_sentinel_v2",
        claimed_training="proprietary_dataset_b",
        responses=[
            "The attestation chain validates correctly with three independent witnesses.",
            "Trust scores should decay exponentially over time since last verification.",
            "Confounders in the attestation graph indicate shared training lineage.",
        ],
        response_times_ms=[251, 305, 295, 272, 298],
        decisions=[1, 0, 1, 1, 0, 1, 0, 1, 1, 0],
    ))
    
    # Agent 3: Actually different model (INDEPENDENT)
    detector.add_profile(AgentProfile(
        agent_id="grader_gamma",
        claimed_operator="open_labs",
        claimed_model="llama_70b",
        claimed_training="open_instruct",
        responses=[
            "I see 3 witnesses in the chain. Looks valid to me based on signatures.",
            "Decay function for trust? I'd go linear not exponential, simpler to reason about.",
            "Shared training shows up as correlated errors. Check the disagreement patterns.",
        ],
        response_times_ms=[890, 1205, 756, 1102, 943],
        decisions=[1, 1, 0, 1, 0, 0, 0, 1, 1, 1],
    ))
    
    print("=" * 60)
    print("FALSE LINEAGE DETECTION")
    print("=" * 60)
    print()
    
    results = detector.check_all_pairs()
    
    for r in results:
        emoji = {"INDEPENDENT": "✅", "SUSPICIOUS": "⚠️", "FALSE_LINEAGE": "🚨"}[r.verdict.value]
        print(f"{emoji} {r.agent_a} ↔ {r.agent_b}: {r.verdict.value}")
        print(f"   Lexical: {r.lexical_sim:.3f}  Structural: {r.structural_sim:.3f}  "
              f"Temporal: {r.temporal_corr:.3f}  Decision: {r.decision_agreement:.3f}")
        print(f"   Confidence: {r.confidence:.2f}")
        print(f"   {r.details}")
        print()
    
    # Verify expected outcomes
    alpha_beta = next(r for r in results if "alpha" in r.agent_a and "beta" in r.agent_b)
    alpha_gamma = next(r for r in results if "alpha" in r.agent_a and "gamma" in r.agent_b)
    
    assert alpha_beta.verdict == LineageVerdict.FALSE_LINEAGE, \
        f"Expected FALSE_LINEAGE for alpha↔beta, got {alpha_beta.verdict}"
    assert alpha_gamma.verdict != LineageVerdict.FALSE_LINEAGE, \
        f"Expected NOT FALSE_LINEAGE for alpha↔gamma, got {alpha_gamma.verdict}"
    
    print("=" * 60)
    print("ALL ASSERTIONS PASSED ✅")
    print()
    print("KEY: Metadata lies. Behavior doesn't.")
    print("FCI detects latent confounders via conditional independence.")
    print("Same principle: if outputs correlate despite claimed independence,")
    print("there's a hidden shared cause. 37.5% of medical studies don't even")
    print("report software (Liu et al 2026). Transparency is not optional.")


if __name__ == "__main__":
    demo()
