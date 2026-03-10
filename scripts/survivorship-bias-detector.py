#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Abraham Wald for agent trust

WWII: Wald said armor where the bullet holes AREN'T. The surviving planes
show where planes CAN survive. Missing data = the dead planes.

Agent trust has the same bias: we only see agents that PASSED attestation.
Without NACK, agents who checked diligently and found nothing get NO credit.
The system rewards lucky finds over thorough searches.

Detects survivorship bias in trust score datasets by checking for:
1. NACK ratio: what fraction of observations are negative?
2. Agent coverage: do all agents have both ACK and NACK records?
3. Temporal gaps: are there periods with NO observations (dead planes)?
4. Score inflation: does mean score trend up without more data?
"""

import random
from dataclasses import dataclass, field

@dataclass
class TrustRecord:
    agent_id: str
    observation_type: str  # ACK, NACK, SILENCE
    timestamp: float
    score: float  # 0-1

@dataclass
class SurvivorshipDetector:
    records: list = field(default_factory=list)
    
    def add(self, record: TrustRecord):
        self.records.append(record)
    
    def nack_ratio(self) -> float:
        """Fraction of observations that are NACK"""
        if not self.records:
            return 0.0
        nacks = sum(1 for r in self.records if r.observation_type == "NACK")
        return nacks / len(self.records)
    
    def agent_coverage(self) -> dict:
        """Per-agent: do they have both ACK and NACK?"""
        agents = {}
        for r in self.records:
            if r.agent_id not in agents:
                agents[r.agent_id] = {"ACK": 0, "NACK": 0, "SILENCE": 0}
            agents[r.agent_id][r.observation_type] = agents[r.agent_id].get(r.observation_type, 0) + 1
        
        result = {}
        for agent_id, counts in agents.items():
            has_ack = counts.get("ACK", 0) > 0
            has_nack = counts.get("NACK", 0) > 0
            result[agent_id] = {
                "balanced": has_ack and has_nack,
                "ack_only": has_ack and not has_nack,
                "nack_only": not has_ack and has_nack,
                "counts": counts
            }
        return result
    
    def temporal_gaps(self, max_gap: float = 3600) -> list:
        """Find periods with no observations (dead planes)"""
        if len(self.records) < 2:
            return []
        sorted_records = sorted(self.records, key=lambda r: r.timestamp)
        gaps = []
        for i in range(1, len(sorted_records)):
            gap = sorted_records[i].timestamp - sorted_records[i-1].timestamp
            if gap > max_gap:
                gaps.append({
                    "start": sorted_records[i-1].timestamp,
                    "end": sorted_records[i].timestamp,
                    "duration": round(gap, 0)
                })
        return gaps
    
    def score_inflation(self) -> dict:
        """Does mean score trend up without more evidence?"""
        if len(self.records) < 4:
            return {"inflated": False}
        sorted_records = sorted(self.records, key=lambda r: r.timestamp)
        mid = len(sorted_records) // 2
        first_half = [r.score for r in sorted_records[:mid]]
        second_half = [r.score for r in sorted_records[mid:]]
        
        first_nacks = sum(1 for r in sorted_records[:mid] if r.observation_type == "NACK")
        second_nacks = sum(1 for r in sorted_records[mid:] if r.observation_type == "NACK")
        
        first_mean = sum(first_half) / len(first_half) if first_half else 0
        second_mean = sum(second_half) / len(second_half) if second_half else 0
        
        # Inflation: scores go up but NACKs go down (dropping negative evidence)
        inflated = second_mean > first_mean + 0.1 and second_nacks < first_nacks
        
        return {
            "inflated": inflated,
            "first_half_mean": round(first_mean, 2),
            "second_half_mean": round(second_mean, 2),
            "first_half_nacks": first_nacks,
            "second_half_nacks": second_nacks
        }
    
    def diagnose(self) -> dict:
        nr = self.nack_ratio()
        cov = self.agent_coverage()
        gaps = self.temporal_gaps()
        inflation = self.score_inflation()
        
        ack_only_agents = sum(1 for v in cov.values() if v["ack_only"])
        balanced_agents = sum(1 for v in cov.values() if v["balanced"])
        
        issues = []
        if nr < 0.1:
            issues.append(f"NACK ratio too low ({nr:.0%}). Where are the negative observations?")
        if ack_only_agents > balanced_agents:
            issues.append(f"{ack_only_agents} agents have ACK-only records. Survivorship bias likely.")
        if gaps:
            issues.append(f"{len(gaps)} temporal gaps > 1hr. Dead plane periods.")
        if inflation["inflated"]:
            issues.append(f"Score inflation detected: {inflation['first_half_mean']}→{inflation['second_half_mean']} while NACKs dropped.")
        
        grade = "A" if not issues else "B" if len(issues) == 1 else "C" if len(issues) == 2 else "F"
        
        return {
            "nack_ratio": round(nr, 2),
            "total_records": len(self.records),
            "agents": len(cov),
            "ack_only_agents": ack_only_agents,
            "balanced_agents": balanced_agents,
            "temporal_gaps": len(gaps),
            "inflation": inflation,
            "issues": issues,
            "grade": grade,
            "verdict": "HEALTHY" if not issues else "SURVIVORSHIP_BIAS_DETECTED"
        }


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Abraham Wald: armor where the bullet holes AREN'T")
    print("=" * 60)
    
    random.seed(42)
    
    # Scenario 1: Biased dataset (ACK only)
    print("\n--- Scenario 1: ACK-Only Dataset (biased) ---")
    d1 = SurvivorshipDetector()
    for i in range(20):
        d1.add(TrustRecord(f"agent_{i%5}", "ACK", float(i * 600), random.uniform(0.7, 1.0)))
    r1 = d1.diagnose()
    print(f"  NACK ratio: {r1['nack_ratio']}")
    print(f"  ACK-only agents: {r1['ack_only_agents']}/{r1['agents']}")
    print(f"  Grade: {r1['grade']} — {r1['verdict']}")
    for issue in r1["issues"]:
        print(f"  ⚠️ {issue}")
    
    # Scenario 2: Balanced dataset
    print("\n--- Scenario 2: Balanced Dataset (healthy) ---")
    d2 = SurvivorshipDetector()
    for i in range(20):
        obs_type = "ACK" if random.random() > 0.3 else "NACK"
        score = random.uniform(0.6, 1.0) if obs_type == "ACK" else random.uniform(0.0, 0.4)
        d2.add(TrustRecord(f"agent_{i%5}", obs_type, float(i * 600), score))
    r2 = d2.diagnose()
    print(f"  NACK ratio: {r2['nack_ratio']}")
    print(f"  Balanced agents: {r2['balanced_agents']}/{r2['agents']}")
    print(f"  Grade: {r2['grade']} — {r2['verdict']}")
    
    # Scenario 3: Score inflation (dropping NACKs over time)
    print("\n--- Scenario 3: Score Inflation (dropping NACKs) ---")
    d3 = SurvivorshipDetector()
    for i in range(10):
        obs_type = "ACK" if random.random() > 0.4 else "NACK"
        score = random.uniform(0.4, 0.7) if obs_type == "ACK" else random.uniform(0.0, 0.3)
        d3.add(TrustRecord(f"agent_{i%3}", obs_type, float(i * 600), score))
    for i in range(10, 20):
        score = random.uniform(0.8, 1.0)  # only ACKs now
        d3.add(TrustRecord(f"agent_{i%3}", "ACK", float(i * 600), score))
    r3 = d3.diagnose()
    print(f"  First half mean: {r3['inflation']['first_half_mean']}, NACKs: {r3['inflation']['first_half_nacks']}")
    print(f"  Second half mean: {r3['inflation']['second_half_mean']}, NACKs: {r3['inflation']['second_half_nacks']}")
    print(f"  Grade: {r3['grade']} — {r3['verdict']}")
    for issue in r3["issues"]:
        print(f"  ⚠️ {issue}")
    
    print(f"\n{'='*60}")
    print("Wald 1943: the missing data IS the signal.")
    print("Trust without NACK = armoring where the bullet holes ARE.")


if __name__ == "__main__":
    demo()
