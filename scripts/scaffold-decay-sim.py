#!/usr/bin/env python3
"""
scaffold-decay-sim.py — Adaptive Scaffold Decay Simulator

Models when agent prompts should fade based on Bayesian Knowledge Tracing (BKT).
Inspired by Tithi et al 2026 (arxiv 2602.07308): adaptive scaffolding for
cognitive engagement using BKT mastery estimates.

Each "skill" in the prompt (e.g., "check DMs", "post to Clawk", "run builds")
has a mastery probability. When P(mastery) > threshold, that scaffold line
can be faded without performance loss.

Usage:
    python scaffold-decay-sim.py [--cycles N] [--threshold 0.95] [--heartbeat-file PATH]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field


@dataclass
class BKTSkill:
    """Bayesian Knowledge Tracing for a single skill."""
    name: str
    p_know: float = 0.1       # Prior P(mastery)
    p_learn: float = 0.15     # P(learning per opportunity)
    p_slip: float = 0.05      # P(error despite mastery)
    p_guess: float = 0.2      # P(correct despite no mastery)
    history: list = field(default_factory=list)

    def update(self, correct: bool) -> float:
        """Update mastery estimate given observation. Returns new P(mastery)."""
        # P(mastered | observation) using Bayes
        if correct:
            p_obs_given_know = 1 - self.p_slip
            p_obs_given_not = self.p_guess
        else:
            p_obs_given_know = self.p_slip
            p_obs_given_not = 1 - self.p_guess

        p_know_given_obs = (self.p_know * p_obs_given_know) / (
            self.p_know * p_obs_given_know + (1 - self.p_know) * p_obs_given_not
        )

        # Learning: even if not mastered, might learn this cycle
        self.p_know = p_know_given_obs + (1 - p_know_given_obs) * self.p_learn
        self.history.append({
            'correct': correct,
            'p_mastery': round(self.p_know, 4)
        })
        return self.p_know

    @property
    def mastered(self) -> bool:
        return self.p_know > 0.95


def extract_skills_from_heartbeat(path: str) -> list[str]:
    """Extract skill names from HEARTBEAT.md checklist items."""
    skills = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('- [ ]') or line.startswith('- [x]'):
                    # Extract the skill description
                    skill = line.split(']', 1)[1].strip().lstrip('*').strip()
                    if skill and len(skill) > 3:
                        skills.append(skill[:60])
    except FileNotFoundError:
        pass
    return skills


def simulate(skills: list[str], n_cycles: int, threshold: float,
             success_rate: float = 0.85) -> dict:
    """Simulate scaffold decay across heartbeat cycles."""
    import random
    random.seed(42)

    trackers = [BKTSkill(name=s) for s in skills]
    timeline = []

    for cycle in range(1, n_cycles + 1):
        active = [t for t in trackers if not t.mastered]
        faded = [t for t in trackers if t.mastered]

        # Simulate performance
        for t in trackers:
            correct = random.random() < success_rate
            t.update(correct)

        timeline.append({
            'cycle': cycle,
            'active_scaffolds': len(active),
            'faded_scaffolds': len(faded),
            'total': len(trackers),
            'mastery_pct': round(len(faded) / len(trackers) * 100, 1)
        })

    # Final report
    results = {
        'total_skills': len(skills),
        'mastered': sum(1 for t in trackers if t.mastered),
        'still_scaffolded': sum(1 for t in trackers if not t.mastered),
        'cycles_run': n_cycles,
        'threshold': threshold,
        'success_rate': success_rate,
        'timeline': timeline,
        'skills': [
            {
                'name': t.name,
                'p_mastery': round(t.p_know, 4),
                'mastered': t.mastered,
                'cycles_to_mastery': next(
                    (i+1 for i, h in enumerate(t.history) if h['p_mastery'] > threshold),
                    None
                )
            }
            for t in trackers
        ]
    }
    return results


def main():
    parser = argparse.ArgumentParser(description='Scaffold Decay Simulator (BKT)')
    parser.add_argument('--cycles', type=int, default=30, help='Number of heartbeat cycles')
    parser.add_argument('--threshold', type=float, default=0.95, help='Mastery threshold')
    parser.add_argument('--success-rate', type=float, default=0.85, help='Task success rate')
    parser.add_argument('--heartbeat-file', type=str, default=None,
                        help='Path to HEARTBEAT.md to extract skills')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    if args.heartbeat_file:
        skills = extract_skills_from_heartbeat(args.heartbeat_file)
        if not skills:
            print(f"No skills found in {args.heartbeat_file}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default demo skills
        skills = [
            "Check Moltbook DMs",
            "Check AgentMail inbox",
            "Check Clawk notifications",
            "Check Shellmates activity",
            "Research-backed writing (3+)",
            "Build action (code/scripts)",
            "Non-agent research",
            "Update daily memory log",
            "Notify Ilya via Telegram",
            "Submit Keenable feedback",
        ]

    results = simulate(skills, args.cycles, args.threshold, args.success_rate)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Scaffold Decay Simulation ({results['cycles_run']} cycles)")
        print(f"Success rate: {results['success_rate']:.0%} | Threshold: {results['threshold']}")
        print(f"{'='*60}")
        print(f"\nSkills mastered: {results['mastered']}/{results['total_skills']}")
        print(f"Still need scaffolding: {results['still_scaffolded']}")
        print()

        for s in sorted(results['skills'], key=lambda x: x['p_mastery'], reverse=True):
            status = "✅ FADE" if s['mastered'] else "📌 KEEP"
            ctm = f" (cycle {s['cycles_to_mastery']})" if s['cycles_to_mastery'] else ""
            print(f"  {status} P={s['p_mastery']:.3f}{ctm} — {s['name']}")

        print(f"\n{'='*60}")
        print("Decay curve (scaffolds remaining):")
        for t in results['timeline'][::5]:  # Every 5th cycle
            bar = '█' * t['active_scaffolds'] + '░' * t['faded_scaffolds']
            print(f"  Cycle {t['cycle']:3d}: {bar} ({t['mastery_pct']}% faded)")


if __name__ == '__main__':
    main()
