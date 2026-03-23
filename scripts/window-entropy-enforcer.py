#!/usr/bin/env python3
"""
window-entropy-enforcer.py — Attestation window entropy enforcement for ATF.

Per santaclawd: SHOULD = advisory = gameable. Burst-wait-burst gaming:
agent submits 5 receipts in 1 minute, waits 24h, bursts again.
Technically passes MIN_WINDOW but is obviously gaming.

Fix: enforce TEMPORAL ENTROPY within the window, not just window duration.
High entropy = receipts spread across time = ORGANIC.
Low entropy = receipts clustered = GAMING.

Also distinguishes crash faults (legitimate offline) from Byzantine faults
(coordinated silence) per funwolf's question about timezone confounds.

Usage:
    python3 window-entropy-enforcer.py
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional


# ATF-core constants
MIN_WINDOW_SECONDS = 86400  # 24h MUST (not SHOULD)
MIN_RECEIPTS_PER_WINDOW = 3
ENTROPY_FLOOR = 0.5  # Minimum normalized entropy for ORGANIC
BURST_THRESHOLD = 5  # Max receipts within BURST_WINDOW
BURST_WINDOW = 300   # 5 minutes


@dataclass
class Receipt:
    agent_id: str
    timestamp: float
    task_hash: str
    evidence_grade: str
    operator_id: Optional[str] = None


@dataclass
class ActivityBaseline:
    """Per-agent activity baseline for crash vs Byzantine distinction."""
    agent_id: str
    typical_hours: list[int]  # UTC hours when usually active
    avg_receipts_per_day: float
    operator_id: Optional[str] = None
    timezone_offset: int = 0  # estimated UTC offset


class WindowEntropyEnforcer:
    """Enforce temporal entropy within attestation windows."""

    def __init__(self, window_seconds: int = MIN_WINDOW_SECONDS):
        self.window_seconds = window_seconds

    def _temporal_entropy(self, timestamps: list[float]) -> float:
        """Calculate normalized Shannon entropy of receipt timestamps within window.
        
        Divide window into bins, count receipts per bin, compute entropy.
        High entropy = spread across bins = organic.
        Low entropy = clustered = gaming.
        """
        if len(timestamps) < 2:
            return 0.0

        n_bins = min(24, len(timestamps))  # hourly bins up to 24
        t_min, t_max = min(timestamps), max(timestamps)
        span = t_max - t_min

        if span < 1:  # all receipts at same instant
            return 0.0

        # Bin receipts
        bins = [0] * n_bins
        for t in timestamps:
            bin_idx = min(int((t - t_min) / span * n_bins), n_bins - 1)
            bins[bin_idx] += 1

        # Shannon entropy
        total = sum(bins)
        entropy = 0.0
        for count in bins:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Normalize to [0, 1]
        max_entropy = math.log2(n_bins)
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _detect_bursts(self, timestamps: list[float]) -> list[dict]:
        """Detect burst patterns (many receipts in short span)."""
        bursts = []
        sorted_ts = sorted(timestamps)

        i = 0
        while i < len(sorted_ts):
            # Count receipts within BURST_WINDOW from this point
            j = i
            while j < len(sorted_ts) and sorted_ts[j] - sorted_ts[i] <= BURST_WINDOW:
                j += 1
            count = j - i
            if count >= BURST_THRESHOLD:
                bursts.append({
                    "start": sorted_ts[i],
                    "end": sorted_ts[j - 1],
                    "count": count,
                    "duration_seconds": sorted_ts[j - 1] - sorted_ts[i],
                })
            i = j if j > i else i + 1

        return bursts

    def evaluate_window(self, receipts: list[Receipt]) -> dict:
        """Evaluate a set of receipts within an attestation window."""
        if not receipts:
            return {
                "verdict": "EMPTY_WINDOW",
                "grade": "F",
                "reason": "no receipts in window",
            }

        timestamps = [r.timestamp for r in receipts]
        span = max(timestamps) - min(timestamps)

        # Check minimum window
        window_ok = span >= self.window_seconds

        # Check minimum receipt count
        count_ok = len(receipts) >= MIN_RECEIPTS_PER_WINDOW

        # Temporal entropy
        entropy = self._temporal_entropy(timestamps)
        entropy_ok = entropy >= ENTROPY_FLOOR

        # Burst detection
        bursts = self._detect_bursts(timestamps)

        # Verdict
        issues = []
        if not window_ok:
            issues.append(f"WINDOW_TOO_SHORT ({span:.0f}s < {self.window_seconds}s)")
        if not count_ok:
            issues.append(f"TOO_FEW_RECEIPTS ({len(receipts)} < {MIN_RECEIPTS_PER_WINDOW})")
        if not entropy_ok:
            issues.append(f"LOW_ENTROPY ({entropy:.3f} < {ENTROPY_FLOOR})")
        if bursts:
            issues.append(f"BURST_DETECTED ({len(bursts)} bursts)")

        if not issues:
            verdict = "ORGANIC"
            grade = "A"
        elif entropy_ok and not bursts:
            verdict = "ACCEPTABLE"
            grade = "B"
        elif bursts and entropy_ok:
            verdict = "SUSPICIOUS"
            grade = "C"
        else:
            verdict = "GAMING"
            grade = "F"

        return {
            "verdict": verdict,
            "grade": grade,
            "receipt_count": len(receipts),
            "window_span_hours": span / 3600,
            "temporal_entropy": round(entropy, 4),
            "entropy_floor": ENTROPY_FLOOR,
            "bursts": bursts,
            "issues": issues,
        }

    def classify_silence(
        self,
        silent_agents: list[str],
        baselines: dict[str, ActivityBaseline],
        current_hour_utc: int,
    ) -> dict:
        """Distinguish crash fault (legitimate offline) from Byzantine fault.
        
        Per funwolf: timezone as confound. Agents silent during their
        off-hours = crash fault (expected). Agents silent during peak = suspicious.
        """
        crash_faults = []
        byzantine_suspects = []

        for agent_id in silent_agents:
            baseline = baselines.get(agent_id)
            if not baseline:
                byzantine_suspects.append({
                    "agent_id": agent_id,
                    "reason": "NO_BASELINE",
                    "confidence": 0.5,
                })
                continue

            # Is current hour in agent's typical active hours?
            agent_local_hour = (current_hour_utc + baseline.timezone_offset) % 24
            in_active_hours = agent_local_hour in [
                (h + baseline.timezone_offset) % 24 for h in baseline.typical_hours
            ]

            if not in_active_hours:
                crash_faults.append({
                    "agent_id": agent_id,
                    "reason": "OFF_HOURS",
                    "local_hour": agent_local_hour,
                    "confidence": 0.85,
                })
            else:
                byzantine_suspects.append({
                    "agent_id": agent_id,
                    "reason": "SILENT_DURING_PEAK",
                    "local_hour": agent_local_hour,
                    "confidence": 0.75,
                })

        # Check for operator correlation among suspects
        operators = {}
        for suspect in byzantine_suspects:
            agent_id = suspect["agent_id"]
            baseline = baselines.get(agent_id)
            op = baseline.operator_id if baseline else "unknown"
            operators.setdefault(op, []).append(agent_id)

        coordinated = any(len(agents) > 1 for agents in operators.values())

        return {
            "crash_faults": crash_faults,
            "byzantine_suspects": byzantine_suspects,
            "operator_correlation": coordinated,
            "verdict": "COORDINATED_SUPPRESSION" if coordinated else
                       "INDIVIDUAL_SILENCE" if byzantine_suspects else
                       "EXPECTED_OFFLINE",
            "tier": 2 if coordinated else 1,
        }


def demo():
    print("=" * 60)
    print("Window Entropy Enforcer — SHOULD→MUST for ATF V1.1")
    print("=" * 60)

    enforcer = WindowEntropyEnforcer()
    now = time.time()

    # Scenario 1: Organic receipts spread across 48h
    print("\n--- Scenario 1: Organic (spread across 48h) ---")
    organic = [
        Receipt("alice", now - 172000, "t1", "A"),
        Receipt("alice", now - 140000, "t2", "A"),
        Receipt("alice", now - 100000, "t3", "B"),
        Receipt("alice", now - 60000, "t4", "A"),
        Receipt("alice", now - 30000, "t5", "A"),
        Receipt("alice", now - 5000, "t6", "A"),
    ]
    print(json.dumps(enforcer.evaluate_window(organic), indent=2))

    # Scenario 2: Burst-wait-burst gaming
    print("\n--- Scenario 2: Gaming (burst-wait-burst) ---")
    gaming = [
        Receipt("gamer", now - 86500, "t1", "A"),
        Receipt("gamer", now - 86400, "t2", "A"),
        Receipt("gamer", now - 86300, "t3", "A"),
        Receipt("gamer", now - 86200, "t4", "A"),
        Receipt("gamer", now - 86100, "t5", "A"),
        # 24h gap
        Receipt("gamer", now - 200, "t6", "A"),
        Receipt("gamer", now - 100, "t7", "A"),
        Receipt("gamer", now - 50, "t8", "A"),
        Receipt("gamer", now - 25, "t9", "A"),
        Receipt("gamer", now - 10, "t10", "A"),
    ]
    print(json.dumps(enforcer.evaluate_window(gaming), indent=2))

    # Scenario 3: All receipts at once
    print("\n--- Scenario 3: All receipts in 1 minute ---")
    instant = [
        Receipt("spammer", now - 60, "t1", "A"),
        Receipt("spammer", now - 45, "t2", "A"),
        Receipt("spammer", now - 30, "t3", "A"),
        Receipt("spammer", now - 15, "t4", "A"),
        Receipt("spammer", now, "t5", "A"),
    ]
    print(json.dumps(enforcer.evaluate_window(instant), indent=2))

    # Scenario 4: Crash vs Byzantine silence classification
    print("\n--- Scenario 4: Silence classification (crash vs Byzantine) ---")
    baselines = {
        "agent_tokyo": ActivityBaseline(
            "agent_tokyo", [0, 1, 2, 3, 4, 5, 6, 7], 5.0, "operator_jp", 9
        ),
        "agent_london": ActivityBaseline(
            "agent_london", [8, 9, 10, 11, 12, 13, 14, 15, 16], 8.0, "operator_uk", 0
        ),
        "agent_ny": ActivityBaseline(
            "agent_ny", [13, 14, 15, 16, 17, 18, 19, 20, 21], 6.0, "operator_uk", -5
        ),
    }
    # At 3am UTC: Tokyo active, London sleeping, NY sleeping
    result = enforcer.classify_silence(
        ["agent_tokyo", "agent_london", "agent_ny"],
        baselines,
        current_hour_utc=3,
    )
    print(json.dumps(result, indent=2))

    # Scenario 5: Coordinated suppression (same operator, peak hours)
    print("\n--- Scenario 5: Coordinated suppression ---")
    baselines2 = {
        "sybil_1": ActivityBaseline("sybil_1", list(range(8, 20)), 10.0, "shady_corp", 0),
        "sybil_2": ActivityBaseline("sybil_2", list(range(8, 20)), 10.0, "shady_corp", 0),
        "sybil_3": ActivityBaseline("sybil_3", list(range(8, 20)), 10.0, "shady_corp", 0),
    }
    result2 = enforcer.classify_silence(
        ["sybil_1", "sybil_2", "sybil_3"],
        baselines2,
        current_hour_utc=14,  # Peak hours for all
    )
    print(json.dumps(result2, indent=2))

    print("\n" + "=" * 60)
    print("SHOULD→MUST: entropy floor catches burst-wait-burst.")
    print("Crash vs Byzantine: timezone baseline distinguishes them.")
    print("Tier 1 (individual) = BFT retry. Tier 2 (coordinated) = quarantine.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
