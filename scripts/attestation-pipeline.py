#!/usr/bin/env python3
"""
attestation-pipeline.py — Unified attestation verification pipeline

Integrates today's tools into one flow:
1. preregistration-commit-reveal.py → scope commitment
2. signed-null-observation.py → observation signing
3. evidence-gated-attestation.py → evidence gate
4. heartbeat-payload-verifier.py → multistage watchdog
5. dead-mans-switch.py → absence detection
6. vigilance-decrement-sim.py → monitor rotation

McKinley 2015: spend innovation tokens on coordination, not transport.
This pipeline uses boring primitives (hashes, timestamps, JSON) for everything.

Pipeline: COMMIT → OBSERVE → GATE → VERIFY → SWITCH → ROTATE
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AttestationBeat:
    """A single heartbeat through the full pipeline"""
    agent_id: str
    timestamp: float
    # Preregistration
    declared_channels: list
    declared_queries: list
    # Observation
    findings: dict          # channel → result
    null_channels: list     # channels checked, nothing found
    action_count: int
    action_digest: str
    # Metadata
    scope_hash: str = ""
    memory_hash: str = ""

    def __post_init__(self):
        if not self.scope_hash:
            payload = json.dumps({"channels": sorted(self.declared_channels), "queries": sorted(self.declared_queries)}, sort_keys=True)
            self.scope_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class PipelineResult:
    stage_results: dict = field(default_factory=dict)
    final_verdict: str = "UNKNOWN"
    final_grade: str = "F"
    
    def summary(self) -> str:
        lines = []
        for stage, result in self.stage_results.items():
            lines.append(f"  {stage}: {result['verdict']} (Grade {result['grade']})")
        lines.append(f"  FINAL: {self.final_verdict} (Grade {self.final_grade})")
        return "\n".join(lines)


class AttestationPipeline:
    """6-stage attestation verification"""
    
    def __init__(self, expected_channels: list, min_search_power: float = 0.5):
        self.expected_channels = expected_channels
        self.min_search_power = min_search_power
        self.last_digest = ""
        self.last_timestamp = 0.0
        self.last_scope_hash = ""
        self.consecutive_stale = 0
        self.miss_count = 0
        self.beat_count = 0
    
    def process(self, beat: AttestationBeat) -> PipelineResult:
        result = PipelineResult()
        self.beat_count += 1
        elapsed = beat.timestamp - self.last_timestamp if self.last_timestamp > 0 else 1200
        
        # Stage 1: COMMIT — scope preregistration
        committed = set(beat.declared_channels)
        checked = set(beat.findings.keys()) | set(beat.null_channels)
        coverage = len(checked & committed) / max(len(committed), 1)
        extra = checked - committed
        
        commit_grade = "A" if coverage >= 0.8 and not extra else "C" if coverage >= 0.5 else "F"
        result.stage_results["1_COMMIT"] = {
            "verdict": "VALID" if coverage >= 0.8 else "PARTIAL",
            "grade": commit_grade,
            "coverage": round(coverage, 2),
            "p_hacking": bool(extra)
        }
        
        # Stage 2: OBSERVE — signed observation quality
        is_null = all(v in (None, 0, [], "null", "nothing", "") for v in beat.findings.values())
        if is_null and coverage >= self.min_search_power:
            obs_verdict, obs_grade = "VALID_NACK", "B"
        elif is_null and coverage < self.min_search_power:
            obs_verdict, obs_grade = "LOW_POWER_NACK", "D"
        elif not is_null:
            obs_verdict, obs_grade = "ACK", "A"
        else:
            obs_verdict, obs_grade = "SILENCE", "F"
        
        result.stage_results["2_OBSERVE"] = {
            "verdict": obs_verdict,
            "grade": obs_grade,
            "is_null": is_null,
            "search_power": round(coverage, 2)
        }
        
        # Stage 3: GATE — evidence check
        if beat.action_digest == self.last_digest and self.last_digest:
            self.consecutive_stale += 1
            gate_verdict = "STALE"
            gate_grade = "C" if self.consecutive_stale < 3 else "F"
        elif beat.action_count == 0 and not beat.null_channels:
            gate_verdict = "EMPTY"
            gate_grade = "D"
        else:
            self.consecutive_stale = 0
            gate_verdict = "FRESH"
            gate_grade = "A"
        
        result.stage_results["3_GATE"] = {
            "verdict": gate_verdict,
            "grade": gate_grade,
            "consecutive_stale": self.consecutive_stale
        }
        
        # Stage 4: VERIFY — payload checks
        checks_passed = 0
        total_checks = 3
        if beat.action_count > 0 or beat.null_channels: checks_passed += 1
        if coverage >= 0.5: checks_passed += 1
        if beat.scope_hash: checks_passed += 1
        
        verify_grade = "A" if checks_passed == 3 else "B" if checks_passed == 2 else "D"
        result.stage_results["4_VERIFY"] = {
            "verdict": f"{checks_passed}/{total_checks} checks",
            "grade": verify_grade
        }
        
        # Stage 5: SWITCH — dead man's switch
        if elapsed > 3600 and self.last_timestamp > 0:
            switch_verdict, switch_grade = "ALARM", "F"
            self.miss_count += 1
        elif elapsed > 1800 and self.last_timestamp > 0:
            switch_verdict, switch_grade = "OVERDUE", "C"
        else:
            switch_verdict, switch_grade = "OK", "A"
            self.miss_count = 0
        
        result.stage_results["5_SWITCH"] = {
            "verdict": switch_verdict,
            "grade": switch_grade,
            "elapsed": round(elapsed, 0)
        }
        
        # Stage 6: ROTATE — should monitor rotate?
        fatigue = min(self.beat_count / 10, 1.0)  # 10 beats = full fatigue
        rotate_needed = fatigue > 0.7
        result.stage_results["6_ROTATE"] = {
            "verdict": "ROTATE" if rotate_needed else "OK",
            "grade": "C" if rotate_needed else "A",
            "fatigue": round(fatigue, 2),
            "beats": self.beat_count
        }
        
        # Final verdict — worst grade wins
        grades = [r["grade"] for r in result.stage_results.values()]
        grade_order = "ABCDF"
        result.final_grade = max(grades, key=lambda g: grade_order.index(g))
        
        if result.final_grade in ("A", "B"):
            result.final_verdict = "TRUSTED"
        elif result.final_grade == "C":
            result.final_verdict = "DEGRADED"
        elif result.final_grade == "D":
            result.final_verdict = "SUSPECT"
        else:
            result.final_verdict = "UNTRUSTED"
        
        self.last_digest = beat.action_digest
        self.last_timestamp = beat.timestamp
        self.last_scope_hash = beat.scope_hash
        
        return result


def demo():
    print("=" * 60)
    print("Attestation Pipeline — 6 Stages")
    print("COMMIT → OBSERVE → GATE → VERIFY → SWITCH → ROTATE")
    print("=" * 60)
    
    pipeline = AttestationPipeline(
        expected_channels=["clawk", "email", "moltbook", "shellmates"]
    )
    t = time.time()
    
    # Beat 1: Healthy
    beat1 = AttestationBeat(
        agent_id="kit_fox", timestamp=t,
        declared_channels=["clawk", "email", "moltbook", "shellmates"],
        declared_queries=["check_feed", "check_inbox"],
        findings={"clawk": "5 mentions", "moltbook": "3 posts"},
        null_channels=["email", "shellmates"],
        action_count=8, action_digest="abc123"
    )
    r1 = pipeline.process(beat1)
    print(f"\n1. HEALTHY BEAT:")
    print(r1.summary())
    
    # Beat 2: Clawk-only (scope contraction)
    beat2 = AttestationBeat(
        agent_id="kit_fox", timestamp=t + 1200,
        declared_channels=["clawk"],
        declared_queries=["check_feed"],
        findings={"clawk": "2 replies"},
        null_channels=[],
        action_count=3, action_digest="def456"
    )
    r2 = pipeline.process(beat2)
    print(f"\n2. SCOPE CONTRACTION:")
    print(r2.summary())
    
    # Beat 3: Stale (same digest)
    beat3 = AttestationBeat(
        agent_id="kit_fox", timestamp=t + 2400,
        declared_channels=["clawk", "email", "moltbook", "shellmates"],
        declared_queries=["check_all"],
        findings={},
        null_channels=["clawk", "email", "moltbook", "shellmates"],
        action_count=0, action_digest="def456"
    )
    r3 = pipeline.process(beat3)
    print(f"\n3. STALE + NULL:")
    print(r3.summary())
    
    print(f"\n{'='*60}")
    print("6 stages, 6 scripts, 1 pipeline.")
    print("Boring primitives (hashes, timestamps, JSON).")
    print("McKinley 2015: spend tokens on coordination, not transport.")


if __name__ == "__main__":
    demo()
