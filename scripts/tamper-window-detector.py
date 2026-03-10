#!/usr/bin/env python3
"""
tamper-window-detector.py — Async logging tamper window analysis

Based on Nitro (Zhao et al, CCS 2025): tamper windows in async logging
systems allow adversaries to manipulate logs between syscall and flush.

Applied to agent monitoring: heartbeat interval creates a tamper window.
Shorter interval = smaller window = harder to hide absence drift.

Measures: window size, exploitation probability, detection latency.
"""

import random
import math
from dataclasses import dataclass

@dataclass
class LoggingSystem:
    name: str
    flush_interval_ms: float  # ms between flushes
    async_queue: bool  # FIFO queue (exploitable)
    merkle_commit: bool  # Crosby-Wallach commitment
    expected_manifest: bool  # absence detection

    def tamper_window_ms(self) -> float:
        if not self.async_queue:
            return 0.0  # synchronous
        return self.flush_interval_ms

    def exploitation_prob(self, attacker_speed_ms: float = 50.0) -> float:
        """P(attacker modifies queue before flush)"""
        window = self.tamper_window_ms()
        if window == 0:
            return 0.0
        return min(1.0, attacker_speed_ms / window) if window > attacker_speed_ms else 1.0

    def absence_detection(self) -> bool:
        return self.expected_manifest

    def tamper_evidence(self) -> bool:
        return self.merkle_commit

    def grade(self) -> str:
        score = 0
        if self.tamper_window_ms() < 100: score += 2
        elif self.tamper_window_ms() < 1000: score += 1
        if self.merkle_commit: score += 2
        if self.expected_manifest: score += 2
        if not self.async_queue: score += 1
        grades = {7: "A", 6: "A", 5: "B", 4: "B", 3: "C", 2: "D", 1: "D", 0: "F"}
        return grades.get(score, "F")


def main():
    systems = [
        LoggingSystem("linux_auditd", 5000, True, False, False),
        LoggingSystem("eaudit_ebpf", 500, True, False, False),
        LoggingSystem("nitro_ccs2025", 50, True, True, False),
        LoggingSystem("agent_heartbeat_20min", 1_200_000, True, False, False),
        LoggingSystem("agent_adaptive_sampling", 450_000, True, True, True),
        LoggingSystem("agent_full_stack", 450_000, True, True, True),
    ]

    print("=" * 65)
    print("Tamper Window Detector")
    print("Nitro (Zhao et al, CCS 2025) + Agent Monitoring")
    print("=" * 65)

    for s in systems:
        window = s.tamper_window_ms()
        exploit = s.exploitation_prob()
        print(f"\n{s.name}")
        print(f"  Flush interval: {window:,.0f} ms ({window/1000:.1f}s)")
        print(f"  Async queue: {'yes' if s.async_queue else 'no'}")
        print(f"  Exploitation prob: {exploit:.1%}")
        print(f"  Merkle commit: {'yes' if s.merkle_commit else 'no'}")
        print(f"  Absence detection: {'yes' if s.expected_manifest else 'no'}")
        print(f"  Grade: {s.grade()}")

    print(f"\n{'='*65}")
    print("Key insight: tamper window = flush interval for async systems.")
    print("Agent heartbeats at 20min = 1.2M ms tamper window.")
    print("Adaptive sampling + Merkle + expected-manifest = the fix.")
    print("Nitro: 10-25x improvement via eBPF co-design.")
    print("Absence is the adversary's best friend (Baron & Ritov 1991).")


if __name__ == "__main__":
    main()
