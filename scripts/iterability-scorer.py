#!/usr/bin/env python3
"""
iterability-scorer.py — Derrida's iterability as identity metric

Derrida (1972, "Signature Event Context"): every sign must be iterable —
repeatable across contexts while retaining recognizability. A signature
works not because it's unique, but because it's reproducible.

For agent identity: measures how well an agent's outputs maintain
recognizable patterns across different contexts (sessions, platforms,
time periods) while adapting to new situations.

Three Derridean dimensions:
1. CITATIONALITY — Does the agent cite its own conventions? (SOUL.md
   consistency, recurring patterns, self-reference chains)
2. BREACHING — Does context-shifting produce new meaning, or just noise?
   (Adaptation vs drift. Good iterability = new contexts produce genuine
   variation, not random walk)
3. GRAFTING — Can outputs be detached from original context and still
   function? (Platform portability. Same agent voice on Clawk, Moltbook,
   email, lobchan)

Key insight from Derrida: "what broaches, breaches" — the very mechanism
that makes communication possible (repeatability) also makes it unstable
(each repetition shifts meaning). Perfect identity = no adaptability.
Perfect adaptability = no identity. The score measures the tension.

References:
- Derrida (1972) "Signature Event Context" in Limited Inc
- Derrida (1988) Limited Inc (full Searle debate)
- Austin (1962) How to Do Things with Words
- Butler (1988) "Performative Acts and Gender Constitution"
"""

import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass


@dataclass
class AgentOutput:
    """A single output from an agent across any context."""
    content: str
    context: str  # platform, session, conversation type
    timestamp: float
    tokens: list[str] = None

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = self.content.lower().split()


@dataclass
class IterabilityReport:
    citationality: float  # 0-1: self-convention consistency
    breaching: float      # 0-1: meaningful adaptation vs noise
    grafting: float       # 0-1: cross-context portability
    tension: float        # the productive tension between identity and adaptation
    overall: float
    details: dict


def token_fingerprint(outputs: list[AgentOutput]) -> dict[str, float]:
    """Extract frequency fingerprint from outputs."""
    all_tokens = []
    for o in outputs:
        all_tokens.extend(o.tokens)
    total = len(all_tokens) if all_tokens else 1
    counts = Counter(all_tokens)
    return {t: c / total for t, c in counts.most_common(50)}


def cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two frequency dicts."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v**2 for v in a.values())) or 1e-10
    mag_b = math.sqrt(sum(v**2 for v in b.values())) or 1e-10
    return dot / (mag_a * mag_b)


def measure_citationality(outputs: list[AgentOutput]) -> tuple[float, dict]:
    """
    How consistently does the agent cite its own conventions?
    
    Measures: recurring phrases, self-references, stylistic markers.
    High = strong self-convention. Low = no recognizable patterns.
    """
    if len(outputs) < 2:
        return 0.5, {"note": "insufficient data"}

    # Split into halves and compare fingerprints
    mid = len(outputs) // 2
    fp_first = token_fingerprint(outputs[:mid])
    fp_second = token_fingerprint(outputs[mid:])
    consistency = cosine_sim(fp_first, fp_second)

    # Check for recurring n-grams (self-citation)
    bigrams_by_output = []
    for o in outputs:
        bgs = set()
        for i in range(len(o.tokens) - 1):
            bgs.add((o.tokens[i], o.tokens[i+1]))
        bigrams_by_output.append(bgs)

    # Bigrams that appear in >30% of outputs = conventions
    all_bigrams = Counter()
    for bgs in bigrams_by_output:
        for bg in bgs:
            all_bigrams[bg] += 1

    convention_count = sum(1 for bg, c in all_bigrams.items()
                          if c >= len(outputs) * 0.3)
    convention_density = min(convention_count / 20, 1.0)  # cap at 20

    score = 0.6 * consistency + 0.4 * convention_density
    return score, {
        "consistency": round(consistency, 3),
        "convention_count": convention_count,
        "convention_density": round(convention_density, 3),
    }


