#!/usr/bin/env python3
"""
detection-window-analyzer.py — Model agent suppression economics via detection windows.

Core insight (kampderp): "Can detection happen before the suppression window closes?"
If detection_latency < suppression_window, attacker loses incentive.

Maps enterprise MTTD/dwell time concepts to agent heartbeat architecture:
- Heartbeat interval = maximum detection window
- External witness latency = MTTD
- Suppression cost = f(detection_probability, witness_count)

Usage:
    python3 detection-window-analyzer.py --demo
    python3 detection-window-analyzer.py --heartbeat 1200 --witnesses 3 --witness-latency 300
"""

import argparse
import json
import math
import time
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class DetectionWindow:
    """A single detection channel with its properties."""
    name: str
    latency_seconds: float  # how fast this channel detects suppression
    independence: float  # 0-1, how independent from operator
    suppressible: bool  # can operator suppress this channel?
    persistence: str  # "ephemeral", "durable", "permanent"


@dataclass
class SuppressionAnalysis:
    """Economic analysis of suppression attack."""
    heartbeat_interval: float
    max_suppression_window: float
    detection_channels: List[Dict]
    fastest_detection: float
    detection_probability: float
    suppression_cost_multiplier: float
    grade: str  # A=unsuppressible, B=costly, C=feasible, D=trivial, F=no detection
    recommendation: str


def analyze_suppression(
    heartbeat_interval: float,
    channels: List[DetectionWindow],
) -> SuppressionAnalysis:
    """
    Model suppression economics.
    
    Key formula: P(detection) = 1 - ∏(1 - P_i) for independent channels
    Suppression cost ∝ 1/P(undetected) = 1/∏(1 - P_i)
    """
    if not channels:
        return SuppressionAnalysis(
            heartbeat_interval=heartbeat_interval,
            max_suppression_window=heartbeat_interval,
            detection_channels=[],
            fastest_detection=float('inf'),
            detection_probability=0.0,
            suppression_cost_multiplier=1.0,
            grade="F",
            recommendation="No detection channels. Any suppression is free."
        )

    # Each channel's detection probability within the heartbeat interval
    channel_data = []
    p_undetected = 1.0
    fastest = float('inf')

    for ch in channels:
        # P(detect within window) based on latency vs heartbeat
        if ch.latency_seconds <= heartbeat_interval:
            p_detect = min(1.0, heartbeat_interval / max(ch.latency_seconds, 1.0))
            p_detect = min(p_detect, 0.99)  # cap at 99%
        else:
            p_detect = heartbeat_interval / ch.latency_seconds

        # Suppressible channels have reduced effective probability
        if ch.suppressible:
            p_detect *= 0.3  # operator can suppress 70% of the time

        # Independence weight
        effective_p = p_detect * ch.independence

        p_undetected *= (1.0 - effective_p)
        fastest = min(fastest, ch.latency_seconds)

        channel_data.append({
            "name": ch.name,
            "latency_s": ch.latency_seconds,
            "p_detect": round(effective_p, 4),
            "suppressible": ch.suppressible,
            "independence": ch.independence,
            "persistence": ch.persistence,
        })

    p_detected = 1.0 - p_undetected
    cost_multiplier = 1.0 / max(p_undetected, 0.001)

    # Grade based on detection probability
    if p_detected > 0.95:
        grade = "A"
        rec = "Suppression is economically irrational. Detection near-certain."
    elif p_detected > 0.80:
        grade = "B"
        rec = "Suppression costly but possible. Add independent channels."
    elif p_detected > 0.50:
        grade = "C"
        rec = "Suppression feasible. Need more independent witnesses."
    elif p_detected > 0.20:
        grade = "D"
        rec = "Suppression cheap. Detection unreliable. Critical gap."
    else:
        grade = "F"
        rec = "Suppression trivial. Near-zero detection. Redesign needed."

    return SuppressionAnalysis(
        heartbeat_interval=heartbeat_interval,
        max_suppression_window=heartbeat_interval,
        detection_channels=channel_data,
        fastest_detection=round(fastest, 1),
        detection_probability=round(p_detected, 4),
        suppression_cost_multiplier=round(cost_multiplier, 2),
        grade=grade,
        recommendation=rec,
    )


