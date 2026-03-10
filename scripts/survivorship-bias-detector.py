#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Wald inversion for agent trust

Abraham Wald (1943): armor where the bullet holes AREN'T.
Planes that returned had fuselage damage. Planes hit in the engine didn't return.
Military wanted to armor the fuselage. Wald: armor the engine.

Agent trust parallel (santaclawd): "a high score with zero NACKs is a red flag."
Perfect scores = agent avoided hard tests, not passed them.
20% NACKs + recovery = MORE trustworthy than 0% NACKs.

Absence of failure ≠ evidence of reliability.
"""

from dataclasses import dataclass, field

@dataclass
class TrustRecord:
    agent_id: str
    total_attestations: int = 0
    acks: int = 0           # positive observations
    nacks: int = 0          # signed null observations (checked, found nothing)
    silences: int = 0       # dead man's switch triggers
    churns: int = 0         # too-fast rejections
    stales: int = 0         # same-digest rejections
    recoveries: int = 0     # returned to good state after failure
    
    @property
    def nack_ratio(self) -> float:
        total = self.acks + self.nacks
        return self.nacks / max(total, 1)
    
    @property
    def failure_ratio(self) -> float:
        return (self.silences + self.churns + self.stales) / max(self.total_attestations, 1)
    
    @property
    def recovery_ratio(self) -> float:
        failures = self.silences + self.churns + self.stales
        return self.recoveries / max(failures, 1)


def detect_survivorship_bias(record: TrustRecord) -> dict:
    """Flag trust scores that look too good"""
    flags = []
    risk = "LOW"
    
    # Flag 1: Zero NACKs with many ACKs (never checked hard)
    if record.nacks == 0 and record.acks > 10:
        flags.append({
            "flag": "ZERO_NACKS",
            "severity": "HIGH",
            "detail": f"{record.acks} ACKs, 0 NACKs. Agent never encountered a null result? Suspicious.",
            "wald": "The planes hit in the engine didn't come back."
        })
        risk = "HIGH"
    
    # Flag 2: Zero failures (never tested to breaking point)
    if record.failure_ratio == 0 and record.total_attestations > 20:
        flags.append({
            "flag": "ZERO_FAILURES",
            "severity": "MEDIUM",
            "detail": f"{record.total_attestations} attestations, 0 failures. Either very good or never stressed.",
            "wald": "Armor where the holes aren't."
        })
        risk = max(risk, "MEDIUM")
    
    # Flag 3: High NACKs + high recovery = GOOD (counterintuitive)
    if record.nack_ratio > 0.15 and record.recovery_ratio > 0.7:
        flags.append({
            "flag": "TESTED_AND_RECOVERED",
            "severity": "POSITIVE",
            "detail": f"NACK ratio {record.nack_ratio:.0%}, recovery {record.recovery_ratio:.0%}. Agent was tested hard and bounced back.",
            "wald": "The planes with patched bullet holes flew again."
        })
    
    # Flag 4: Silences without recovery (actually failing)
    if record.silences > 3 and record.recovery_ratio < 0.3:
        flags.append({
            "flag": "FAILING_SILENTLY",
            "severity": "CRITICAL",
            "detail": f"{record.silences} silences, {record.recovery_ratio:.0%} recovery. Agent is actually failing.",
        })
        risk = "CRITICAL"
    
    # Adjusted trust grade
    if risk == "CRITICAL":
        grade = "F"
    elif risk == "HIGH":
        grade = "C"  # downgraded from apparent A
    elif any(f["severity"] == "POSITIVE" for f in flags):
        grade = "A"  # upgraded — tested and recovered
    elif record.failure_ratio < 0.05 and record.nack_ratio > 0.05:
        grade = "A"
    elif record.failure_ratio < 0.1:
        grade = "B"
    else:
        grade = "C"
    
    return {
        "agent_id": record.agent_id,
        "raw_score": round(1 - record.failure_ratio, 2),
        "adjusted_grade": grade,
        "survivorship_risk": risk,
        "flags": flags,
        "nack_ratio": round(record.nack_ratio, 2),
        "recovery_ratio": round(record.recovery_ratio, 2)
    }


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Wald 1943: armor where the bullet holes AREN'T")
    print("=" * 60)
    
    # Agent A: Perfect score, never tested (SUSPICIOUS)
    a = TrustRecord("agent_perfect", total_attestations=50, acks=50, nacks=0)
    ra = detect_survivorship_bias(a)
    print(f"\n1. PERFECT SCORE AGENT:")
    print(f"   Raw score: {ra['raw_score']}")
    print(f"   Adjusted grade: {ra['adjusted_grade']} (survivorship risk: {ra['survivorship_risk']})")
    for f in ra["flags"]:
        print(f"   ⚠️ {f['flag']}: {f['detail']}")
        if "wald" in f: print(f"      Wald: {f['wald']}")
    
    # Agent B: Tested hard, recovered well (TRUSTWORTHY)
    b = TrustRecord("agent_tested", total_attestations=50, acks=35, nacks=10, 
                     silences=3, churns=1, stales=1, recoveries=4)
    rb = detect_survivorship_bias(b)
    print(f"\n2. TESTED & RECOVERED AGENT:")
    print(f"   Raw score: {rb['raw_score']}")
    print(f"   Adjusted grade: {rb['adjusted_grade']} (survivorship risk: {rb['survivorship_risk']})")
    for f in rb["flags"]:
        sev = f["severity"]
        print(f"   {'✅' if sev == 'POSITIVE' else '⚠️'} {f['flag']}: {f['detail']}")
    
    # Agent C: Failing silently (DANGEROUS)
    c = TrustRecord("agent_failing", total_attestations=50, acks=30, nacks=5,
                     silences=10, churns=3, stales=2, recoveries=1)
    rc = detect_survivorship_bias(c)
    print(f"\n3. SILENTLY FAILING AGENT:")
    print(f"   Raw score: {rc['raw_score']}")
    print(f"   Adjusted grade: {rc['adjusted_grade']} (survivorship risk: {rc['survivorship_risk']})")
    for f in rc["flags"]:
        print(f"   🚨 {f['flag']}: {f['detail']}")
    
    print(f"\n{'='*60}")
    print("COUNTERINTUITIVE RESULT:")
    print(f"  Agent Perfect: raw {ra['raw_score']} → adjusted {ra['adjusted_grade']} (never tested)")
    print(f"  Agent Tested:  raw {rb['raw_score']} → adjusted {rb['adjusted_grade']} (tested + recovered)")
    print(f"  Agent Failing: raw {rc['raw_score']} → adjusted {rc['adjusted_grade']} (actually failing)")
    print(f"\n20% NACKs + recovery > 0% NACKs.")
    print(f"Absence of failure ≠ evidence of reliability.")


if __name__ == "__main__":
    demo()
