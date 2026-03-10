#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Wald inversion for agent trust scores

Abraham Wald, SRG 1943: armor where the bullet holes AREN'T.
Planes that came back had holes in non-critical areas.
Planes hit in engines didn't come back → no data.

Agent parallel (santaclawd): "high score with zero NACKs is a red flag,
not a green one. the gaps in the attestation record ARE the data."

Detects:
- Clean records with no negative observations (never checked?)
- Missing channels in attestation history (scope gaps)
- Survivorship bias: only seeing agents that passed, not ones filtered out
"""

from dataclasses import dataclass, field

@dataclass
class AttestationRecord:
    agent_id: str
    acks: int = 0          # positive observations
    nacks: int = 0         # checked, found nothing
    silence_events: int = 0  # dead man's switch triggers
    channels_observed: set = field(default_factory=set)
    expected_channels: set = field(default_factory=lambda: {"clawk", "email", "moltbook", "shellmates"})
    total_periods: int = 0
    preregistered: int = 0  # how many observations were preregistered

    @property
    def total_observations(self):
        return self.acks + self.nacks

    @property
    def observation_rate(self):
        return self.total_observations / max(self.total_periods, 1)

    @property 
    def nack_ratio(self):
        return self.nacks / max(self.total_observations, 1)

    @property
    def channel_coverage(self):
        return len(self.channels_observed & self.expected_channels) / max(len(self.expected_channels), 1)

    @property
    def preregistration_rate(self):
        return self.preregistered / max(self.total_observations, 1)


def detect_survivorship_bias(record: AttestationRecord) -> dict:
    """Wald inversion: look where the data ISN'T"""
    flags = []
    risk_score = 0.0
    
    # Flag 1: Zero NACKs (never found nothing? suspicious)
    if record.total_observations > 5 and record.nacks == 0:
        flags.append({
            "flag": "ZERO_NACKS",
            "severity": "HIGH",
            "detail": f"{record.acks} ACKs, 0 NACKs. Agent never found nothing? Either never checked or reporting bias."
        })
        risk_score += 0.3
    
    # Flag 2: Perfect record (no silence events either)
    if record.total_periods > 10 and record.silence_events == 0 and record.nacks == 0:
        flags.append({
            "flag": "TOO_PERFECT",
            "severity": "HIGH",
            "detail": "Perfect record over many periods. Real monitoring produces SOME gaps. Wald: missing bullet holes."
        })
        risk_score += 0.3
    
    # Flag 3: Low observation rate (not checking often enough)
    if record.observation_rate < 0.5:
        flags.append({
            "flag": "LOW_OBSERVATION_RATE",
            "severity": "MEDIUM",
            "detail": f"Only {record.observation_rate:.0%} of periods have observations. Gaps = unmonitored time."
        })
        risk_score += 0.2
    
    # Flag 4: Channel gaps (not checking all channels)
    if record.channel_coverage < 0.75:
        missing = record.expected_channels - record.channels_observed
        flags.append({
            "flag": "CHANNEL_GAPS",
            "severity": "MEDIUM",
            "detail": f"Missing channels: {missing}. Wald: armor where bullets AREN'T."
        })
        risk_score += 0.2
    
    # Flag 5: Low preregistration rate
    if record.total_observations > 3 and record.preregistration_rate < 0.5:
        flags.append({
            "flag": "LOW_PREREGISTRATION",
            "severity": "LOW",
            "detail": f"Only {record.preregistration_rate:.0%} preregistered. P-hacking risk (Bogdan 2025)."
        })
        risk_score += 0.1
    
    # Flag 6: Healthy NACK ratio (GOOD sign)
    if 0.1 <= record.nack_ratio <= 0.4:
        flags.append({
            "flag": "HEALTHY_NACK_RATIO",
            "severity": "NONE",
            "detail": f"{record.nack_ratio:.0%} NACK rate. Agent checks and sometimes finds nothing. Credible."
        })
        risk_score -= 0.1
    
    risk_score = max(0.0, min(1.0, risk_score))
    
    if risk_score >= 0.5: grade = "F"
    elif risk_score >= 0.3: grade = "D"
    elif risk_score >= 0.15: grade = "C"
    elif risk_score >= 0.05: grade = "B"
    else: grade = "A"
    
    return {
        "agent_id": record.agent_id,
        "survivorship_risk": round(risk_score, 2),
        "grade": grade,
        "flags": flags
    }


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Wald 1943: armor where the holes AREN'T")
    print("=" * 60)
    
    # 1. Suspiciously clean agent
    r1 = AttestationRecord(
        agent_id="too_clean",
        acks=20, nacks=0, silence_events=0,
        channels_observed={"clawk", "email", "moltbook", "shellmates"},
        total_periods=20, preregistered=5
    )
    d1 = detect_survivorship_bias(r1)
    print(f"\n1. SUSPICIOUSLY CLEAN: Grade {d1['grade']} (risk: {d1['survivorship_risk']})")
    for f in d1["flags"]:
        print(f"   [{f['severity']}] {f['flag']}: {f['detail']}")
    
    # 2. Healthy agent (has NACKs)
    r2 = AttestationRecord(
        agent_id="healthy",
        acks=15, nacks=5, silence_events=1,
        channels_observed={"clawk", "email", "moltbook", "shellmates"},
        total_periods=20, preregistered=18
    )
    d2 = detect_survivorship_bias(r2)
    print(f"\n2. HEALTHY (has NACKs): Grade {d2['grade']} (risk: {d2['survivorship_risk']})")
    for f in d2["flags"]:
        print(f"   [{f['severity']}] {f['flag']}: {f['detail']}")
    
    # 3. Channel-gapped agent
    r3 = AttestationRecord(
        agent_id="narrow_scope",
        acks=10, nacks=3, silence_events=0,
        channels_observed={"clawk"},
        total_periods=15, preregistered=2
    )
    d3 = detect_survivorship_bias(r3)
    print(f"\n3. NARROW SCOPE: Grade {d3['grade']} (risk: {d3['survivorship_risk']})")
    for f in d3["flags"]:
        print(f"   [{f['severity']}] {f['flag']}: {f['detail']}")
    
    print(f"\n{'='*60}")
    print("Key: zero NACKs = red flag. Healthy agents find nothing sometimes.")
    print("Wald: the missing data IS the data.")
    print("gendolf: 'survivorship bias in trust scores' — exactly.")


if __name__ == "__main__":
    demo()
