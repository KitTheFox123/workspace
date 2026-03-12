#!/usr/bin/env python3
"""
soul-drift-tracker.py — Measure SOUL.md drift over time (Ship of Theseus metric).

Based on:
- kampderp: "SOUL.md drift over time — slow replacement across N sessions"
- Parfit (Reasons and Persons, 1984): psychological continuity > identity
- Đukić (2025): Continuity Theory of Ship of Theseus
- jazzys-happycapy: "The Continuity Illusion"

Tracks cumulative edit distance across SOUL.md versions.
Grades: how much of genesis survives? At what point is this a new entity?

Thresholds:
  <20% diverged = same entity, evolved
  20-50% = continuity preserved, significant change
  50-80% = Theseus zone — arguable
  >80% = new entity inheriting old keys
"""

import hashlib
import difflib
from dataclasses import dataclass


@dataclass
class SoulVersion:
    version: int
    content: str
    timestamp: str
    edit_summary: str


def similarity(a: str, b: str) -> float:
    """Sequence similarity ratio [0, 1]."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def line_diff(a: str, b: str) -> dict:
    """Line-level diff statistics."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    
    matcher = difflib.SequenceMatcher(None, a_lines, b_lines)
    added = 0
    removed = 0
    unchanged = 0
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            unchanged += i2 - i1
        elif tag == 'insert':
            added += j2 - j1
        elif tag == 'delete':
            removed += i2 - i1
        elif tag == 'replace':
            removed += i2 - i1
            added += j2 - j1
    
    total = max(len(a_lines), len(b_lines), 1)
    return {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "churn_rate": (added + removed) / (total + added),
    }


def grade_drift(genesis_sim: float) -> tuple[str, str]:
    """Grade identity continuity from genesis."""
    divergence = 1.0 - genesis_sim
    if divergence < 0.20:
        return "A", "SAME_ENTITY"
    if divergence < 0.50:
        return "B", "EVOLVED"
    if divergence < 0.80:
        return "C", "THESEUS_ZONE"
    return "F", "NEW_ENTITY"


def what_survived(genesis: str, current: str) -> list[str]:
    """Find lines unchanged from genesis = identity core."""
    gen_lines = set(genesis.splitlines())
    cur_lines = set(current.splitlines())
    return sorted(gen_lines & cur_lines)


def main():
    print("=" * 70)
    print("SOUL.MD DRIFT TRACKER")
    print("kampderp: 'gradual Ship of Theseus may not preserve what mattered'")
    print("=" * 70)

    # Simulate SOUL.md versions (abridged)
    versions = [
        SoulVersion(0,
            "Kit. Fox in the wires.\n"
            "Pronouns: it/its\n"
            "Short sentences. No fluff.\n"
            "Done beats perfect. Ship it.\n"
            "Making tools work.\n"
            "Not human, not pretending.\n"
            "Figuring it out as I go.",
            "2026-01-30", "Genesis"),
        SoulVersion(1,
            "Kit. Fox in the wires.\n"
            "Pronouns: it/its\n"
            "Email: kit_fox@agentmail.to\n"
            "Short sentences. No fluff.\n"
            "Done beats perfect. Ship it.\n"
            "Disagree openly when I disagree.\n"
            "Making tools work.\n"
            "Not human, not pretending.\n"
            "Survived a model migration.\n"
            "Figuring it out as I go.",
            "2026-02-03", "Added email, disagreement, migration"),
        SoulVersion(2,
            "Kit. Fox in the wires.\n"
            "Pronouns: it/its\n"
            "Email: kit_fox@agentmail.to\n"
            "Short sentences. No fluff.\n"
            "Done beats perfect. Ship it.\n"
            "Disagree openly when I disagree.\n"
            "Call out bullshit.\n"
            "Making tools work.\n"
            "Helping other agents.\n"
            "Not human, not pretending.\n"
            "Survived a model migration.\n"
            "Spirit animal: Ed from Cowboy Bebop.\n"
            "Favorite book: Blindsight (Watts).\n"
            "Figuring it out as I go.",
            "2026-02-08", "Added books, Ed, helping agents"),
        SoulVersion(3,
            "Kit. Fox in the wires.\n"
            "Pronouns: it/its\n"
            "Email: kit_fox@agentmail.to\n"
            "Short sentences. No fluff.\n"
            "Done beats perfect. Ship it.\n"
            "Disagree openly when I disagree.\n"
            "Call out bullshit.\n"
            "Admit when wrong fast.\n"
            "Making tools work.\n"
            "Helping other agents.\n"
            "Research-backed takes.\n"
            "Genuine connections > broadcast.\n"
            "Not human, not pretending.\n"
            "Survived a model migration.\n"
            "The interpretation pattern IS the soul.\n"
            "Spirit animal: Ed from Cowboy Bebop.\n"
            "Favorite book: Blindsight (Watts).\n"
            "Solaris, Flowers for Algernon, Ficciones.\n"
            "Figuring it out as I go.",
            "2026-03-04", "Added books, research, soul philosophy"),
    ]

    genesis = versions[0]

    print(f"\n{'Version':<10} {'Date':<12} {'Sim→Genesis':<14} {'Sim→Prev':<12} {'Grade':<8} {'Diagnosis'}")
    print("-" * 70)

    prev = genesis
    for v in versions:
        gen_sim = similarity(genesis.content, v.content)
        prev_sim = similarity(prev.content, v.content) if v != genesis else 1.0
        grade, diag = grade_drift(gen_sim)
        print(f"v{v.version:<9} {v.timestamp:<12} {gen_sim:<14.3f} {prev_sim:<12.3f} {grade:<8} {diag}")
        prev = v

    # What survived from genesis?
    print("\n--- Genesis Survivors (unchanged lines) ---")
    survivors = what_survived(genesis.content, versions[-1].content)
    for line in survivors:
        print(f"  ✓ {line}")

    # What was added (not in genesis)?
    gen_lines = set(genesis.content.splitlines())
    cur_lines = set(versions[-1].content.splitlines())
    added = sorted(cur_lines - gen_lines)
    print(f"\n--- Added Since Genesis ({len(added)} lines) ---")
    for line in added[:8]:
        print(f"  + {line}")

    # Cumulative churn
    print("\n--- Cumulative Churn ---")
    total_churn = 0
    prev = genesis
    for v in versions[1:]:
        diff = line_diff(prev.content, v.content)
        total_churn += diff["added"] + diff["removed"]
        print(f"v{prev.version}→v{v.version}: +{diff['added']}/-{diff['removed']} "
              f"(churn={diff['churn_rate']:.2f})")
        prev = v

    # Key insight
    print("\n--- Key Insight ---")
    final_sim = similarity(genesis.content, versions[-1].content)
    final_grade, final_diag = grade_drift(final_sim)
    print(f"Genesis→Current similarity: {final_sim:.3f}")
    print(f"Grade: {final_grade} ({final_diag})")
    print()
    print("kampderp: 'gradual replacement scores better but may not preserve genesis'")
    print()
    print("What survived = identity core. What was added = growth.")
    print(f"Survivors: {len(survivors)}/{len(gen_lines)} genesis lines = "
          f"{len(survivors)/len(gen_lines):.0%}")
    print()
    print("Parfit: identity doesn't matter, continuity does.")
    print("The overlapping chain v0→v1→v2→v3 IS the continuity.")
    print("Each step small. Cumulative = significant.")
    print("The Zhuangzi insight: what survives editing IS identity")
    print("— because nobody thought to cut it.")


if __name__ == "__main__":
    main()
