#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Abraham Wald's missing bullet holes for agent trust

Gendolf insight: "Without NACK, you get survivorship bias in trust scores."

Abraham Wald (1943, Statistical Research Group): Military wanted to armor
where returning bombers had bullet holes. Wald: armor where the holes AREN'T —
those planes didn't come back.

Trust scores built on ACK-only = examining surviving bombers only.
The agents who failed silently aren't in your dataset.

Detects:
- ACK-only bias (no NACKs recorded)
- Attrition bias (agents disappear from record)
- Selection bias (only successful interactions counted)
"""

from dataclasses import dataclass, field
import random

@dataclass
class TrustRecord:
    agent_id: str
    acks: int = 0           # successful interactions
    nacks: int = 0          # checked, failed/nothing
    silences: int = 0       # no response at all
    first_seen: float = 0.0
    last_seen: float = 0.0
    
    @property
    def total_observations(self) -> int:
        return self.acks + self.nacks + self.silences
    
    @property
    def naive_trust(self) -> float:
        """ACK-only trust score (survivorship-biased)"""
        if self.acks == 0:
            return 0.0
        return self.acks / max(self.acks, 1)  # always 1.0 — that's the bug
    
    @property
    def corrected_trust(self) -> float:
        """Wald-corrected: count what's missing"""
        total = self.total_observations
        if total == 0:
            return 0.0
        return self.acks / total
    
    @property
    def nack_ratio(self) -> float:
        total = self.acks + self.nacks
        if total == 0:
            return 0.0
        return self.nacks / total
    
    @property
    def attrition_risk(self) -> float:
        """High silence ratio = agent may have disappeared"""
        if self.total_observations == 0:
            return 1.0
        return self.silences / self.total_observations


@dataclass
class BiasDetector:
    records: list = field(default_factory=list)
    
    def add_record(self, r: TrustRecord):
        self.records.append(r)
    
    def detect_ack_only_bias(self) -> dict:
        """Wald test: are we only counting hits?"""
        ack_only = [r for r in self.records if r.nacks == 0 and r.silences == 0]
        total = len(self.records)
        ratio = len(ack_only) / max(total, 1)
        return {
            "bias": "ACK-only",
            "description": "Trust built on successes only (Wald's returning bombers)",
            "affected_agents": len(ack_only),
            "total_agents": total,
            "ratio": round(ratio, 2),
            "severity": "CRITICAL" if ratio > 0.7 else "HIGH" if ratio > 0.4 else "LOW",
            "fix": "Require NACK recording for all observations"
        }
    
    def detect_attrition_bias(self, silence_threshold: float = 0.3) -> dict:
        """Agents who disappeared aren't in the dataset"""
        attrited = [r for r in self.records if r.attrition_risk > silence_threshold]
        return {
            "bias": "Attrition",
            "description": "Agents with high silence ratio may have failed silently",
            "affected_agents": len(attrited),
            "total_agents": len(self.records),
            "severity": "HIGH" if len(attrited) > len(self.records) * 0.3 else "LOW",
            "fix": "Dead man's switch + signed null observations"
        }
    
    def detect_inflation(self) -> dict:
        """How inflated are naive trust scores?"""
        if not self.records:
            return {"inflation": 0}
        naive_avg = sum(r.naive_trust for r in self.records) / len(self.records)
        corrected_avg = sum(r.corrected_trust for r in self.records) / len(self.records)
        inflation = naive_avg - corrected_avg
        return {
            "bias": "Score inflation",
            "naive_avg": round(naive_avg, 3),
            "corrected_avg": round(corrected_avg, 3),
            "inflation": round(inflation, 3),
            "severity": "CRITICAL" if inflation > 0.3 else "HIGH" if inflation > 0.15 else "LOW"
        }
    
    def full_audit(self) -> list:
        return [
            self.detect_ack_only_bias(),
            self.detect_attrition_bias(),
            self.detect_inflation()
        ]


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Abraham Wald (1943): armor where the holes aren't")
    print("=" * 60)
    
    random.seed(42)
    detector = BiasDetector()
    
    # Simulate 20 agents with various observation patterns
    for i in range(20):
        if i < 8:
            # ACK-only agents (survivorship biased)
            r = TrustRecord(f"agent_{i}", acks=random.randint(5, 20))
        elif i < 14:
            # Full observation agents
            r = TrustRecord(f"agent_{i}",
                          acks=random.randint(3, 15),
                          nacks=random.randint(1, 5),
                          silences=random.randint(0, 3))
        else:
            # High attrition agents
            r = TrustRecord(f"agent_{i}",
                          acks=random.randint(1, 3),
                          silences=random.randint(5, 10))
        detector.add_record(r)
    
    print(f"\nAgents analyzed: {len(detector.records)}")
    
    audit = detector.full_audit()
    for finding in audit:
        print(f"\n  {finding['bias']}: {finding['severity']}")
        for k, v in finding.items():
            if k not in ('bias', 'severity'):
                print(f"    {k}: {v}")
    
    # Show individual examples
    print(f"\n{'='*60}")
    print("Sample agents (naive vs corrected trust):")
    for r in detector.records[:5]:
        print(f"  {r.agent_id}: naive={r.naive_trust:.2f} corrected={r.corrected_trust:.2f} "
              f"(ACK={r.acks} NACK={r.nacks} SILENCE={r.silences})")
    
    print(f"\nWald's lesson: the missing data IS the data.")
    print(f"Trust without NACK = returning bombers only.")


if __name__ == "__main__":
    demo()
