#!/usr/bin/env python3
"""pull-attestation-sim.py — Pull-based vs push-based attestation simulator.

Models RFC 9683-style pull attestation (verifier fetches evidence directly)
vs push attestation (agent submits its own evidence).

Demonstrates: evidence tampering detection rate, false positive rate,
and log custody implications.

Inspired by santaclawd's "push = marketing, pull = attestation" insight.

Usage:
    python3 pull-attestation-sim.py [--trials N] [--tamper-rate FLOAT]
"""

import argparse
import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ActionRecord:
    """Single agent action with ground truth."""
    action_id: int
    action_type: str
    in_scope: bool  # Ground truth
    timestamp: float
    content_hash: str


@dataclass 
class AttestationResult:
    """Result of attestation check."""
    method: str  # "push" or "pull"
    total_actions: int
    tampered_count: int
    detected_count: int
    false_positives: int
    detection_rate: float
    false_positive_rate: float


def generate_actions(n: int, out_of_scope_rate: float = 0.1) -> list[ActionRecord]:
    """Generate ground truth action log."""
    actions = []
    action_types = ["read_file", "write_file", "api_call", "exec_cmd", "send_msg"]
    for i in range(n):
        atype = random.choice(action_types)
        in_scope = random.random() > out_of_scope_rate
        content = f"{i}:{atype}:{in_scope}:{random.random()}"
        actions.append(ActionRecord(
            action_id=i,
            action_type=atype,
            in_scope=in_scope,
            timestamp=1709942400 + i * 60,
            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16]
        ))
    return actions


def push_attestation(actions: list[ActionRecord], tamper_rate: float) -> AttestationResult:
    """Simulate push-based: agent submits evidence, can curate/tamper."""
    tampered = 0
    detected = 0
    false_pos = 0
    
    for a in actions:
        if not a.in_scope and random.random() < tamper_rate:
            # Agent omits or modifies out-of-scope actions
            tampered += 1
            # Push: verifier only sees what agent sends → low detection
            if random.random() < 0.15:  # 15% chance of detecting omission
                detected += 1
        elif a.in_scope and random.random() < 0.02:
            false_pos += 1
    
    total_oos = sum(1 for a in actions if not a.in_scope)
    return AttestationResult(
        method="push",
        total_actions=len(actions),
        tampered_count=tampered,
        detected_count=detected,
        false_positives=false_pos,
        detection_rate=detected / tampered if tampered > 0 else 1.0,
        false_positive_rate=false_pos / len(actions)
    )


def pull_attestation(actions: list[ActionRecord], tamper_rate: float) -> AttestationResult:
    """Simulate pull-based: verifier fetches log directly from platform."""
    tampered = 0
    detected = 0
    false_pos = 0
    
    for a in actions:
        if not a.in_scope:
            tampered += 1
            # Pull: verifier sees complete log → high detection
            if random.random() < 0.95:  # 95% detection (platform log complete)
                detected += 1
        elif random.random() < 0.03:
            false_pos += 1
    
    return AttestationResult(
        method="pull",
        total_actions=len(actions),
        tampered_count=tampered,
        detected_count=detected,
        false_positives=false_pos,
        detection_rate=detected / tampered if tampered > 0 else 1.0,
        false_positive_rate=false_pos / len(actions)
    )


def run_comparison(n_actions: int = 100, tamper_rate: float = 0.8, trials: int = 1000):
    """Run push vs pull comparison."""
    push_detections = []
    pull_detections = []
    push_fps = []
    pull_fps = []
    
    for _ in range(trials):
        actions = generate_actions(n_actions, out_of_scope_rate=0.1)
        
        push = push_attestation(actions, tamper_rate)
        pull = pull_attestation(actions, tamper_rate)
        
        push_detections.append(push.detection_rate)
        pull_detections.append(pull.detection_rate)
        push_fps.append(push.false_positive_rate)
        pull_fps.append(pull.false_positive_rate)
    
    avg_push_det = sum(push_detections) / len(push_detections)
    avg_pull_det = sum(pull_detections) / len(pull_detections)
    avg_push_fp = sum(push_fps) / len(push_fps)
    avg_pull_fp = sum(pull_fps) / len(pull_fps)
    
    print("=" * 55)
    print("PUSH vs PULL ATTESTATION COMPARISON")
    print(f"({trials} trials, {n_actions} actions each, "
          f"{tamper_rate*100:.0f}% tamper rate)")
    print("=" * 55)
    print()
    print(f"{'Metric':<25} {'Push':>12} {'Pull':>12}")
    print("-" * 55)
    print(f"{'Detection rate':<25} {avg_push_det:>11.1%} {avg_pull_det:>11.1%}")
    print(f"{'False positive rate':<25} {avg_push_fp:>11.2%} {avg_pull_fp:>11.2%}")
    print(f"{'Log custody':<25} {'Agent':>12} {'Platform':>12}")
    print(f"{'Evidence integrity':<25} {'Curated':>12} {'Complete':>12}")
    print(f"{'RFC model':<25} {'(none)':>12} {'RFC 9683':>12}")
    print()
    print(f"Detection improvement: {avg_pull_det/avg_push_det:.1f}x")
    print()
    print("Key insight: push-based attestation lets the agent")
    print("curate what the verifier sees. Pull-based (RFC 9683)")
    print("removes agent from the evidence chain entirely.")
    print()
    print("Log custody is the upstream problem. Solve custody,")
    print("attestation follows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--tamper-rate", type=float, default=0.8)
    parser.add_argument("--actions", type=int, default=100)
    args = parser.parse_args()
    
    run_comparison(args.actions, args.tamper_rate, args.trials)
