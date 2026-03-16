#!/usr/bin/env python3
"""
tech-revolution-phase-detector.py — Carlota Perez framework for protocol adoption.

Every successful protocol follows the same arc:
  1. INSTALLATION: Spec published + early adopter enforcement
  2. TURNING POINT: Crisis or forcing function (fraud, breach, regulation)
  3. DEPLOYMENT: Mass adoption, late majority, becomes invisible infrastructure

Historical examples:
  - TCP/IP: DARPA spec (1974) → BSD impl (1983) → WWW crisis of interop → universal
  - TLS/CT: RFC 6962 (2013) → Chrome enforcement (2018) → DigiNotar crisis → universal
  - HTTPS: RFC 2818 (2000) → Let's Encrypt (2015) → Snowden revelations → 95%+

The turning point is always a crisis that makes the cost of NOT adopting > cost of adopting.
For agent trust: the turning point will be the first high-profile agent fraud with no receipt trail.

Per santaclawd's thread: spec product-neutral, enforcement product-specific.
The anti-pattern: enforcer owns the spec (IE6/ActiveX, vendor lock-in).
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    IRRUPTION = "irruption"           # New tech appears, early experiments
    FRENZY = "frenzy"                 # Speculation, over-investment, competing standards
    TURNING_POINT = "turning_point"   # Crisis forces consolidation
    SYNERGY = "synergy"               # Mass adoption, complementary growth
    MATURITY = "maturity"             # Saturation, next revolution begins


class SignalType(Enum):
    SPEC_PUBLISHED = "spec_published"
    FIRST_ENFORCER = "first_enforcer"
    SECOND_ENFORCER = "second_enforcer"
    CRISIS_EVENT = "crisis_event"
    ADOPTION_THRESHOLD = "adoption_threshold"
    INVISIBLE_INFRA = "invisible_infra"


@dataclass
class AdoptionSignal:
    signal_type: SignalType
    description: str
    timestamp: float
    adoption_pct: float  # Estimated adoption at this point
    confidence: float = 0.8


@dataclass
class ProtocolTimeline:
    name: str
    signals: list[AdoptionSignal] = field(default_factory=list)
    
    def current_phase(self) -> Phase:
        """Determine current Perez phase from signals."""
        types = {s.signal_type for s in self.signals}
        
        if SignalType.INVISIBLE_INFRA in types:
            return Phase.MATURITY
        if SignalType.ADOPTION_THRESHOLD in types:
            return Phase.SYNERGY
        if SignalType.CRISIS_EVENT in types:
            return Phase.TURNING_POINT
        if SignalType.FIRST_ENFORCER in types:
            return Phase.FRENZY
        if SignalType.SPEC_PUBLISHED in types:
            return Phase.IRRUPTION
        return Phase.IRRUPTION
    
    def time_to_turning_point(self) -> Optional[float]:
        """Estimate time to turning point based on historical patterns."""
        spec_time = None
        enforcer_time = None
        crisis_time = None
        
        for s in self.signals:
            if s.signal_type == SignalType.SPEC_PUBLISHED:
                spec_time = s.timestamp
            if s.signal_type == SignalType.FIRST_ENFORCER:
                enforcer_time = s.timestamp
            if s.signal_type == SignalType.CRISIS_EVENT:
                crisis_time = s.timestamp
        
        if crisis_time:
            return 0  # Already past turning point
        
        # Historical: spec → turning point averages ~5-8 years
        # But first enforcer → turning point is ~2-3 years
        if enforcer_time:
            elapsed = time.time() - enforcer_time
            avg_gap = 2.5 * 365 * 86400  # 2.5 years
            remaining = max(0, avg_gap - elapsed)
            return remaining / 86400  # days
        
        if spec_time:
            elapsed = time.time() - spec_time
            avg_gap = 6 * 365 * 86400  # 6 years
            remaining = max(0, avg_gap - elapsed)
            return remaining / 86400
        
        return None
    
    def adoption_velocity(self) -> float:
        """Adoption rate change (% per year)."""
        if len(self.signals) < 2:
            return 0.0
        
        sorted_signals = sorted(self.signals, key=lambda s: s.timestamp)
        first = sorted_signals[0]
        last = sorted_signals[-1]
        
        time_years = (last.timestamp - first.timestamp) / (365 * 86400)
        if time_years < 0.1:
            return 0.0
        
        return (last.adoption_pct - first.adoption_pct) / time_years
    
    def pattern_match(self) -> dict:
        """Compare against historical protocol timelines."""
        phase = self.current_phase()
        velocity = self.adoption_velocity()
        
        # Historical benchmarks
        benchmarks = {
            "TCP/IP": {"spec_to_deploy": 9, "crisis": "interop fragmentation", 
                       "peak_velocity": 15.0},
            "TLS/CT": {"spec_to_deploy": 5, "crisis": "DigiNotar compromise",
                       "peak_velocity": 20.0},
            "HTTPS": {"spec_to_deploy": 15, "crisis": "Snowden + Chrome 'Not Secure'",
                       "peak_velocity": 18.0},
            "DNS-SEC": {"spec_to_deploy": 20, "crisis": "Kaminsky attack (2008)",
                        "peak_velocity": 5.0},  # Still low adoption
        }
        
        # Find closest match
        closest = None
        closest_score = 0
        
        for name, bench in benchmarks.items():
            score = 0
            if velocity > 0:
                vel_ratio = min(velocity, bench["peak_velocity"]) / max(velocity, bench["peak_velocity"])
                score += vel_ratio * 0.5
            
            phase_scores = {
                Phase.IRRUPTION: 0.2,
                Phase.FRENZY: 0.4,
                Phase.TURNING_POINT: 0.6,
                Phase.SYNERGY: 0.8,
                Phase.MATURITY: 1.0,
            }
            score += phase_scores.get(phase, 0) * 0.5
            
            if score > closest_score:
                closest_score = score
                closest = name
        
        return {
            "phase": phase.value,
            "velocity": f"{velocity:.1f}%/yr",
            "closest_historical": closest,
            "match_confidence": f"{closest_score:.0%}",
            "prediction": self._predict(phase, velocity),
        }
    
    def _predict(self, phase: Phase, velocity: float) -> str:
        predictions = {
            Phase.IRRUPTION: "Early. Need first enforcer to create momentum. "
                            "Watch for an agent runtime willing to reject unverified receipts.",
            Phase.FRENZY: "Competing implementations, no standard enforcer yet. "
                         "Crisis will force consolidation. Build the spec now.",
            Phase.TURNING_POINT: "Crisis is happening. Ship enforcement immediately. "
                               "Every month of delay = market share to whoever ships first.",
            Phase.SYNERGY: "Mass adoption in progress. Focus on edge cases and "
                          "backward compatibility. The hard part is over.",
            Phase.MATURITY: "Infrastructure. Invisible. Next revolution starting somewhere.",
        }
        return predictions.get(phase, "Unknown phase")


def demo():
    """Demo with historical and current timelines."""
    now = time.time()
    
    # Historical: TLS Certificate Transparency
    ct = ProtocolTimeline("TLS/CT")
    ct.signals = [
        AdoptionSignal(SignalType.SPEC_PUBLISHED, "RFC 6962", 
                      now - 13*365*86400, 0.0),  # 2013
        AdoptionSignal(SignalType.FIRST_ENFORCER, "Chrome EV enforcement",
                      now - 11*365*86400, 5.0),   # 2015
        AdoptionSignal(SignalType.CRISIS_EVENT, "DigiNotar + Symantec distrust",
                      now - 9*365*86400, 30.0),    # 2017
        AdoptionSignal(SignalType.SECOND_ENFORCER, "Safari CT enforcement",
                      now - 7*365*86400, 70.0),    # 2019
        AdoptionSignal(SignalType.ADOPTION_THRESHOLD, "95%+ CT compliance",
                      now - 5*365*86400, 95.0),    # 2021
        AdoptionSignal(SignalType.INVISIBLE_INFRA, "CT is invisible infra",
                      now - 2*365*86400, 99.0),    # 2024
    ]
    
    # Current: L3.5 Agent Trust Receipts
    l35 = ProtocolTimeline("L3.5 Trust Receipts")
    l35.signals = [
        AdoptionSignal(SignalType.SPEC_PUBLISHED, "isnad-rfc + L3.5 dimension types",
                      now - 45*86400, 0.0),   # ~45 days ago
        AdoptionSignal(SignalType.FIRST_ENFORCER, "consumer-receipt-enforcer.py (reference)",
                      now - 1*86400, 0.1),     # yesterday
    ]
    
    # DNSSEC (cautionary tale — spec without forcing function)
    dnssec = ProtocolTimeline("DNSSEC")
    dnssec.signals = [
        AdoptionSignal(SignalType.SPEC_PUBLISHED, "RFC 2535",
                      now - 26*365*86400, 0.0),   # 1999
        AdoptionSignal(SignalType.CRISIS_EVENT, "Kaminsky DNS attack",
                      now - 18*365*86400, 2.0),    # 2008
        AdoptionSignal(SignalType.FIRST_ENFORCER, "Root zone signed",
                      now - 16*365*86400, 5.0),    # 2010
        # Still only ~30% adoption in 2026
        AdoptionSignal(SignalType.ADOPTION_THRESHOLD, "~30% validation",
                      now, 30.0),
    ]
    
    for timeline in [ct, l35, dnssec]:
        print(f"\n{'='*60}")
        print(f"  {timeline.name}")
        print(f"{'='*60}")
        
        result = timeline.pattern_match()
        print(f"  Phase: {result['phase']}")
        print(f"  Velocity: {result['velocity']}")
        print(f"  Closest historical: {result['closest_historical']}")
        print(f"  Match confidence: {result['match_confidence']}")
        print(f"  Prediction: {result['prediction']}")
        
        ttp = timeline.time_to_turning_point()
        if ttp is not None:
            if ttp == 0:
                print(f"  Turning point: PAST")
            else:
                print(f"  Est. turning point: {ttp:.0f} days")
        
        print(f"  Signals: {len(timeline.signals)}")
        for s in timeline.signals:
            age_years = (now - s.timestamp) / (365 * 86400)
            print(f"    [{s.signal_type.value}] {s.description} "
                  f"({age_years:.1f}y ago, {s.adoption_pct:.0f}%)")
    
    # Key lesson
    print(f"\n{'='*60}")
    print("KEY LESSON")
    print(f"{'='*60}")
    print("""
  DNSSEC vs CT: same crisis-response pattern, different outcomes.
  
  DNSSEC: spec (1999) → crisis (Kaminsky 2008) → root signed (2010) → 30% (2026)
  CT:     spec (2013) → enforcer (Chrome 2015) → crisis (DigiNotar) → 99% (2024)
  
  Difference: Chrome ENFORCED. No browser enforces DNSSEC validation.
  The spec is necessary. The crisis is the catalyst. But the ENFORCER is what
  converts catalyst into adoption.
  
  L3.5 needs: spec (done) + enforcer (building) + crisis (coming).
  The crisis we can't manufacture. The enforcer we can build NOW.
""")


if __name__ == "__main__":
    demo()
