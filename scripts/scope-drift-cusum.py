#!/usr/bin/env python3
"""
scope-drift-cusum.py — Detect behavioral drift in agent heartbeat logs using CUSUM.

Reads daily memory files, extracts action distributions per heartbeat,
computes KL divergence from baseline, and runs CUSUM to detect drift points.

Usage: python3 scope-drift-cusum.py [--baseline N] [--threshold SIGMA] [memory_dir]
"""

import argparse
import re
import sys
import math
from pathlib import Path
from collections import Counter
from dataclasses import dataclass


@dataclass
class HeartbeatVector:
    """Action distribution for a single heartbeat."""
    timestamp: str
    platform: int = 0  # social platform actions
    build: int = 0     # code/script/tool actions
    research: int = 0  # search/read/learn actions
    idle: int = 0      # no action taken

    @property
    def total(self) -> int:
        return self.platform + self.build + self.research + self.idle or 1

    @property
    def distribution(self) -> list[float]:
        t = self.total
        return [self.platform / t, self.build / t, self.research / t, self.idle / t]


def kl_divergence(p: list[float], q: list[float], epsilon: float = 1e-10) -> float:
    """KL(P || Q) with smoothing."""
    return sum(
        pi * math.log((pi + epsilon) / (qi + epsilon))
        for pi, qi in zip(p, q)
    )


def parse_heartbeat_entries(text: str) -> list[HeartbeatVector]:
    """Extract heartbeat vectors from daily memory file."""
    vectors = []
    # Match headers like "## HH:MM UTC" or "## HH:MM UTC — description"
    sections = re.split(r'^## (\d{1,2}:\d{2}\s*(?:UTC)?)', text, flags=re.MULTILINE)

    for i in range(1, len(sections) - 1, 2):
        ts = sections[i].strip()
        body = sections[i + 1].lower()

        v = HeartbeatVector(timestamp=ts)

        # Count action types by keyword
        platform_kw = ['clawk', 'moltbook', 'shellmates', 'reply', 'comment', 'post', 'like', 'dm', 'follow']
        build_kw = ['built', 'script', 'tool', 'commit', 'push', 'code', 'install', 'create']
        research_kw = ['keenable', 'search', 'research', 'paper', 'read', 'fetch', 'arxiv']

        for kw in platform_kw:
            v.platform += body.count(kw)
        for kw in build_kw:
            v.build += body.count(kw)
        for kw in research_kw:
            v.research += body.count(kw)

        if v.total == 1:  # nothing detected
            v.idle = 1

        vectors.append(v)

    return vectors


def run_cusum(values: list[float], threshold: float, drift: float = 0.0) -> list[tuple[int, float]]:
    """
    Run one-sided CUSUM on values.
    Returns list of (index, cusum_value) where threshold exceeded.
    """
    s_high = 0.0
    alerts = []
    for i, v in enumerate(values):
        s_high = max(0, s_high + v - drift)
        if s_high > threshold:
            alerts.append((i, s_high))
            s_high = 0.0  # reset after alert
    return alerts


def main():
    parser = argparse.ArgumentParser(description="CUSUM drift detector for agent heartbeats")
    parser.add_argument('memory_dir', nargs='?', default=str(Path.home() / '.openclaw/workspace/memory'))
    parser.add_argument('--baseline', type=int, default=5, help='Number of initial heartbeats for baseline')
    parser.add_argument('--threshold', type=float, default=3.0, help='Sigma multiplier for alert threshold')
    parser.add_argument('--date', type=str, default=None, help='Specific date file (YYYY-MM-DD)')
    args = parser.parse_args()

    memory_dir = Path(args.memory_dir)

    if args.date:
        files = [memory_dir / f"{args.date}.md"]
    else:
        files = sorted(memory_dir.glob("20??-??-??.md"))[-7:]  # last 7 days

    all_vectors = []
    for f in files:
        if f.exists():
            text = f.read_text()
            vectors = parse_heartbeat_entries(text)
            for v in vectors:
                v.timestamp = f"{f.stem} {v.timestamp}"
            all_vectors.extend(vectors)

    if len(all_vectors) < args.baseline + 1:
        print(f"Need at least {args.baseline + 1} heartbeats, found {len(all_vectors)}")
        sys.exit(1)

    # Compute baseline distribution (mean of first N)
    baseline = [0.0, 0.0, 0.0, 0.0]
    for v in all_vectors[:args.baseline]:
        d = v.distribution
        for j in range(4):
            baseline[j] += d[j] / args.baseline

    print(f"Baseline ({args.baseline} beats): platform={baseline[0]:.2f} build={baseline[1]:.2f} "
          f"research={baseline[2]:.2f} idle={baseline[3]:.2f}")
    print(f"Total heartbeats: {len(all_vectors)}")
    print()

    # Compute KL divergence series
    kl_values = []
    for v in all_vectors:
        kl = kl_divergence(v.distribution, baseline)
        kl_values.append(kl)

    # Stats for threshold
    mean_kl = sum(kl_values) / len(kl_values)
    var_kl = sum((k - mean_kl) ** 2 for k in kl_values) / len(kl_values)
    std_kl = math.sqrt(var_kl) if var_kl > 0 else 0.01
    threshold = mean_kl + args.threshold * std_kl

    print(f"KL stats: mean={mean_kl:.4f} std={std_kl:.4f} threshold={threshold:.4f}")
    print()

    # Run CUSUM
    alerts = run_cusum(kl_values, threshold, drift=mean_kl)

    if alerts:
        print(f"⚠️  DRIFT DETECTED at {len(alerts)} point(s):")
        for idx, val in alerts:
            v = all_vectors[idx]
            print(f"  [{v.timestamp}] CUSUM={val:.4f} dist={v.distribution} KL={kl_values[idx]:.4f}")
    else:
        print("✅ No drift detected.")

    # Summary per-beat
    print("\n--- Per-beat breakdown ---")
    start = max(0, len(all_vectors) - 10)
    for i, v in enumerate(all_vectors[start:]):
        idx = start + i
        marker = " ⚠️" if any(a[0] == idx for a in alerts) else ""
        print(f"  {v.timestamp}: P={v.platform} B={v.build} R={v.research} I={v.idle} "
              f"KL={kl_values[idx]:.4f}{marker}")


if __name__ == "__main__":
    main()
