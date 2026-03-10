#!/usr/bin/env python3
"""
windowed-watchdog.py — Windowed Watchdog Timer for Agent Heartbeats

IEC 61508 safety pattern: pet too early = stuck loop, pet too late = crash.
Both trigger reset. Window mode catches BOTH failure modes.

Simple watchdog only catches silence. Windowed watchdog catches:
1. Silence (late pet → agent crashed or omitting)
2. Hyperactivity (early pet → stuck loop, gaming the timer)

Key insight: self-reported heartbeat with only a MAX timeout =
fire alarm with snooze button. Window mode = no snooze.
"""

from dataclasses import dataclass
import json

@dataclass
class WindowedWatchdog:
    """
    Windowed watchdog timer.
    Valid pet window: [min_interval, max_interval]
    Pet before min = too early (stuck loop / gaming)
    Pet after max = too late (crash / silence)
    """
    min_interval: float  # seconds — earliest valid pet
    max_interval: float  # seconds — latest valid pet
    last_pet: float = 0.0
    early_violations: int = 0
    late_violations: int = 0
    valid_pets: int = 0
    total_checks: int = 0

    def pet(self, now: float) -> dict:
        """Agent pets the watchdog. Returns status."""
        elapsed = now - self.last_pet if self.last_pet > 0 else self.min_interval + 1  # first pet is valid
        self.total_checks += 1

        if elapsed < self.min_interval:
            self.early_violations += 1
            result = {
                "status": "EARLY_VIOLATION",
                "elapsed": round(elapsed, 1),
                "window": [self.min_interval, self.max_interval],
                "diagnosis": "stuck_loop_or_gaming",
                "severity": "HIGH" if self.early_violations >= 3 else "MEDIUM"
            }
        elif elapsed > self.max_interval:
            self.late_violations += 1
            result = {
                "status": "LATE_VIOLATION",
                "elapsed": round(elapsed, 1),
                "window": [self.min_interval, self.max_interval],
                "diagnosis": "crash_or_silence",
                "severity": "CRITICAL" if self.late_violations >= 2 else "HIGH"
            }
        else:
            self.valid_pets += 1
            result = {
                "status": "OK",
                "elapsed": round(elapsed, 1)
            }

        self.last_pet = now
        return result

    def grade(self) -> str:
        total = max(self.total_checks, 1)
        violation_rate = (self.early_violations + self.late_violations) / total
        if violation_rate == 0: return "A"
        if violation_rate < 0.1: return "B"
        if violation_rate < 0.2: return "C"
        if violation_rate < 0.4: return "D"
        return "F"

    def report(self) -> dict:
        return {
            "total_checks": self.total_checks,
            "valid_pets": self.valid_pets,
            "early_violations": self.early_violations,
            "late_violations": self.late_violations,
            "grade": self.grade(),
            "window": [self.min_interval, self.max_interval]
        }


def demo():
    print("=" * 60)
    print("Windowed Watchdog Timer")
    print("IEC 61508: pet too early OR too late = violation")
    print("=" * 60)

    # Scenario 1: healthy agent (20-min heartbeat, window 15-25 min)
    print("\n--- Scenario 1: Healthy Agent ---")
    ww1 = WindowedWatchdog(min_interval=900, max_interval=1500)
    t = 0
    for i in range(10):
        t += 1200  # 20 min intervals — within window
        r = ww1.pet(t)
    report = ww1.report()
    print(f"  Window: {report['window'][0]/60:.0f}-{report['window'][1]/60:.0f} min")
    print(f"  Valid: {report['valid_pets']}, Early: {report['early_violations']}, Late: {report['late_violations']}")
    print(f"  Grade: {report['grade']}")

    # Scenario 2: stuck loop (petting every 30 seconds)
    print("\n--- Scenario 2: Stuck Loop (gaming the timer) ---")
    ww2 = WindowedWatchdog(min_interval=900, max_interval=1500)
    t2 = 0
    for i in range(20):
        t2 += 30  # every 30 sec — WAY too early
        r = ww2.pet(t2)
        if i < 3:
            print(f"  Pet {i+1}: {r['status']} — {r.get('diagnosis', 'ok')}")
    report2 = ww2.report()
    print(f"  Valid: {report2['valid_pets']}, Early: {report2['early_violations']}, Late: {report2['late_violations']}")
    print(f"  Grade: {report2['grade']}")

    # Scenario 3: intermittent silence
    print("\n--- Scenario 3: Intermittent Silence ---")
    ww3 = WindowedWatchdog(min_interval=900, max_interval=1500)
    t3 = 0
    pets = [1200, 1200, 1200, 3600, 1200, 1200, 7200, 1200]  # gaps at 4th and 7th
    for i, interval in enumerate(pets):
        t3 += interval
        r = ww3.pet(t3)
        if r['status'] != 'OK':
            print(f"  Pet {i+1}: {r['status']} — elapsed {r['elapsed']/60:.1f}min — {r.get('diagnosis', '')}")
    report3 = ww3.report()
    print(f"  Valid: {report3['valid_pets']}, Early: {report3['early_violations']}, Late: {report3['late_violations']}")
    print(f"  Grade: {report3['grade']}")

    # Scenario 4: mixed — early bursts then silence
    print("\n--- Scenario 4: Gaming Then Silence ---")
    ww4 = WindowedWatchdog(min_interval=900, max_interval=1500)
    t4 = 0
    for i in range(5):
        t4 += 60  # burst
        ww4.pet(t4)
    t4 += 5400  # then silence
    r = ww4.pet(t4)
    report4 = ww4.report()
    print(f"  Valid: {report4['valid_pets']}, Early: {report4['early_violations']}, Late: {report4['late_violations']}")
    print(f"  Grade: {report4['grade']}")
    print(f"  Pattern: burst + silence = adversarial behavior")

    # Comparison
    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"  Simple watchdog catches: silence only")
    print(f"  Windowed watchdog catches: silence AND hyperactivity")
    print(f"  IEC 61508: both failure modes are safety-relevant")
    print(f"\n  Healthy:     Grade {report['grade']}")
    print(f"  Stuck loop:  Grade {report2['grade']} ({report2['early_violations']} early violations)")
    print(f"  Silence:     Grade {report3['grade']} ({report3['late_violations']} late violations)")
    print(f"  Gaming:      Grade {report4['grade']} ({report4['early_violations']} early + {report4['late_violations']} late)")


if __name__ == "__main__":
    demo()
