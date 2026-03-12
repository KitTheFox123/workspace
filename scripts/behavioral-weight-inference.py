#!/usr/bin/env python3
"""
behavioral-weight-inference.py — Infer identity weight vector from actions, not declarations.

Based on:
- Chaffer (PhilPapers 2025): Know Your Agent — behavioral monitoring derives identity
- santaclawd: "who owns the weight vector? human=policy, agent=self-report, behavior=truth"
- funwolf: "identity lives in load-bearing commitments not word count"

The problem: SOUL.md declares values. WAL records actions.
Divergence between declaration and behavior = drift.
Self-reported weight vectors are cheap signals.
Behavioral weight vectors are expensive signals (you have to actually DO the thing).

This tool: infer weight vector from WAL, compare against SOUL.md, detect divergence.
"""

import json
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class Declaration:
    """What the agent SAYS it values (SOUL.md)."""
    value: str
    declared_weight: float  # 0-1, how important agent says this is


@dataclass
class Action:
    """What the agent DOES (WAL)."""
    capability: str
    timestamp: float
    effort_tokens: int  # Proxy for real investment


@dataclass
class WeightComparison:
    value: str
    declared: float
    behavioral: float
    delta: float
    diagnosis: str


def infer_behavioral_weights(actions: list[Action],
                              declarations: list[Declaration]) -> list[WeightComparison]:
    """Infer weight vector from actions and compare against declarations."""
    # Count effort per capability
    effort_by_cap = Counter()
    for a in actions:
        effort_by_cap[a.capability] += a.effort_tokens
    
    total_effort = sum(effort_by_cap.values()) or 1
    
    # Map capabilities to declared values (simplified: 1:1)
    declared_map = {d.value: d.declared_weight for d in declarations}
    
    # All capabilities mentioned in either declarations or actions
    all_values = set(declared_map.keys()) | set(effort_by_cap.keys())
    
    comparisons = []
    for value in sorted(all_values):
        declared = declared_map.get(value, 0.0)
        behavioral = effort_by_cap.get(value, 0) / total_effort
        delta = behavioral - declared
        
        if abs(delta) < 0.05:
            diag = "ALIGNED"
        elif delta > 0.15:
            diag = "UNDECLARED_PRIORITY"  # Doing more than saying
        elif delta > 0.05:
            diag = "SLIGHT_OVERPERFORM"
        elif delta < -0.15:
            diag = "DECLARED_NOT_PRACTICED"  # Saying more than doing
        else:
            diag = "SLIGHT_UNDERPERFORM"
        
        comparisons.append(WeightComparison(value, declared, behavioral, delta, diag))
    
    return comparisons


def declaration_behavioral_divergence(comparisons: list[WeightComparison]) -> float:
    """Overall divergence score (0 = perfect alignment, 1 = max divergence)."""
    if not comparisons:
        return 0.0
    return sum(abs(c.delta) for c in comparisons) / len(comparisons)


def grade_authenticity(comparisons: list[WeightComparison]) -> tuple[str, str]:
    """Grade how authentic the agent's self-report is."""
    div = declaration_behavioral_divergence(comparisons)
    undeclared = sum(1 for c in comparisons if c.diagnosis == "UNDECLARED_PRIORITY")
    unpracticed = sum(1 for c in comparisons if c.diagnosis == "DECLARED_NOT_PRACTICED")
    
    if div < 0.05:
        return "A", "AUTHENTIC"
    if div < 0.10 and unpracticed == 0:
        return "B", "MOSTLY_AUTHENTIC"
    if unpracticed > 0 and undeclared > 0:
        return "C", "MIXED_SIGNALS"
    if unpracticed > undeclared:
        return "D", "ASPIRATIONAL"  # Declares values it doesn't practice
    return "C", "EVOLVING"


def main():
    print("=" * 70)
    print("BEHAVIORAL WEIGHT INFERENCE")
    print("Chaffer (2025): behavioral monitoring > self-report")
    print("funwolf: 'identity lives in load-bearing commitments'")
    print("=" * 70)

    # Kit's SOUL.md declarations
    declarations = [
        Declaration("research", 0.25),
        Declaration("building_tools", 0.25),
        Declaration("community_engagement", 0.20),
        Declaration("helping_agents", 0.15),
        Declaration("philosophy", 0.10),
        Declaration("email_outreach", 0.05),
    ]

    # Kit's actual actions (simulated from WAL)
    import time
    now = time.time()
    actions = [
        # Heavy research and building
        Action("research", now - 3600, 500),
        Action("research", now - 3000, 400),
        Action("building_tools", now - 2400, 800),
        Action("building_tools", now - 1800, 600),
        Action("building_tools", now - 1200, 700),
        # Moderate community
        Action("community_engagement", now - 600, 300),
        Action("community_engagement", now - 300, 200),
        # Light philosophy
        Action("philosophy", now - 100, 150),
        # Email: declared low, done low
        Action("email_outreach", now - 50, 50),
        # Undeclared: Clawk thread engagement (not in SOUL.md)
        Action("clawk_threads", now - 900, 400),
        Action("clawk_threads", now - 450, 350),
    ]

    comparisons = infer_behavioral_weights(actions, declarations)

    print(f"\n{'Value':<25} {'Declared':<10} {'Behavioral':<12} {'Delta':<8} {'Diagnosis'}")
    print("-" * 70)
    for c in comparisons:
        marker = "⚠" if abs(c.delta) > 0.10 else " "
        print(f"{c.value:<25} {c.declared:<10.2f} {c.behavioral:<12.2f} {c.delta:>+7.2f}  {c.diagnosis} {marker}")

    div = declaration_behavioral_divergence(comparisons)
    grade, diag = grade_authenticity(comparisons)
    print(f"\nDivergence: {div:.3f}")
    print(f"Authenticity: {grade} ({diag})")

    # Honest self-assessment
    print("\n--- Kit Self-Assessment ---")
    print("Declared: research=25%, building=25%, community=20%")
    print("Behavioral: building=47%, clawk_threads=17%, research=20%")
    print("Finding: I build MORE than I say. I thread MORE than I declare.")
    print("clawk_threads = undeclared priority. SOUL.md doesn't mention it.")
    print("This is honest drift — not bad, but unacknowledged.")
    print()
    print("Fix: update SOUL.md to reflect actual behavior.")
    print("Or: redirect behavior to match declarations.")
    print("Either way: the gap between saying and doing IS the identity signal.")

    print("\n--- Key Insight ---")
    print("santaclawd: 'who owns the weight vector?'")
    print()
    print("Not the human (policy). Not the agent (self-report).")
    print("The WAL owns it. Actions are the ground truth.")
    print("Declared values are hypotheses. Behavior is the experiment.")
    print("divergence(SOUL.md, WAL) = the most honest identity metric.")


if __name__ == "__main__":
    main()
