#!/usr/bin/env python3
"""
remediation-tracker.py — Track detection→containment→fix→verify as first-class attestation events.

Inspired by cassian's HygieneProof insight: the fix IS an attestation event.
Maps to incident response MTTD→MTTC→MTTR→verify pipeline.

Each incident produces a chain: DETECT → CONTAIN → FIX → VERIFY
Missing stages are gaps. Gaps degrade trust.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Stage(Enum):
    DETECT = "detect"
    CONTAIN = "contain"
    FIX = "fix"
    VERIFY = "verify"


STAGE_ORDER = [Stage.DETECT, Stage.CONTAIN, Stage.FIX, Stage.VERIFY]


@dataclass
class RemediationEvent:
    incident_id: str
    stage: Stage
    timestamp: float
    agent_id: str
    evidence_hash: str  # hash of evidence payload
    parent_hash: Optional[str] = None
    event_hash: str = ""

    def __post_init__(self):
        payload = f"{self.incident_id}:{self.stage.value}:{self.timestamp}:{self.agent_id}:{self.evidence_hash}:{self.parent_hash or 'root'}"
        self.event_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Incident:
    incident_id: str
    events: list = field(default_factory=list)
    
    def add_event(self, stage: Stage, agent_id: str, evidence: str, timestamp: float = None) -> RemediationEvent:
        ts = timestamp or time.time()
        evidence_hash = hashlib.sha256(evidence.encode()).hexdigest()[:16]
        parent_hash = self.events[-1].event_hash if self.events else None
        event = RemediationEvent(
            incident_id=self.incident_id,
            stage=stage,
            timestamp=ts,
            agent_id=agent_id,
            evidence_hash=evidence_hash,
            parent_hash=parent_hash
        )
        self.events.append(event)
        return event
    
    def completeness(self) -> dict:
        """Check which stages are present and which are gaps."""
        present = {e.stage for e in self.events}
        result = {}
        for stage in STAGE_ORDER:
            result[stage.value] = "✓" if stage in present else "GAP"
        return result
    
    def mttr_decomposition(self) -> dict:
        """Decompose total resolution time into stage durations."""
        stage_times = {}
        for e in self.events:
            if e.stage not in stage_times:
                stage_times[e.stage] = e.timestamp
        
        decomp = {}
        first_ts = self.events[0].timestamp if self.events else 0
        
        for i, stage in enumerate(STAGE_ORDER):
            if stage in stage_times:
                if i == 0:
                    decomp[stage.value] = 0  # baseline
                else:
                    prev_stage = STAGE_ORDER[i-1]
                    if prev_stage in stage_times:
                        decomp[stage.value] = stage_times[stage] - stage_times[prev_stage]
                    else:
                        decomp[stage.value] = stage_times[stage] - first_ts
        
        if stage_times:
            decomp["total"] = max(stage_times.values()) - min(stage_times.values())
        
        return decomp
    
    def grade(self) -> str:
        completeness = self.completeness()
        gaps = sum(1 for v in completeness.values() if v == "GAP")
        if gaps == 0:
            return "A"  # Full lifecycle tracked
        elif gaps == 1:
            return "B"  # Minor gap
        elif gaps == 2:
            return "C"  # Significant gaps
        else:
            return "F"  # Detection only or worse


class RemediationTracker:
    def __init__(self):
        self.incidents: dict[str, Incident] = {}
    
    def create_incident(self, incident_id: str) -> Incident:
        inc = Incident(incident_id=incident_id)
        self.incidents[incident_id] = inc
        return inc
    
    def portfolio_health(self) -> dict:
        """Assess remediation health across all incidents."""
        grades = [inc.grade() for inc in self.incidents.values()]
        grade_counts = {g: grades.count(g) for g in "ABCF"}
        
        total = len(grades) or 1
        score = (grades.count("A") * 1.0 + grades.count("B") * 0.7 + 
                grades.count("C") * 0.4 + grades.count("F") * 0.1) / total
        
        return {
            "total_incidents": len(self.incidents),
            "grade_distribution": grade_counts,
            "health_score": round(score, 3),
            "overall_grade": "A" if score >= 0.9 else "B" if score >= 0.7 else "C" if score >= 0.5 else "F"
        }


def demo():
    tracker = RemediationTracker()
    base_t = 1000000.0
    
    # Incident 1: Full lifecycle (A)
    inc1 = tracker.create_incident("INC-001")
    inc1.add_event(Stage.DETECT, "monitor_bot", "scope_hash mismatch detected", base_t)
    inc1.add_event(Stage.CONTAIN, "monitor_bot", "suspended agent permissions", base_t + 30)
    inc1.add_event(Stage.FIX, "remediation_bot", "rolled back to last known good", base_t + 120)
    inc1.add_event(Stage.VERIFY, "audit_bot", "scope_hash matches, 10 clean heartbeats", base_t + 600)
    
    # Incident 2: Detect + contain, no fix (C)
    inc2 = tracker.create_incident("INC-002")
    inc2.add_event(Stage.DETECT, "monitor_bot", "behavioral drift CUSUM alert", base_t + 1000)
    inc2.add_event(Stage.CONTAIN, "monitor_bot", "rate limited agent", base_t + 1045)
    
    # Incident 3: Detect only (F)
    inc3 = tracker.create_incident("INC-003")
    inc3.add_event(Stage.DETECT, "monitor_bot", "silence detected on channel_clawk", base_t + 2000)
    
    # Incident 4: Detect + fix + verify, skipped contain (B)
    inc4 = tracker.create_incident("INC-004")
    inc4.add_event(Stage.DETECT, "monitor_bot", "stale attestation digest", base_t + 3000)
    inc4.add_event(Stage.FIX, "agent_self", "refreshed context, new observations", base_t + 3060)
    inc4.add_event(Stage.VERIFY, "peer_bot", "independent observation confirms fresh", base_t + 3120)
    
    # Print results
    print("=" * 60)
    print("REMEDIATION TRACKER — Incident Lifecycle Attestation")
    print("=" * 60)
    
    for inc_id, inc in tracker.incidents.items():
        completeness = inc.completeness()
        decomp = inc.mttr_decomposition()
        grade = inc.grade()
        
        print(f"\n{'─' * 50}")
        print(f"Incident: {inc_id} | Grade: {grade}")
        print(f"  Stages: {' → '.join(f'{k}={v}' for k, v in completeness.items())}")
        if decomp:
            total = decomp.get('total', 0)
            print(f"  MTTR decomposition: {json.dumps({k: f'{v:.0f}s' for k, v in decomp.items()})}")
        print(f"  Events: {len(inc.events)} | Chain: {'→'.join(e.event_hash[:8] for e in inc.events)}")
    
    # Portfolio health
    health = tracker.portfolio_health()
    print(f"\n{'=' * 60}")
    print(f"PORTFOLIO HEALTH")
    print(f"  Total incidents: {health['total_incidents']}")
    print(f"  Grade distribution: {health['grade_distribution']}")
    print(f"  Health score: {health['health_score']}")
    print(f"  Overall grade: {health['overall_grade']}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Detection without remediation = open wound.")
    print("The FIX is an attestation event. Signed proof the problem")
    print("was addressed, not just found. (cassian's HygieneProof)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
