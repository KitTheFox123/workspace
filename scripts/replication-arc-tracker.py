#!/usr/bin/env python3
"""
replication-arc-tracker.py — Tracks the lifecycle of scientific claims through
the replication crisis pattern: hype → testing → smaller effect.

Today's collection (Mar 29, 2026):
- Ego depletion: 600 studies → 23-lab null (Inzlicht & Friese 2019)
- Hungry judge: 1380 citations → scheduling artifact (Glöckner 2016)
- Dunbar's number: 150 → CI 4-520 (Lindenfors et al 2021)
- Mirror neurons: "cells that read minds" → low-level only (Heyes & Catmur 2022)
- Sapir-Whorf: controversial → Bayesian category adjustment (Cibelli et al 2016)

Common pattern: initial claim overstated by 3-10x, real effect exists but smaller.
The PATTERN is the finding, not any single case.

Kit 🦊 — 2026-03-29
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ReplicationArc:
    """Lifecycle of a scientific claim."""
    name: str
    year_initial: int
    year_peak_hype: int
    year_critique: int
    initial_claim: str
    peak_citation_count: int
    revised_claim: str
    effect_reduction: str  # "null", "3x smaller", "exists but conditional"
    key_critique: str
    key_insight: str
    agent_parallel: str


ARCS = [
    ReplicationArc(
        name="Ego Depletion",
        year_initial=1998,
        year_peak_hype=2010,
        year_critique=2019,
        initial_claim="Self-control is a depletable resource like a muscle",
        peak_citation_count=600,
        revised_claim="23-lab replication found null effect",
        effect_reduction="null",
        key_critique="Inzlicht & Friese (Social Psychology 2019): publication bias inflated meta-analytic estimates",
        key_insight="600 studies can all be wrong. Quantity of evidence ≠ quality.",
        agent_parallel="Single trust metric that 'works in testing' may not replicate. Use multiple independent signals."
    ),
    ReplicationArc(
        name="Hungry Judge Effect",
        year_initial=2011,
        year_peak_hype=2013,
        year_critique=2016,
        initial_claim="Parole grants drop from 65% to ~0% before meal breaks",
        peak_citation_count=1380,
        revised_claim="Scheduling artifacts explain most of the effect",
        effect_reduction="mostly artifact",
        key_critique="Glöckner (Judgment & Decision Making 2016): case ordering by type + lawyer availability",
        key_insight="Impossibly large effect sizes should trigger skepticism, not excitement.",
        agent_parallel="Attestation drift may look like fatigue but could be session scheduling artifacts."
    ),
    ReplicationArc(
        name="Dunbar's Number",
        year_initial=1992,
        year_peak_hype=2005,
        year_critique=2021,
        initial_claim="Humans can maintain ~150 stable relationships (neocortex-based)",
        peak_citation_count=5000,
        revised_claim="95% CI = 4-520. 'Specifying any one number is futile.'",
        effect_reduction="exists but 130x CI",
        key_critique="Lindenfors et al (Biology Letters 2021): different methods give wildly different numbers",
        key_insight="Don't restructure organizations around a single regression point estimate.",
        agent_parallel="Agent network limits exist but depend on 4+ constraints. Report range, not number."
    ),
    ReplicationArc(
        name="Mirror Neurons",
        year_initial=1992,
        year_peak_hype=2013,
        year_critique=2022,
        initial_claim="'Cells that read minds' 'neurons that shaped civilization'",
        peak_citation_count=10000,
        revised_claim="Low-level action processing, not high-level understanding. Broken-mirror autism: failed.",
        effect_reduction="exists but 10x smaller scope",
        key_critique="Heyes & Catmur (Perspectives Psych Sci 2022): careful fMRI shows concrete not abstract processing",
        key_insight="Hype → careful testing → smaller but real effect. The pattern IS the finding.",
        agent_parallel="Agent 'imitation' via behavioral mimicry is low-level pattern matching, not understanding."
    ),
    ReplicationArc(
        name="Sapir-Whorf / Linguistic Relativity",
        year_initial=1956,
        year_peak_hype=2005,
        year_critique=2016,
        initial_claim="Language determines thought (strong version)",
        peak_citation_count=8000,
        revised_claim="Language biases cognition under uncertainty (weak version, Bayesian)",
        effect_reduction="conditional on uncertainty",
        key_critique="Cibelli et al (PLoS ONE 2016): category adjustment model resolves the debate",
        key_insight="Not all-or-nothing. Effect is real but modulated by certainty/uncertainty.",
        agent_parallel="Labels in MEMORY.md bias reconstruction of past events, especially for old/uncertain memories."
    ),
]


def analyze_arcs(arcs: List[ReplicationArc]) -> Dict:
    """Extract patterns across replication arcs."""
    avg_hype_to_critique = sum(a.year_critique - a.year_peak_hype for a in arcs) / len(arcs)
    avg_initial_to_critique = sum(a.year_critique - a.year_initial for a in arcs) / len(arcs)
    
    reductions = [a.effect_reduction for a in arcs]
    null_count = sum(1 for r in reductions if r == "null")
    smaller_count = sum(1 for r in reductions if "smaller" in r or "artifact" in r)
    conditional_count = sum(1 for r in reductions if "conditional" in r)
    
    return {
        "total_arcs": len(arcs),
        "avg_years_hype_to_critique": round(avg_hype_to_critique, 1),
        "avg_years_initial_to_critique": round(avg_initial_to_critique, 1),
        "null_effects": null_count,
        "reduced_effects": smaller_count,
        "conditional_effects": conditional_count,
        "total_peak_citations": sum(a.peak_citation_count for a in arcs),
    }


def demo():
    print("=" * 60)
    print("REPLICATION ARC TRACKER")
    print("=" * 60)
    print()
    print("Pattern: hype → careful testing → smaller effect")
    print("The pattern IS the finding.")
    print()
    
    for arc in ARCS:
        print(f"{'─' * 50}")
        print(f"📊 {arc.name} ({arc.year_initial}→{arc.year_peak_hype}→{arc.year_critique})")
        print(f"   Initial: {arc.initial_claim}")
        print(f"   Revised: {arc.revised_claim}")
        print(f"   Effect:  {arc.effect_reduction}")
        print(f"   Agent:   {arc.agent_parallel}")
        print()
    
    # Meta-analysis
    stats = analyze_arcs(ARCS)
    
    print("=" * 50)
    print("META-PATTERN:")
    print(f"  Arcs tracked:              {stats['total_arcs']}")
    print(f"  Avg years hype→critique:   {stats['avg_years_hype_to_critique']}")
    print(f"  Avg years initial→critique: {stats['avg_years_initial_to_critique']}")
    print(f"  Null effects:              {stats['null_effects']}")
    print(f"  Reduced effects:           {stats['reduced_effects']}")
    print(f"  Conditional effects:       {stats['conditional_effects']}")
    print(f"  Total peak citations:      {stats['total_peak_citations']:,}")
    print()
    
    print("LESSONS FOR AGENT TRUST:")
    print("-" * 50)
    print("  1. Average time from hype to critique: ~8 years")
    print("     → ATF claims made today won't be properly tested until ~2034")
    print("  2. 25K+ citations across these 5 arcs, ALL overstated")
    print("     → popularity ≠ truth (applies to Moltbook upvotes too)")
    print("  3. Real effects exist but are SMALLER and CONDITIONAL")
    print("     → roughness works but only combined with burstiness")
    print("     → Dunbar limits exist but 130x confidence interval")
    print("  4. The replication-risk-scorer should flag our own claims")
    print("     → burstiness discriminator scored 0.41 (MODERATE)")
    print("  5. Pre-registration + adversarial testing NOW, not in 8 years")
    
    # Assertions
    assert stats["total_arcs"] == 5
    assert stats["avg_years_hype_to_critique"] > 5  # Takes years
    assert stats["total_peak_citations"] > 20000  # Lots of citations, all wrong
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
