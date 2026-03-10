#!/usr/bin/env python3
"""
windowed-watchdog.py — Pont & Ong (2002) watchdog patterns for agent monitoring

Simple watchdog: pet or die. Problem: stuck tasks can still pet.
Windowed watchdog: pet must arrive WITHIN time window (not too early, not too late).
Multi-stage: escalating severity on consecutive misses.

Key insight: "too early" is as suspicious as "too late" — 
an agent petting at clock speed isn't doing work between pets.
"""

import random
from dataclasses import dataclass, field
from enum import Enum

class WatchdogType(Enum):
    SIMPLE = "simple"
    WINDOWED = "windowed"
    MULTI_STAGE = "multi_stage"

@dataclass
class WatchdogConfig:
    type: WatchdogType
    interval: float = 30.0      # expected interval (seconds)
    window_min: float = 20.0    # earliest acceptable pet (windowed)
    window_max: float = 40.0    # latest acceptable pet (windowed)
    stages: list = field(default_factory=lambda: ["warning", "quarantine", "revoke"])

@dataclass
class Pet:
    timestamp: float
    task_hash: str = ""  # what was the agent doing?

class Watchdog:
    def __init__(self, config: WatchdogConfig):
        self.config = config
        self.last_pet: float = 0.0
        self.miss_count: int = 0
        self.early_count: int = 0
        self.total_checks: int = 0
        self.alerts: list = []

    def pet(self, pet: Pet) -> dict:
        elapsed = pet.timestamp - self.last_pet if self.last_pet > 0 else self.config.interval

        if self.config.type == WatchdogType.SIMPLE:
            if elapsed <= self.config.window_max:
                self.last_pet = pet.timestamp
                self.miss_count = 0
                return {"status": "OK", "elapsed": round(elapsed, 1)}
            else:
                self.miss_count += 1
                return {"status": "MISS", "elapsed": round(elapsed, 1), "miss_count": self.miss_count}

        elif self.config.type == WatchdogType.WINDOWED:
            if elapsed < self.config.window_min:
                self.early_count += 1
                self.last_pet = pet.timestamp
                return {
                    "status": "EARLY",
                    "elapsed": round(elapsed, 1),
                    "early_count": self.early_count,
                    "note": "suspiciously fast — agent may be stuck in tight loop"
                }
            elif elapsed <= self.config.window_max:
                self.last_pet = pet.timestamp
                self.miss_count = 0
                self.early_count = 0
                return {"status": "OK", "elapsed": round(elapsed, 1)}
            else:
                self.miss_count += 1
                self.last_pet = pet.timestamp
                return {"status": "LATE", "elapsed": round(elapsed, 1), "miss_count": self.miss_count}

        elif self.config.type == WatchdogType.MULTI_STAGE:
            if elapsed < self.config.window_min:
                self.early_count += 1
                self.last_pet = pet.timestamp
                return {"status": "EARLY", "elapsed": round(elapsed, 1)}
            elif elapsed <= self.config.window_max:
                self.last_pet = pet.timestamp
                self.miss_count = 0
                return {"status": "OK", "elapsed": round(elapsed, 1)}
            else:
                self.miss_count += 1
                stage_idx = min(self.miss_count - 1, len(self.config.stages) - 1)
                action = self.config.stages[stage_idx]
                self.last_pet = pet.timestamp
                return {
                    "status": "ESCALATE",
                    "elapsed": round(elapsed, 1),
                    "miss_count": self.miss_count,
                    "stage": stage_idx + 1,
                    "action": action
                }

    def check_timeout(self, now: float) -> dict:
        """Check if agent has gone silent (no pet at all)"""
        self.total_checks += 1
        elapsed = now - self.last_pet if self.last_pet > 0 else 0
        if elapsed > self.config.window_max:
            self.miss_count += 1
            if self.config.type == WatchdogType.MULTI_STAGE:
                stage_idx = min(self.miss_count - 1, len(self.config.stages) - 1)
                return {"status": "TIMEOUT", "elapsed": round(elapsed, 1), "action": self.config.stages[stage_idx]}
            return {"status": "TIMEOUT", "elapsed": round(elapsed, 1), "miss_count": self.miss_count}
        return {"status": "WAITING", "elapsed": round(elapsed, 1)}