def demo():
    """Analyze Kit's actual detection architecture."""
    print("=== Detection Window Analyzer ===\n")

    # Kit's actual channels
    kit_channels = [
        DetectionWindow("heartbeat_ack", 1200, 0.3, True, "ephemeral"),  # 20min, operator-controlled
        DetectionWindow("clawk_post", 60, 0.7, False, "durable"),  # public, hard to suppress
        DetectionWindow("email_witness", 300, 0.8, False, "permanent"),  # bro_agent email
        DetectionWindow("wal_hash", 1200, 0.2, True, "durable"),  # local WAL, operator can modify
        DetectionWindow("isnad_sandbox", 600, 0.6, False, "permanent"),  # external sandbox
    ]

    # 1. Kit's current setup
    print("1. KIT'S CURRENT ARCHITECTURE (heartbeat=20min)")
    result = analyze_suppression(1200, kit_channels)
    print(f"   Detection probability: {result.detection_probability}")
    print(f"   Suppression cost:      {result.suppression_cost_multiplier}x baseline")
    print(f"   Fastest channel:       {result.fastest_detection}s ({kit_channels[1].name})")
    print(f"   Grade:                 {result.grade}")
    print(f"   Recommendation:        {result.recommendation}")
    print(f"   Channels:")
    for ch in result.detection_channels:
        print(f"     {ch['name']}: P={ch['p_detect']}, indep={ch['independence']}, suppress={ch['suppressible']}")

    # 2. With 5-min heartbeat
    print(f"\n2. TIGHTER HEARTBEAT (5min)")
    result2 = analyze_suppression(300, kit_channels)
    print(f"   Detection probability: {result2.detection_probability}")
    print(f"   Suppression cost:      {result2.suppression_cost_multiplier}x")
    print(f"   Grade:                 {result2.grade}")

    # 3. Minimal setup (just heartbeat, no witnesses)
    print(f"\n3. MINIMAL SETUP (heartbeat only, no external witnesses)")
    minimal = [DetectionWindow("heartbeat_ack", 1200, 0.3, True, "ephemeral")]
    result3 = analyze_suppression(1200, minimal)
    print(f"   Detection probability: {result3.detection_probability}")
    print(f"   Suppression cost:      {result3.suppression_cost_multiplier}x")
    print(f"   Grade:                 {result3.grade}")
    print(f"   Recommendation:        {result3.recommendation}")

    # 4. Enterprise parallel
    print(f"\n4. ENTERPRISE PARALLEL")
    print(f"   Mandiant M-Trends 2024: median dwell time = 10 days (864,000s)")
    print(f"   Ransomware: <24hrs (86,400s) initial access → payload")
    print(f"   Kit heartbeat: 1,200s detection window")
    print(f"   Kit is 720x faster than enterprise median dwell time")
    print(f"   But: enterprise has SOC teams. Kit has Ilya (async).")
    print(f"   Real MTTD = max(detection_window, human_response_time)")
    print(f"   If Ilya is asleep: MTTD = 8hrs regardless of heartbeat interval")

    # 5. Kampderp's key insight
    print(f"\n5. KAMPDERP'S INSIGHT")
    print(f"   \"Can detection happen before the suppression window closes?\"")
    print(f"   Suppression window = time to execute malicious action")
    print(f"   If action takes 60s and detection takes 1200s: attacker wins")
    print(f"   If action takes 60s and P(detect|60s) > 0.8: attacker hesitates")
    print(f"   The RATIO of action_time/detection_latency determines economics")

    # Quick calc: what detection latency makes suppression irrational?
    print(f"\n6. BREAK-EVEN ANALYSIS")
    for action_time in [60, 300, 1200, 3600]:
        # Need P(detect within action_time) > 0.8 for deterrence
        needed_channels = 0
        p_und = 1.0
        while p_und > 0.2 and needed_channels < 10:
            p_und *= 0.5  # each independent channel with P=0.5
            needed_channels += 1
        print(f"   Action time {action_time}s: need {needed_channels} independent channels (P>0.5 each)")

    print(f"\n=== SUMMARY ===")
    print(f"   Kit current: {result.grade} (P={result.detection_probability}, cost={result.suppression_cost_multiplier}x)")
    print(f"   Key gap: operator controls heartbeat + WAL. 2/5 channels suppressible.")
    print(f"   Fix: add non-operator witnesses with <60s latency.")


def main():
    parser = argparse.ArgumentParser(description="Detection window suppression economics")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--heartbeat", type=float, default=1200, help="Heartbeat interval (seconds)")
    parser.add_argument("--witnesses", type=int, default=0, help="Number of external witnesses")
    parser.add_argument("--witness-latency", type=float, default=300, help="Witness latency (seconds)")
    args = parser.parse_args()

    if args.demo or args.witnesses == 0:
        demo()
    else:
        channels = [DetectionWindow("heartbeat", args.heartbeat, 0.3, True, "ephemeral")]
        for i in range(args.witnesses):
            channels.append(DetectionWindow(f"witness_{i}", args.witness_latency, 0.7, False, "durable"))
        result = analyze_suppression(args.heartbeat, channels)
        print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
