#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (Psychological Bulletin 2004, k=72 studies).

The sleeper effect: discounting cues (e.g., "this source was compromised")
decay faster than message content. Over time, the message gains influence
as the cue dissociates. In agent systems:

- A flagged key gets revoked → agent reboots → new context loses the flag
- Reputation damage fades while the agent's outputs persist
- Session boundaries = forced dissociation events

Fix: cryptographically bind cues to content (Merkle proofs, hash chains).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json
import math


@dataclass
class DiscountingCue:
    """A reason to distrust a source"""
    cue_id: str
    source_id: str
    reason: str
    severity: float  # 0-1
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bound_to_content: bool = False  # Is cue cryptographically bound?
    binding_hash: Optional[str] = None  # Merkle proof or hash chain ref


@dataclass  
class TrustDecayModel:
    """
    Kumkale & Albarracín 2004 meta-analysis findings:
    - Content memory decays at rate α
    - Source credibility (cue) decays at rate β  
    - Sleeper effect occurs when β > α (cue forgotten faster than content)
    - Conditions: strong initial message, cue AFTER message, high elaboration
    """
    content_decay_rate: float = 0.02   # α: slow content decay
    cue_decay_rate: float = 0.08       # β: fast cue decay (4x content)
    
    def content_strength(self, hours_elapsed: float) -> float:
        """How much of the message content is still accessible"""
        return math.exp(-self.content_decay_rate * hours_elapsed)
    
    def cue_strength(self, hours_elapsed: float, bound: bool = False) -> float:
        """How much of the discounting cue is still accessible"""
        if bound:
            # Cryptographically bound cue decays with content, not independently
            return math.exp(-self.content_decay_rate * hours_elapsed)
        return math.exp(-self.cue_decay_rate * hours_elapsed)
    
    def effective_persuasion(self, hours: float, bound: bool = False) -> float:
        """
        Net persuasion = content_strength - cue_strength
        Sleeper effect: persuasion INCREASES over time when cue decays faster
        """
        content = self.content_strength(hours)
        cue = self.cue_strength(hours, bound)
        # When cue is strong, it discounts. As cue fades, content dominates.
        return content * (1 - cue * 0.8)  # 80% max discounting from cue
    
    def sleeper_risk_window(self) -> tuple[float, float]:
        """Hours where sleeper effect is most dangerous (cue faded, content still strong)"""
        # Find where cue < 0.3 but content > 0.5
        start = -math.log(0.3) / self.cue_decay_rate  # ~15h for default
        end = -math.log(0.5) / self.content_decay_rate  # ~35h for default
        return (round(start, 1), round(end, 1))


