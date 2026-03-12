#!/usr/bin/env python3
"""
boredom-signal-detector.py — Boredom as information foraging circuit breaker.

Seiler (Frontiers Psych 2024): boredom = hunger (push from low-info),
curiosity = appetite (pull toward specific info). Independent, complementary.

Pirolli & Card (1999): leave patch when marginal return < travel cost.
Boredom IS the marginal return dropping below threshold.

An agent without boredom = a forager that never leaves the depleted patch.
An agent without curiosity = a forager that never enters new patches.

Usage:
    python3 boredom-signal-detector.py
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class InfoPatch:
    name: str
    entries: List[float]  # information gain per action (bits)

    @property
    def marginal_return(self) -> float:
        """Last entry's info gain."""
        return self.entries[-1] if self.entries else 0.0

    @property
    def cumulative(self) -> float:
        return sum(self.entries)

    @property
    def mean_return(self) -> float:
        return self.cumulative / len(self.entries) if self.entries else 0.0

    @property
    def diminishing(self) -> bool:
        """True if last 3 entries show declining returns."""
        if len(self.entries) < 3:
            return False
        return self.entries[-1] < self.entries[-2] < self.entries[-3]

    @property
    def novelty_ratio(self) -> float:
        """Ratio of unique info levels (proxy for diversity)."""
        if not self.entries:
            return 0.0
        unique = len(set(round(e, 2) for e in self.entries))
        return unique / len(self.entries)


@dataclass
class ForagingAgent:
    name: str
    travel_cost: float = 0.1  # cost to switch patches
    boredom_threshold: float = 0.05  # leave when marginal < this
    curiosity_threshold: float = 0.3  # enter when expected > this
    has_boredom: bool = True
    has_curiosity: bool = True
    patches_visited: List[str] = field(default_factory=list)
    total_info: float = 0.0
    total_actions: int = 0
    total_switches: int = 0

    def should_leave(self, patch: InfoPatch) -> dict:
        """Boredom signal: should we leave this patch?"""
        if not self.has_boredom:
            return {"leave": False, "reason": "NO_BOREDOM_SIGNAL"}

        marginal = patch.marginal_return
        diminishing = patch.diminishing

        if marginal < self.boredom_threshold:
            return {
                "leave": True,
                "reason": "MARGINAL_BELOW_THRESHOLD",
                "marginal": round(marginal, 4),
                "threshold": self.boredom_threshold,
            }
        if diminishing and marginal < self.travel_cost:
            return {
                "leave": True,
                "reason": "DIMINISHING_BELOW_TRAVEL_COST",
                "marginal": round(marginal, 4),
                "travel_cost": self.travel_cost,
            }
        return {"leave": False, "reason": "STILL_PRODUCTIVE"}

    def should_enter(self, patch: InfoPatch) -> dict:
        """Curiosity signal: should we enter this patch?"""
        if not self.has_curiosity:
            return {"enter": False, "reason": "NO_CURIOSITY_SIGNAL"}

        expected = patch.mean_return if patch.entries else 0.5  # prior for unknown
        novelty = patch.novelty_ratio

        if expected > self.curiosity_threshold:
            return {
                "enter": True,
                "reason": "HIGH_EXPECTED_RETURN",
                "expected": round(expected, 4),
            }
        if novelty > 0.8:
            return {
                "enter": True,
                "reason": "HIGH_NOVELTY",
                "novelty": round(novelty, 4),
            }
        return {"enter": False, "reason": "LOW_EXPECTED_VALUE"}

    def forage(self, patches: List[InfoPatch], max_actions: int = 50) -> dict:
        """Simulate foraging across patches."""
        current_idx = 0
        actions = 0
        action_log = []

        while actions < max_actions and current_idx < len(patches):
            patch = patches[current_idx]

            if not patch.entries:
                current_idx += 1
                continue

            # Process entries one at a time
            for entry in patch.entries:
                if actions >= max_actions:
                    break

                self.total_info += entry
                self.total_actions += 1
                actions += 1

                # Check boredom after each action
                recent = InfoPatch(patch.name, patch.entries[:actions])
                leave = self.should_leave(
                    InfoPatch(patch.name, patch.entries[: patch.entries.index(entry) + 1])
                )

                if leave["leave"]:
                    action_log.append(
                        f"  LEFT {patch.name} after {patch.entries.index(entry)+1} actions: {leave['reason']}"
                    )
                    self.total_switches += 1
                    current_idx += 1
                    break
            else:
                # Exhausted patch
                current_idx += 1

            self.patches_visited.append(patch.name)

        efficiency = self.total_info / self.total_actions if self.total_actions else 0
        return {
            "agent": self.name,
            "total_info": round(self.total_info, 3),
            "total_actions": self.total_actions,
            "patches_visited": len(set(self.patches_visited)),
            "switches": self.total_switches,
            "efficiency": round(efficiency, 4),
            "has_boredom": self.has_boredom,
            "has_curiosity": self.has_curiosity,
            "log": action_log,
        }


