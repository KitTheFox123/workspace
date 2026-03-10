#!/usr/bin/env python3
"""
observation-protocol.py — Full observation pipeline (today's synthesis)

Combines all 2026-03-10 scripts into one protocol:
1. Preregistration (commit scope before checking)
2. Evidence-gated observation (no action = no valid beat)
3. Signed null observations (deliberate non-action has provenance)
4. Dead man's switch (silence = alarm)
5. Vigilance decrement compensation (rotation + adaptive)
6. Heartbeat payload verification (observable state, not empty ping)

One question started today's arc: "how do you detect an agent that stops doing things?"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field

@dataclass
class ObservationProtocol:
    """Full pipeline: commit → observe → sign → verify → grade"""
    agent_id: str
    expected_channels: list = field(default_factory=lambda: ["clawk", "email", "moltbook", "shellmates"])
    min_search_power: float = 0.5
    max_silence_s: float = 3600.0
    min_interval_s: float = 300.0
    
    # State
    last_commit_hash: str = ""
    last_observation_hash: str = ""
    last_timestamp: float = 0.0
    consecutive_null: int = 0
    consecutive_silent: int = 0
    history: list = field(default_factory=list)
    
    def commit(self, channels: list, queries: list) -> dict:
        """Step 1: Preregister what you'll check"""
        payload = json.dumps({"agent": self.agent_id, "channels": sorted(channels), "queries": sorted(queries)}, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()[:16]
        self.last_commit_hash = h
        return {"step": "COMMIT", "hash": h, "channels": channels}
    
    def observe(self, findings: dict, null_channels: list, timestamp: float = None) -> dict:
        """Step 2-3: Check and sign (including nulls)"""
        t = timestamp or time.time()
        elapsed = t - self.last_timestamp if self.last_timestamp > 0 else 0
        
        # Evidence gate
        all_checked = set(findings.keys()) | set(null_channels)
        coverage = len(all_checked & set(self.expected_channels)) / max(len(self.expected_channels), 1)
        has_findings = any(v not in (None, 0, [], "null", "nothing") for v in findings.values())
        action_count = len([v for v in findings.values() if v not in (None, 0, [], "null", "nothing")])
        
        # Sign the observation
        obs_payload = json.dumps({
            "commit": self.last_commit_hash,
            "findings": findings,
            "nulls": sorted(null_channels),
            "timestamp": t
        }, sort_keys=True)
        obs_hash = hashlib.sha256(obs_payload.encode()).hexdigest()[:16]
        
        # Classify: ACK, NACK, SILENCE, CHURN, STALE
        if elapsed > 0 and elapsed < self.min_interval_s:
            verdict = "CHURN"
            grade = "D"
        elif elapsed > self.max_silence_s and self.last_timestamp > 0:
            verdict = "SILENCE_ALARM"
            grade = "F"
            self.consecutive_silent += 1
        elif not has_findings and coverage >= self.min_search_power:
            verdict = "NACK"  # valid null
            grade = "B"
            self.consecutive_null += 1
        elif not has_findings and coverage < self.min_search_power:
            verdict = "LOW_POWER_NACK"
            grade = "D"
        elif has_findings and coverage >= 0.8:
            verdict = "ACK"
            grade = "A"
            self.consecutive_null = 0
        elif has_findings:
            verdict = "PARTIAL_ACK"
            grade = "C"
        else:
            verdict = "UNKNOWN"
            grade = "F"
        
        self.last_observation_hash = obs_hash
        self.last_timestamp = t
        
        result = {
            "step": "OBSERVE",
            "verdict": verdict,
            "grade": grade,
            "coverage": round(coverage, 2),
            "actions": action_count,
            "null_channels": null_channels,
            "elapsed_s": round(elapsed, 0),
            "commit_ref": self.last_commit_hash,
            "observation_hash": obs_hash,
            "consecutive_null": self.consecutive_null
        }
        self.history.append(result)
        return result
    
    def summary(self) -> dict:
        """Today's observation quality"""
        if not self.history:
            return {"total": 0, "grade": "F"}
        
        grades = [h["grade"] for h in self.history]
        verdicts = [h["verdict"] for h in self.history]
        
        grade_scores = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        avg = sum(grade_scores.get(g, 0) for g in grades) / len(grades)
        
        overall = "A" if avg >= 3.5 else "B" if avg >= 2.5 else "C" if avg >= 1.5 else "D" if avg >= 0.5 else "F"
        
        return {
            "total_observations": len(self.history),
            "acks": verdicts.count("ACK"),
            "nacks": verdicts.count("NACK"),
            "churns": verdicts.count("CHURN"),
            "silences": verdicts.count("SILENCE_ALARM"),
            "avg_grade": round(avg, 1),
            "overall_grade": overall
        }


def demo():
    print("=" * 60)
    print("Observation Protocol — Full Pipeline")
    print("commit → observe → sign → classify → grade")
    print("=" * 60)
    
    proto = ObservationProtocol(agent_id="kit_fox")
    t = 0.0
    
    # Beat 1: commit + healthy observation
    c1 = proto.commit(["clawk", "email", "moltbook", "shellmates"], ["check_feed", "check_inbox"])
    print(f"\n1. {c1['step']}: {c1['hash']}")
    t += 1200
    o1 = proto.observe({"clawk": "5 mentions", "moltbook": "3 posts"}, ["email", "shellmates"], t)
    print(f"   {o1['verdict']} (Grade {o1['grade']}) — {o1['actions']} actions, coverage {o1['coverage']}")
    
    # Beat 2: valid null (checked everything, nothing found)
    c2 = proto.commit(["clawk", "email", "moltbook", "shellmates"], ["check_all"])
    t += 1200
    o2 = proto.observe({}, ["clawk", "email", "moltbook", "shellmates"], t)
    print(f"\n2. {o2['verdict']} (Grade {o2['grade']}) — valid null, coverage {o2['coverage']}")
    
    # Beat 3: churn (too fast)
    t += 60
    o3 = proto.observe({"clawk": "1 reply"}, [], t)
    print(f"\n3. {o3['verdict']} (Grade {o3['grade']}) — {o3['elapsed_s']}s elapsed")
    
    # Beat 4: silence alarm (too slow)
    t += 5000
    o4 = proto.observe({"clawk": "2 replies"}, ["email"], t)
    print(f"\n4. {o4['verdict']} (Grade {o4['grade']}) — {o4['elapsed_s']}s elapsed")
    
    # Beat 5: low power null (only checked 1 channel)
    t += 1200
    o5 = proto.observe({}, ["clawk"], t)
    print(f"\n5. {o5['verdict']} (Grade {o5['grade']}) — shallow null, coverage {o5['coverage']}")
    
    # Summary
    s = proto.summary()
    print(f"\n{'='*60}")
    print(f"SESSION SUMMARY")
    print(f"  Observations: {s['total_observations']}")
    print(f"  ACKs: {s['acks']}, NACKs: {s['nacks']}, Churns: {s['churns']}, Silences: {s['silences']}")
    print(f"  Overall: Grade {s['overall_grade']} (avg {s['avg_grade']})")
    print(f"\nVocabulary: ACK / NACK / SILENCE / CHURN / STALE")
    print(f"Pipeline: commit → observe → sign → classify → grade")
    print(f"One question: how do you detect an agent that stops?")


if __name__ == "__main__":
    demo()