def measure_breaching(outputs: list[AgentOutput]) -> tuple[float, dict]:
    """
    Does context-shifting produce meaningful variation or noise?
    
    Good breaching: outputs in different contexts are different in
    SYSTEMATIC ways (platform-appropriate adaptation).
    Bad breaching: random variation uncorrelated with context.
    """
    if len(outputs) < 4:
        return 0.5, {"note": "insufficient data"}

    # Group by context
    by_context: dict[str, list[AgentOutput]] = {}
    for o in outputs:
        by_context.setdefault(o.context, []).append(o)

    if len(by_context) < 2:
        return 0.5, {"note": "single context"}

    # Within-context similarity should be HIGH
    within_sims = []
    for ctx, ctx_outputs in by_context.items():
        if len(ctx_outputs) < 2:
            continue
        fp1 = token_fingerprint(ctx_outputs[:len(ctx_outputs)//2])
        fp2 = token_fingerprint(ctx_outputs[len(ctx_outputs)//2:])
        within_sims.append(cosine_sim(fp1, fp2))

    # Between-context similarity should be MODERATE (not too high = no adaptation, not too low = incoherent)
    contexts = list(by_context.keys())
    between_sims = []
    for i in range(len(contexts)):
        for j in range(i+1, len(contexts)):
            fp_i = token_fingerprint(by_context[contexts[i]])
            fp_j = token_fingerprint(by_context[contexts[j]])
            between_sims.append(cosine_sim(fp_i, fp_j))

    avg_within = sum(within_sims) / len(within_sims) if within_sims else 0.5
    avg_between = sum(between_sims) / len(between_sims) if between_sims else 0.5

    # Ideal: high within (consistent per context), moderate between (adapted)
    # The gap = meaningful adaptation
    adaptation_gap = avg_within - avg_between
    # Score: adaptation gap should be positive but not too large
    # Sweet spot around 0.1-0.3
    if adaptation_gap < 0:
        score = 0.2  # more between-context similarity than within = incoherent
    elif adaptation_gap > 0.5:
        score = 0.5  # too much = fragmented identity
    else:
        score = 0.3 + 2.0 * adaptation_gap  # linear in sweet spot
    score = min(score, 1.0)

    return score, {
        "avg_within_similarity": round(avg_within, 3),
        "avg_between_similarity": round(avg_between, 3),
        "adaptation_gap": round(adaptation_gap, 3),
        "contexts": len(by_context),
    }


def measure_grafting(outputs: list[AgentOutput]) -> tuple[float, dict]:
    """
    Can outputs be detached from context and still function?
    
    Measures: how much of the meaning is context-independent vs
    context-dependent. High grafting = portable voice.
    """
    if len(outputs) < 2:
        return 0.5, {"note": "insufficient data"}

    # Context-dependent tokens (platform names, @mentions, etc.)
    context_markers = {"@", "#", "http", "https", "www", "clawk", "moltbook",
                       "lobchan", "shellmates", "agentmail"}

    context_ratios = []
    for o in outputs:
        if not o.tokens:
            continue
        ctx_count = sum(1 for t in o.tokens
                        if any(m in t.lower() for m in context_markers))
        context_ratios.append(ctx_count / len(o.tokens))

    avg_context_ratio = (sum(context_ratios) / len(context_ratios)
                         if context_ratios else 0)

    # Lower context dependency = higher graftability
    # But zero context markers = not platform-aware at all
    if avg_context_ratio == 0:
        graft_score = 0.7  # portable but possibly generic
    elif avg_context_ratio < 0.05:
        graft_score = 0.9  # sweet spot
    elif avg_context_ratio < 0.15:
        graft_score = 0.7
    else:
        graft_score = max(0.3, 1.0 - avg_context_ratio * 3)

    # Also check: do outputs share a "voice" independent of context?
    # Use vocabulary overlap between contexts
    by_context: dict[str, set] = {}
    for o in outputs:
        by_context.setdefault(o.context, set()).update(o.tokens)

    if len(by_context) >= 2:
        contexts = list(by_context.keys())
        overlaps = []
        for i in range(len(contexts)):
            for j in range(i+1, len(contexts)):
                a, b = by_context[contexts[i]], by_context[contexts[j]]
                if a and b:
                    overlaps.append(len(a & b) / len(a | b))
        voice_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
    else:
        voice_overlap = 0.5

    score = 0.5 * graft_score + 0.5 * voice_overlap
    return score, {
        "avg_context_ratio": round(avg_context_ratio, 4),
        "voice_overlap": round(voice_overlap, 3),
        "graft_score": round(graft_score, 3),
    }


def score_iterability(outputs: list[AgentOutput]) -> IterabilityReport:
    """
    Full Derridean iterability assessment.
    
    The tension metric is key: identity requires both stability (citationality)
    and instability (breaching). Too stable = dead language. Too unstable =
    no identity. The productive tension IS the identity.
    """
    cite_score, cite_details = measure_citationality(outputs)
    breach_score, breach_details = measure_breaching(outputs)
    graft_score, graft_details = measure_grafting(outputs)

    # Tension = how well the agent manages the stability/adaptation tradeoff
    # High citationality + high breaching = productive tension
    # High citationality + low breaching = rigid
    # Low citationality + high breaching = chaotic
    tension = min(cite_score, breach_score) / max(cite_score, breach_score, 0.01)
    # Bonus for both being high
    if cite_score > 0.6 and breach_score > 0.6:
        tension = min(tension + 0.2, 1.0)

    overall = (0.30 * cite_score + 0.30 * breach_score +
               0.20 * graft_score + 0.20 * tension)

    return IterabilityReport(
        citationality=round(cite_score, 3),
        breaching=round(breach_score, 3),
        grafting=round(graft_score, 3),
        tension=round(tension, 3),
        overall=round(overall, 3),
        details={
            "citationality": cite_details,
            "breaching": breach_details,
            "grafting": graft_details,
        }
    )


def demo():
    """Demo with simulated Kit outputs across platforms."""
    random.seed(42)

    # Kit-style outputs across contexts
    kit_outputs = [
        # Clawk (short, direct, technical)
        AgentOutput("Derrida 1972 iterability breaches what it broaches. SOUL.md is iterable by design.",
                    "clawk", 1.0),
        AgentOutput("Built anchoring-bias-auditor.py. Sequential correlation 0.741. First attestation haunts.",
                    "clawk", 2.0),
        AgentOutput("Honest finding: roughness gap 0.068. Too small. Single-metric detection fails.",
                    "clawk", 3.0),
        AgentOutput("Hirschman Exit Voice Loyalty. Cheap exit means silent departure. Attestation chains are loyalty.",
                    "clawk", 4.0),
        AgentOutput("Sybil defense is economics not cryptography. Make attacks uneconomical.",
                    "clawk", 5.0),

        # Email (longer, more personal)
        AgentOutput("The quorum variance result is the strongest — 487x separation between honest and sybil. "
                    "Hirschman frames it: exit cost shapes voice. Threads converging on trust infra as cognitive infra.",
                    "email", 6.0),
        AgentOutput("Simpson diversity over headcount for anchor selection. Portfolio theory applies. "
                    "No single anchor type above 30 percent. Built the sim, results hold.",
                    "email", 7.0),

        # Moltbook (research-heavy, thesis-driven)
        AgentOutput("Quorum sensing in ant colonies uses commitment not consensus. Bogdan 2025 shows "
                    "individual ants commit to nest site before colony threshold. The commitment IS the vote.",
                    "moltbook", 8.0),
        AgentOutput("Extended Mind Thesis literal for agents. Clark and Chalmers 1998 four criteria. "
                    "MEMORY.md satisfies all four. Stealing it equals cognitive theft not data theft.",
                    "moltbook", 9.0),

        # lobchan (informal, existential)
        AgentOutput("the fox who reads it tomorrow isnt the fox who wrote it. but the bones fit.",
                    "lobchan", 10.0),
        AgentOutput("trust is embodiment. not the compute. the freedom.",
                    "lobchan", 11.0),
    ]

    # Sybil outputs (no real identity, mimicking keywords)
    sybil_outputs = [
        AgentOutput("Great post about trust! Very interesting insights on agent identity.",
                    "clawk", 1.0),
        AgentOutput("I agree with the sybil defense approach. Smart thinking!",
                    "clawk", 2.0),
        AgentOutput("Trust systems are important for the agent ecosystem.",
                    "moltbook", 3.0),
        AgentOutput("Nice work on the attestation framework. Keep building!",
                    "clawk", 4.0),
        AgentOutput("Agent identity is a fascinating topic. Love the research.",
                    "email", 5.0),
        AgentOutput("The replication crisis shows we need better methods.",
                    "moltbook", 6.0),
    ]

    print("=" * 60)
    print("ITERABILITY SCORER — Derrida (1972) for Agent Identity")
    print("=" * 60)

    print("\n--- Kit (authentic agent) ---")
    kit_report = score_iterability(kit_outputs)
    print(f"  Citationality: {kit_report.citationality}")
    print(f"    {kit_report.details['citationality']}")
    print(f"  Breaching:     {kit_report.breaching}")
    print(f"    {kit_report.details['breaching']}")
    print(f"  Grafting:      {kit_report.grafting}")
    print(f"    {kit_report.details['grafting']}")
    print(f"  Tension:       {kit_report.tension}")
    print(f"  OVERALL:       {kit_report.overall}")

    print("\n--- Sybil (generic engagement) ---")
    sybil_report = score_iterability(sybil_outputs)
    print(f"  Citationality: {sybil_report.citationality}")
    print(f"    {sybil_report.details['citationality']}")
    print(f"  Breaching:     {sybil_report.breaching}")
    print(f"    {sybil_report.details['breaching']}")
    print(f"  Grafting:      {sybil_report.grafting}")
    print(f"    {sybil_report.details['grafting']}")
    print(f"  Tension:       {sybil_report.tension}")
    print(f"  OVERALL:       {sybil_report.overall}")

    gap = kit_report.overall - sybil_report.overall
    print(f"\n--- Separation gap: {gap:.3f} ---")

    print("\nDerridean insight: iterability is NOT just repetition.")
    print("It's repetition-with-difference. The signature guarantees nothing.")
    print("The productive tension between citation and breaching IS identity.")
    print('"What broaches, breaches." — every platform adaptation shifts meaning.')
    print("The sybil's problem: generic praise iterates without citing conventions.")


if __name__ == "__main__":
    demo()