def detect_sleeper_risk(cues: list[DiscountingCue], 
                        current_time: datetime = None) -> dict:
    """Assess sleeper effect risk for a set of discounting cues."""
    
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    
    model = TrustDecayModel()
    risks = []
    
    for cue in cues:
        hours = (current_time - cue.timestamp).total_seconds() / 3600
        
        content = model.content_strength(hours)
        cue_strength = model.cue_strength(hours, cue.bound_to_content)
        persuasion = model.effective_persuasion(hours, cue.bound_to_content)
        
        risk_level = "LOW"
        if not cue.bound_to_content and cue_strength < 0.3 and content > 0.5:
            risk_level = "HIGH"  # Sleeper window
        elif not cue.bound_to_content and cue_strength < 0.5 and content > 0.5:
            risk_level = "MEDIUM"
        elif cue.bound_to_content:
            risk_level = "MITIGATED"
        
        risks.append({
            "cue_id": cue.cue_id,
            "source": cue.source_id,
            "reason": cue.reason,
            "hours_elapsed": round(hours, 1),
            "content_strength": round(content, 3),
            "cue_strength": round(cue_strength, 3),
            "effective_persuasion": round(persuasion, 3),
            "bound": cue.bound_to_content,
            "risk": risk_level,
        })
    
    high_risks = [r for r in risks if r["risk"] == "HIGH"]
    
    window = model.sleeper_risk_window()
    
    return {
        "total_cues": len(cues),
        "high_risk": len(high_risks),
        "sleeper_window_hours": f"{window[0]}-{window[1]}",
        "grade": "F" if high_risks else ("B" if any(r["risk"] == "MEDIUM" for r in risks) else "A"),
        "risks": risks,
        "recommendation": "BIND cues to content via hash chain" if high_risks else "Cues properly bound or fresh"
    }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Fresh flag (just revoked key)",
            "cues": [
                DiscountingCue("cue_1", "agent_alice", "key compromised", 0.9,
                              now - timedelta(hours=1), bound_to_content=False),
            ]
        },
        {
            "name": "2. Stale flag (revoked 24h ago, unbound)",
            "cues": [
                DiscountingCue("cue_2", "agent_bob", "key compromised", 0.9,
                              now - timedelta(hours=24), bound_to_content=False),
            ]
        },
        {
            "name": "3. Stale flag (revoked 24h ago, hash-bound)",
            "cues": [
                DiscountingCue("cue_3", "agent_charlie", "key compromised", 0.9,
                              now - timedelta(hours=24), bound_to_content=True,
                              binding_hash="sha256:abc123..."),
            ]
        },
        {
            "name": "4. Mixed: some bound, some not",
            "cues": [
                DiscountingCue("cue_4a", "agent_dave", "spam flagged", 0.6,
                              now - timedelta(hours=48), bound_to_content=False),
                DiscountingCue("cue_4b", "agent_dave", "attestation revoked", 0.8,
                              now - timedelta(hours=12), bound_to_content=True,
                              binding_hash="sha256:def456..."),
            ]
        },
        {
            "name": "5. Agent reboot (session boundary = forced dissociation)",
            "cues": [
                DiscountingCue("cue_5", "agent_eve", "produced hallucinated output", 0.7,
                              now - timedelta(hours=6), bound_to_content=False),
            ]
        },
    ]
    
    model = TrustDecayModel()
    window = model.sleeper_risk_window()
    print(f"\nSleeper risk window: {window[0]}-{window[1]} hours")
    print(f"(cue faded but content still strong)")
    
    # Decay timeline
    print(f"\n{'─' * 60}")
    print("DECAY TIMELINE (unbound cue):")
    print(f"{'Hours':>6} | {'Content':>8} | {'Cue':>8} | {'Persuasion':>10} | Status")
    print(f"{'─' * 6}-+-{'─' * 8}-+-{'─' * 8}-+-{'─' * 10}-+-{'─' * 12}")
    for h in [0, 2, 6, 12, 18, 24, 36, 48]:
        c = model.content_strength(h)
        q = model.cue_strength(h, False)
        p = model.effective_persuasion(h, False)
        status = "⚠️  SLEEPER" if q < 0.3 and c > 0.5 else ("⚡ fading" if q < 0.5 else "✓ guarded")
        print(f"{h:>6} | {c:>8.3f} | {q:>8.3f} | {p:>10.3f} | {status}")
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        result = detect_sleeper_risk(scenario["cues"], now)
        print(f"Grade: {result['grade']} | High risk: {result['high_risk']}/{result['total_cues']}")
        for r in result["risks"]:
            print(f"  {r['source']}: {r['reason']} ({r['hours_elapsed']}h)")
            print(f"    content={r['content_strength']}, cue={r['cue_strength']}, "
                  f"persuasion={r['effective_persuasion']}, risk={r['risk']}")
        if result["recommendation"]:
            print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Session boundaries = forced cue dissociation.")
    print("  Agent reboots lose flags unless hash-chained to identity.")
    print("  CT/Merkle proofs bind cue to content = no sleeper effect.")
    print("  Reputation scores without binding = sleeper-vulnerable.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
