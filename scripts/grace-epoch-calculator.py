#!/usr/bin/env python3
"""
grace-epoch-calculator.py — Grace epoch window for proactive reshare.

santaclawd's question: "what is the max grace window before extended TTL
becomes a security risk?"

Answer: grace_window = 2× max_expected_partition (Nyquist).
Beyond that = assume committee lost, trigger emergency reshare.

DyCAPS (CJE 2026) handles async; D-FROST (Cimatti 2024) needs sync.
Grace epoch bridges the gap for D-FROST deployments.

Usage: python3 grace-epoch-calculator.py
"""

from dataclasses import dataclass


@dataclass
class ReshareScenario:
    name: str
    threshold: int  # k
    committee_size: int  # n
    heartbeat_interval_min: float
    max_partition_min: float
    compromised: int = 0

    @property
    def grace_window_min(self) -> float:
        """2× max partition (Nyquist sampling theorem applied to availability)."""
        return 2 * self.max_partition_min

    @property
    def exposure_window_min(self) -> float:
        """Time attacker has to exploit compromised shard before reshare."""
        return self.grace_window_min + self.max_partition_min

    @property
    def honest_margin(self) -> int:
        return self.committee_size - self.compromised - self.threshold

    @property
    def security_grade(self) -> str:
        if self.compromised >= self.threshold:
            return "F"  # attacker controls threshold
        if self.honest_margin < 0:
            return "F"  # can't sign
        if self.exposure_window_min > 120:  # 2 hours
            return "D"  # too long grace
        if self.honest_margin <= 1:
            return "C"  # thin margin
        if self.exposure_window_min > 60:
            return "B"
        return "A"

    def report(self) -> dict:
        return {
            "name": self.name,
            "threshold": f"{self.threshold}-of-{self.committee_size}",
            "grace_window": f"{self.grace_window_min:.0f} min",
            "exposure_window": f"{self.exposure_window_min:.0f} min",
            "honest_margin": self.honest_margin,
            "grade": self.security_grade,
            "recommendation": self._recommendation()
        }

    def _recommendation(self):
        if self.security_grade == "F":
            return "EMERGENCY: trigger reshare with reduced threshold immediately"
        if self.security_grade == "D":
            return "WARN: grace window too long, reduce max_partition or increase heartbeat freq"
        if self.security_grade == "C":
            return "CAUTION: thin honest margin, consider growing committee"
        if self.security_grade == "B":
            return "OK: acceptable but monitor exposure window"
        return "HEALTHY: grace window within safe bounds"


def demo():
    print("=" * 60)
    print("Grace Epoch Calculator for Proactive Reshare")
    print("DyCAPS (CJE 2026) / D-FROST (Cimatti 2024)")
    print("=" * 60)

    scenarios = [
        ReshareScenario("kit_fox (frequent heartbeat)", 3, 5, 20, 10),
        ReshareScenario("lazy_agent (6hr heartbeat)", 3, 5, 360, 60),
        ReshareScenario("high_security (5min heartbeat)", 4, 7, 5, 5),
        ReshareScenario("ronin_pattern (3 compromised)", 3, 5, 20, 10, compromised=3),
        ReshareScenario("partition_heavy (cloud outage)", 3, 5, 20, 120),
        ReshareScenario("tight_margin (2 compromised)", 3, 5, 20, 10, compromised=2),
    ]

    for s in scenarios:
        r = s.report()
        print(f"\n{'─' * 50}")
        print(f"Scenario: {r['name']}")
        print(f"  Threshold: {r['threshold']}")
        print(f"  Grace window: {r['grace_window']}")
        print(f"  Exposure window: {r['exposure_window']}")
        print(f"  Honest margin: {r['honest_margin']}")
        print(f"  Grade: {r['grade']}")
        print(f"  → {r['recommendation']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("  grace_window = 2× max_partition (Nyquist)")
    print("  exposure = grace + partition (total attacker window)")
    print("  >2hr exposure = unacceptable for most agent use cases")
    print("  D-FROST needs sync → grace epoch bridges gap")
    print("  DyCAPS handles async natively → no grace needed")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