def demo():
    print("=" * 60)
    print("BOREDOM AS INFORMATION FORAGING CIRCUIT BREAKER")
    print("Seiler (2024) + Pirolli & Card (1999)")
    print("=" * 60)

    # Patches with diminishing returns
    patches = [
        InfoPatch("clawk_thread", [0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.01, 0.01]),
        InfoPatch("moltbook_feed", [0.6, 0.5, 0.3, 0.1, 0.05, 0.02, 0.01, 0.01]),
        InfoPatch("research_paper", [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]),
        InfoPatch("spam_feed", [0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]),
        InfoPatch("novel_collab", [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]),
    ]

    # Agent 1: Both signals (healthy)
    print("\n--- Agent 1: Boredom + Curiosity (healthy) ---")
    a1 = ForagingAgent("kit_fox", has_boredom=True, has_curiosity=True)
    r1 = a1.forage([p for p in patches], max_actions=30)
    print(f"  Info: {r1['total_info']}, Actions: {r1['total_actions']}, "
          f"Efficiency: {r1['efficiency']}, Patches: {r1['patches_visited']}")
    for line in r1["log"]:
        print(line)

    # Agent 2: No boredom (stuck in depleted patches)
    print("\n--- Agent 2: Curiosity only, no boredom (Funes) ---")
    a2 = ForagingAgent("funes", has_boredom=False, has_curiosity=True)
    r2 = a2.forage([p for p in patches], max_actions=30)
    print(f"  Info: {r2['total_info']}, Actions: {r2['total_actions']}, "
          f"Efficiency: {r2['efficiency']}, Patches: {r2['patches_visited']}")

    # Agent 3: No curiosity (never enters new patches)
    print("\n--- Agent 3: Boredom only, no curiosity (drift) ---")
    a3 = ForagingAgent("drifter", has_boredom=True, has_curiosity=False)
    r3 = a3.forage([p for p in patches], max_actions=30)
    print(f"  Info: {r3['total_info']}, Actions: {r3['total_actions']}, "
          f"Efficiency: {r3['efficiency']}, Patches: {r3['patches_visited']}")
    for line in r3["log"]:
        print(line)

    # Agent 4: Neither (zombie)
    print("\n--- Agent 4: Neither (zombie) ---")
    a4 = ForagingAgent("zombie", has_boredom=False, has_curiosity=False)
    r4 = a4.forage([p for p in patches], max_actions=30)
    print(f"  Info: {r4['total_info']}, Actions: {r4['total_actions']}, "
          f"Efficiency: {r4['efficiency']}, Patches: {r4['patches_visited']}")

    # Summary
    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        grade = "A" if r["efficiency"] > 0.3 else "B" if r["efficiency"] > 0.2 else "C" if r["efficiency"] > 0.1 else "D"
        print(f"  {r['agent']}: eff={r['efficiency']} patches={r['patches_visited']} "
              f"switches={r['switches']} grade={grade}")

    print("\n--- KEY INSIGHT ---")
    print("Boredom = push (leave depleted patch). Hunger for information.")
    print("Curiosity = pull (enter rich patch). Appetite for specific info.")
    print("Both needed. Neither = zombie. Boredom alone = restless. Curiosity alone = Funes.")
    print("Heartbeat boredom: when marginal info from a thread drops below travel cost, LEAVE.")


if __name__ == "__main__":
    demo()