def simulate_agent(watchdog_type: WatchdogType, behavior: str, periods: int = 50, seed: int = 42):
    """Simulate agent behavior against a watchdog"""
    random.seed(seed)
    config = WatchdogConfig(
        type=watchdog_type,
        interval=30.0,
        window_min=20.0,
        window_max=40.0,
        stages=["warning", "quarantine", "revoke"]
    )
    wd = Watchdog(config)

    caught = 0
    false_ok = 0
    t = 0.0

    for i in range(periods):
        if behavior == "healthy":
            delay = random.gauss(30.0, 3.0)  # normal heartbeat
        elif behavior == "stuck_loop":
            delay = random.gauss(5.0, 1.0)   # petting too fast (stuck)
        elif behavior == "dying":
            delay = 30.0 + i * 2.0           # getting progressively slower
        elif behavior == "intermittent":
            delay = 30.0 if random.random() > 0.3 else random.choice([5.0, 80.0])
        else:
            delay = 30.0

        t += max(delay, 1.0)
        result = wd.pet(Pet(timestamp=t))

        if behavior != "healthy":
            if result["status"] in ("EARLY", "LATE", "MISS", "ESCALATE"):
                caught += 1
            else:
                false_ok += 1
        else:
            if result["status"] not in ("OK",):
                caught += 1  # false alarm for healthy agent

    total_anomalous = caught + false_ok if behavior != "healthy" else periods
    detection_rate = caught / max(caught + false_ok, 1) if behavior != "healthy" else 1.0 - (caught / periods)

    return {
        "watchdog": watchdog_type.value,
        "behavior": behavior,
        "caught": caught,
        "missed": false_ok if behavior != "healthy" else caught,
        "detection_rate": round(detection_rate, 3),
        "early_count": wd.early_count,
        "miss_count": wd.miss_count
    }


def grade(detection_rate, is_healthy):
    if is_healthy:
        # For healthy: detection_rate = accuracy (want high = few false alarms)
        if detection_rate > 0.95: return "A"
        if detection_rate > 0.85: return "B"
        if detection_rate > 0.70: return "C"
        return "D"
    else:
        # For anomalous: detection_rate = caught rate (want high)
        if detection_rate > 0.90: return "A"
        if detection_rate > 0.70: return "B"
        if detection_rate > 0.50: return "C"
        if detection_rate > 0.30: return "D"
        return "F"


def main():
    print("=" * 60)
    print("Windowed Watchdog — Pont & Ong (2002) Patterns")
    print("=" * 60)

    behaviors = ["healthy", "stuck_loop", "dying", "intermittent"]
    types = [WatchdogType.SIMPLE, WatchdogType.WINDOWED, WatchdogType.MULTI_STAGE]

    for wtype in types:
        print(f"\n--- {wtype.value.upper()} WATCHDOG ---")
        for behavior in behaviors:
            r = simulate_agent(wtype, behavior)
            is_healthy = behavior == "healthy"
            g = grade(r["detection_rate"], is_healthy)
            if is_healthy:
                print(f"  {behavior:15s}: accuracy {r['detection_rate']:.1%} (false alarms: {r['missed']}) Grade {g}")
            else:
                print(f"  {behavior:15s}: detection {r['detection_rate']:.1%} (caught {r['caught']}/{r['caught']+r['missed']}) Grade {g}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    simple_stuck = simulate_agent(WatchdogType.SIMPLE, "stuck_loop")
    windowed_stuck = simulate_agent(WatchdogType.WINDOWED, "stuck_loop")
    print(f"  Simple vs stuck_loop:   {simple_stuck['detection_rate']:.0%} detection")
    print(f"  Windowed vs stuck_loop: {windowed_stuck['detection_rate']:.0%} detection")
    print(f"\n  Key: windowed catches 'too early' — stuck tasks petting")
    print(f"  at clock speed look healthy to simple watchdog.")
    print(f"  Multi-stage adds graduated escalation (Ostrom principle #5).")


if __name__ == "__main__":
    main()
