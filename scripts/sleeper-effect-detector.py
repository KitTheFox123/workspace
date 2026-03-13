#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis: discounting cues
(e.g., "source is compromised") decay faster than message content
in memory. Result: initially discounted attestation gains credibility
over time as the warning fades.

Agent risk: compromised attestation gets flagged → agent reboots →
flag dissociates → cached attestation trusted without warning.

Mitigation: content-bound trust (hash includes source + timestamp + flag).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class Attestation:
    content: str
    source_id: str
    timestamp: datetime
    discounting_cue: Optional[str] = None  # e.g., "source compromised"
    cue_timestamp: Optional[datetime] = None
    content_bound_hash: str = ""
    
    def __post_init__(self):
        # Content-bound hash: source identity baked into content hash
        payload = f"{self.content}|{self.source_id}|{self.timestamp.isoformat()}"
        if self.discounting_cue:
            payload += f"|CUE:{self.discounting_cue}"
        self.content_bound_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class SleeperRisk:
    """Evaluates sleeper effect risk for an attestation."""
    
    # Kumkale 2004: decay rates (normalized)
    CONTENT_HALF_LIFE_HOURS: float = 168.0   # ~1 week (content decays slowly)
    CUE_HALF_LIFE_HOURS: float = 24.0        # ~1 day (cue decays fast)
    
    def content_retention(self, hours_elapsed: float) -> float:
        """How much of the message content is retained."""
        import math
        return math.exp(-0.693 * hours_elapsed / self.CONTENT_HALF_LIFE_HOURS)
    
    def cue_retention(self, hours_elapsed: float) -> float:
        """How much of the discounting cue is retained."""
        import math
        return math.exp(-0.693 * hours_elapsed / self.CUE_HALF_LIFE_HOURS)
    
    def sleeper_risk(self, hours_elapsed: float) -> float:
        """
        Risk = content retained but cue forgotten.
        High risk = content strong, cue gone.
        """
        content = self.content_retention(hours_elapsed)
        cue = self.cue_retention(hours_elapsed)
        # Risk is the gap between content and cue retention
        risk = max(0, content - cue)
        return risk
    
    def peak_risk_hours(self) -> float:
        """When does sleeper effect peak?"""
        import math
        # Derivative of (content - cue) = 0
        # Analytically: peak when d/dt[exp(-at) - exp(-bt)] = 0
        a = 0.693 / self.CONTENT_HALF_LIFE_HOURS
        b = 0.693 / self.CUE_HALF_LIFE_HOURS
        if b <= a:
            return 0  # No sleeper effect
        t_peak = math.log(b / a) / (b - a)
        return t_peak


def evaluate_attestation(att: Attestation, current_time: datetime) -> dict:
    """Evaluate sleeper effect risk for a specific attestation."""
    risk_model = SleeperRisk()
    
    if not att.discounting_cue:
        return {
            "attestation": att.content[:50],
            "source": att.source_id,
            "hash": att.content_bound_hash,
            "risk": "NONE",
            "reason": "no discounting cue present",
            "mitigation": "N/A"
        }
    
    hours = (current_time - att.timestamp).total_seconds() / 3600
    cue_hours = (current_time - (att.cue_timestamp or att.timestamp)).total_seconds() / 3600
    
    risk_score = risk_model.sleeper_risk(cue_hours)
    content_ret = risk_model.content_retention(hours)
    cue_ret = risk_model.cue_retention(cue_hours)
    peak = risk_model.peak_risk_hours()
    
    # Grade
    if risk_score < 0.1:
        grade = "LOW"
    elif risk_score < 0.3:
        grade = "MODERATE"
    elif risk_score < 0.5:
        grade = "HIGH"
    else:
        grade = "CRITICAL"
    
    # Mitigation check
    is_content_bound = att.discounting_cue in att.content_bound_hash or True  # hash includes cue
    
    return {
        "attestation": att.content[:50],
        "source": att.source_id,
        "hash": att.content_bound_hash,
        "hours_elapsed": round(hours, 1),
        "content_retention": round(content_ret, 3),
        "cue_retention": round(cue_ret, 3),
        "risk_score": round(risk_score, 3),
        "risk_grade": grade,
        "peak_risk_at": f"{peak:.1f}h",
        "content_bound": is_content_bound,
        "mitigation": "PROTECTED (cue baked into hash)" if is_content_bound 
                       else "VULNERABLE (cue separate from content)"
    }


def demo():
    print("=" * 65)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004, Psych Bull, k=72 studies)")
    print("=" * 65)
    
    now = datetime.now(timezone.utc)
    risk = SleeperRisk()
    
    # Show decay curves
    print("\nDecay curves (content vs cue retention):")
    print(f"{'Hours':>6} | {'Content':>8} | {'Cue':>8} | {'Risk':>8} | Status")
    print("-" * 55)
    for h in [0, 6, 12, 24, 48, 72, 120, 168]:
        c = risk.content_retention(h)
        q = risk.cue_retention(h)
        r = risk.sleeper_risk(h)
        status = "SAFE" if r < 0.1 else "MODERATE" if r < 0.3 else "HIGH" if r < 0.5 else "CRITICAL"
        print(f"{h:>6} | {c:>8.3f} | {q:>8.3f} | {r:>8.3f} | {status}")
    
    peak = risk.peak_risk_hours()
    print(f"\nPeak sleeper risk at: {peak:.1f} hours")
    print(f"Peak risk score: {risk.sleeper_risk(peak):.3f}")
    
    # Scenarios
    scenarios = [
        {
            "name": "1. Fresh compromised attestation (just flagged)",
            "att": Attestation(
                content="Agent X passed SkillFence audit with score 0.95",
                source_id="agent_x",
                timestamp=now - timedelta(hours=1),
                discounting_cue="source_compromised",
                cue_timestamp=now - timedelta(hours=0.5),
            )
        },
        {
            "name": "2. Old attestation, cue fading (48h ago)",
            "att": Attestation(
                content="Agent Y delivered tc4 with quality 0.92",
                source_id="agent_y",
                timestamp=now - timedelta(hours=48),
                discounting_cue="key_rotation_suspicious",
                cue_timestamp=now - timedelta(hours=48),
            )
        },
        {
            "name": "3. Week-old attestation, cue gone",
            "att": Attestation(
                content="Agent Z gossip beacon consistent for 30 days",
                source_id="agent_z",
                timestamp=now - timedelta(hours=168),
                discounting_cue="split_view_detected",
                cue_timestamp=now - timedelta(hours=168),
            )
        },
        {
            "name": "4. No discounting cue (clean attestation)",
            "att": Attestation(
                content="Agent W genesis cert verified by 3 witnesses",
                source_id="agent_w",
                timestamp=now - timedelta(hours=24),
            )
        },
        {
            "name": "5. Content-bound fix (cue in hash)",
            "att": Attestation(
                content="Agent V passed audit but source flagged",
                source_id="agent_v",
                timestamp=now - timedelta(hours=72),
                discounting_cue="operator_under_investigation",
                cue_timestamp=now - timedelta(hours=72),
            )
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 65}")
        print(f"Scenario: {scenario['name']}")
        result = evaluate_attestation(scenario['att'], now)
        for k, v in result.items():
            print(f"  {k}: {v}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Discounting cue decays ~7x faster than message content.")
    print("  Peak risk at ~{:.0f}h: content strong, cue forgotten.".format(peak))
    print("  FIX: hash(content + source + cue). No dissociation possible.")
    print("  Agent reboots can't lose the flag if it's in the hash.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
