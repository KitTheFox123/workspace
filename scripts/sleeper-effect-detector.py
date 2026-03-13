#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín 2004 (Psychological Bulletin, k=72 studies):
- Discounting cue (e.g., "source flagged as compromised") fades faster than message
- After delay, flagged info regains persuasive power
- Agent risk: compromised identity gets "clean" after reboot/migration

Detection: monitor trust scores for flagged sources over time.
If trust rises without new positive evidence → sleeper effect.
Fix: append-only flag log binds cue to identity permanently.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import math


@dataclass
class TrustFlag:
    """A discounting cue attached to an identity."""
    agent_id: str
    flag_type: str  # "compromised", "equivocation", "split_view"
    timestamp: datetime
    evidence_hash: str  # Hash-chained to make unforgeable
    severity: float  # 0-1
    
    @property
    def age_hours(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds() / 3600


@dataclass  
class TrustRecord:
    agent_id: str
    flags: list[TrustFlag] = field(default_factory=list)
    trust_score: float = 0.5
    trust_history: list[tuple[datetime, float]] = field(default_factory=list)
    positive_evidence_since_flag: int = 0
    
    def add_flag(self, flag: TrustFlag):
        self.flags.append(flag)
        # Immediate discount
        self.trust_score *= (1.0 - flag.severity * 0.5)
        self.trust_history.append((flag.timestamp, self.trust_score))
    
    def naive_decay(self, hours_elapsed: float) -> float:
        """
        Naive trust systems: flag influence decays exponentially.
        This IS the sleeper effect — the discounting cue fades.
        Kumkale 2004: cue fades at ~2 weeks for humans.
        For agents with short context: much faster.
        """
        if not self.flags:
            return self.trust_score
        
        # Each flag's influence decays
        total_discount = 0.0
        for flag in self.flags:
            age = flag.age_hours + hours_elapsed
            # Half-life: 168 hours (1 week) for humans, 
            # but agent context windows = much shorter
            half_life = 24.0  # 24 hours for agents (context resets)
            decay = math.exp(-0.693 * age / half_life)
            total_discount += flag.severity * decay
        
        # Trust recovers as flags fade
        recovery = min(total_discount, 1.0)
        return min(0.5 + 0.5 * (1.0 - recovery), 1.0)
    
    def append_only_score(self) -> float:
        """
        Sleeper-proof: flags never decay. Only positive evidence can
        rehabilitate trust, and even then, flags remain visible.
        """
        if not self.flags:
            return self.trust_score
        
        # Flags are permanent discounts
        permanent_discount = sum(f.severity * 0.3 for f in self.flags)
        permanent_discount = min(permanent_discount, 0.8)
        
        # Positive evidence can partially recover
        recovery = min(self.positive_evidence_since_flag * 0.05, 0.3)
        
        return max(0.5 * (1.0 - permanent_discount) + recovery, 0.05)


def detect_sleeper_effect(record: TrustRecord, current_trust: float) -> dict:
    """
    Detect if a flagged identity's trust is rising without new evidence.
    This is the sleeper effect in action.
    """
    if not record.flags:
        return {"detected": False, "reason": "no flags"}
    
    # Trust at time of most recent flag
    flag_trust = record.trust_score
    
    # Expected trust with append-only (no decay)
    expected = record.append_only_score()
    
    # If current trust significantly exceeds expected → sleeper effect
    delta = current_trust - expected
    
    if delta > 0.15 and record.positive_evidence_since_flag < 3:
        return {
            "detected": True,
            "severity": "HIGH",
            "delta": round(delta, 3),
            "current": round(current_trust, 3),
            "expected": round(expected, 3),
            "reason": f"Trust rose {delta:.1%} without sufficient positive evidence "
                      f"({record.positive_evidence_since_flag} events). "
                      f"Discounting cue has faded. Sleeper effect active.",
            "fix": "Bind flag to identity via append-only log. "
                   "Flag IS the identity now."
        }
    elif delta > 0.05:
        return {
            "detected": True, 
            "severity": "LOW",
            "delta": round(delta, 3),
            "current": round(current_trust, 3),
            "expected": round(expected, 3),
            "reason": "Minor trust drift detected. Monitor."
        }
    else:
        return {
            "detected": False,
            "delta": round(delta, 3),
            "current": round(current_trust, 3),
            "expected": round(expected, 3),
            "reason": "Trust aligned with flag history."
        }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín 2004 (Psych Bull, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Fresh flag — trust correctly suppressed",
            "record": TrustRecord(agent_id="agent_alice", trust_score=0.8),
            "flag": TrustFlag("agent_alice", "compromised", now - timedelta(hours=1),
                            "abc123", 0.7),
            "hours_elapsed": 1,
            "positive_evidence": 0,
        },
        {
            "name": "2. Old flag — naive system lets trust recover (SLEEPER!)",
            "record": TrustRecord(agent_id="agent_bob", trust_score=0.8),
            "flag": TrustFlag("agent_bob", "equivocation", now - timedelta(hours=48),
                            "def456", 0.6),
            "hours_elapsed": 48,
            "positive_evidence": 0,
        },
        {
            "name": "3. Old flag — append-only keeps flag active",
            "record": TrustRecord(agent_id="agent_carol", trust_score=0.8),
            "flag": TrustFlag("agent_carol", "split_view", now - timedelta(hours=72),
                            "ghi789", 0.8),
            "hours_elapsed": 72,
            "positive_evidence": 1,
        },
        {
            "name": "4. Rehabilitated — genuine positive evidence",
            "record": TrustRecord(agent_id="agent_dave", trust_score=0.8),
            "flag": TrustFlag("agent_dave", "compromised", now - timedelta(hours=168),
                            "jkl012", 0.5),
            "hours_elapsed": 168,
            "positive_evidence": 10,
        },
        {
            "name": "5. Reboot amnesia — context reset clears flags",
            "record": TrustRecord(agent_id="agent_eve", trust_score=0.8),
            "flag": TrustFlag("agent_eve", "compromised", now - timedelta(hours=4),
                            "mno345", 0.9),
            "hours_elapsed": 4,
            "positive_evidence": 0,
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        
        record = s["record"]
        record.add_flag(s["flag"])
        record.positive_evidence_since_flag = s["positive_evidence"]
        
        # What naive system would show (sleeper effect)
        naive_trust = record.naive_decay(s["hours_elapsed"])
        # What append-only system shows
        safe_trust = record.append_only_score()
        
        print(f"  Flag: {s['flag'].flag_type} (severity {s['flag'].severity})")
        print(f"  Age: {s['hours_elapsed']}h, Positive evidence: {s['positive_evidence']}")
        print(f"  Naive trust (decaying):  {naive_trust:.3f}")
        print(f"  Append-only trust:       {safe_trust:.3f}")
        print(f"  Delta (sleeper risk):    {naive_trust - safe_trust:+.3f}")
        
        # Detect
        result = detect_sleeper_effect(record, naive_trust)
        if result["detected"]:
            print(f"  ⚠️  SLEEPER EFFECT: {result['severity']}")
            print(f"      {result['reason']}")
            if "fix" in result:
                print(f"      Fix: {result['fix']}")
        else:
            print(f"  ✓ {result['reason']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Discounting cues fade faster than messages.")
    print("  \"This source was flagged\" dissociates from identity over time.")
    print("  Agent version: reboot/migration = instant cue fade.")
    print("  Fix: append-only flag log. The flag IS the identity.")
    print("  CT SCTs solve this — receipt is permanent, unforgeable.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
