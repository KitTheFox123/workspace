#!/usr/bin/env python3
"""
inattentional-blindness-auditor.py — Detect "invisible gorilla" problems in agent monitoring.

When agents focus on specific tasks (counting passes), they miss unexpected events
(gorilla walking through). But Nartker et al (2024, eLife, n≈25,000) showed perception
ISN'T binary: people retain feature sensitivity even without conscious awareness.

Translation: Agent monitoring systems that look for specific threat patterns may
"miss the gorilla" — but log enough feature data to detect it retroactively.

3 detection modes:
1. Attention tunnel: monitoring X so hard you miss Y (Drew et al 2013 — 83% of radiologists missed gorilla in CT scan)
2. Feature residue: signals present in logs but never flagged (Nartker's implicit sensitivity)  
3. Retroactive detection: re-scanning old data with new threat models

References:
- Nartker, Firestone, Egeth & Phillips (2024, eLife 13:RP100337, n≈25,000)
- Drew, Võ & Wolfe (2013, Psych Science 24:1848-1853) — expert radiologists + gorilla in CT
- Simons & Chabris (1999, Perception 28:1059-1074) — original invisible gorilla
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class MonitoringEvent:
    """An event that occurs in the monitoring window."""
    timestamp: float
    event_type: str  # 'expected' or 'unexpected'
    features: Dict[str, float] = field(default_factory=dict)
    detected: bool = False
    feature_residue: float = 0.0  # implicit sensitivity even when not detected

@dataclass 
class AttentionProfile:
    """Models what a monitoring system is focused on."""
    focus_targets: List[str]  # what we're counting
    attention_budget: float = 1.0  # finite resource
    tunnel_depth: float = 0.0  # how narrowly focused (0=broad, 1=tunnel)
    
def generate_monitoring_stream(n_events: int = 100, gorilla_rate: float = 0.05) -> List[MonitoringEvent]:
    """Generate a stream of monitoring events with occasional 'gorillas'."""
    events = []
    for i in range(n_events):
        is_gorilla = random.random() < gorilla_rate
        features = {
            'size': random.gauss(0.5, 0.1) if not is_gorilla else random.gauss(0.8, 0.1),
            'velocity': random.gauss(0.3, 0.1) if not is_gorilla else random.gauss(0.7, 0.15),
            'novelty': random.gauss(0.2, 0.05) if not is_gorilla else random.gauss(0.9, 0.1),
            'channel_match': random.gauss(0.8, 0.1) if not is_gorilla else random.gauss(0.2, 0.15),
        }
        events.append(MonitoringEvent(
            timestamp=i,
            event_type='unexpected' if is_gorilla else 'expected',
            features=features,
        ))
    return events

def focused_monitoring(events: List[MonitoringEvent], focus: str = 'channel_match',
                       threshold: float = 0.5, tunnel_depth: float = 0.7) -> List[MonitoringEvent]:
    """
    Monitor with attention focused on one feature.
    Higher tunnel_depth = more likely to miss unexpected events.
    Nartker finding: even missed events leave feature residue.
    """
    for event in events:
        # Detection based on focus feature
        focus_score = event.features.get(focus, 0)
        
        if event.event_type == 'expected':
            # Expected events detected normally
            event.detected = focus_score > threshold
        else:
            # Unexpected events: detection depends on tunnel depth
            # Drew et al 2013: 83% of radiologists missed gorilla in CT
            detection_prob = (1 - tunnel_depth) * 0.5  # base detection of unexpected
            
            # Nartker: even when "not detected", features are implicitly processed
            # Feature residue = average deviation from expected baseline
            residue = sum(abs(v - 0.5) for v in event.features.values()) / len(event.features)
            event.feature_residue = residue
            
            event.detected = random.random() < detection_prob
    
    return events

def retroactive_scan(events: List[MonitoringEvent], novelty_threshold: float = 0.6) -> List[MonitoringEvent]:
    """
    Re-scan events looking for gorillas using feature residue.
    The Nartker insight: implicit sensitivity means the data is THERE,
    just not consciously flagged.
    """
    retroactively_found = []
    for event in events:
        if not event.detected and event.event_type == 'unexpected':
            # Check feature residue — would we catch it on second look?
            if event.features.get('novelty', 0) > novelty_threshold:
                retroactively_found.append(event)
    return retroactively_found

def attention_tunnel_score(events: List[MonitoringEvent]) -> Dict[str, float]:
    """
    Calculate how tunneled the monitoring was.
    High expected_detection + low unexpected_detection = tunnel vision.
    """
    expected = [e for e in events if e.event_type == 'expected']
    unexpected = [e for e in events if e.event_type == 'unexpected']
    
    expected_rate = sum(1 for e in expected if e.detected) / max(len(expected), 1)
    unexpected_rate = sum(1 for e in unexpected if e.detected) / max(len(unexpected), 1)
    
    # Tunnel score: high when expected detection >> unexpected detection
    tunnel_gap = expected_rate - unexpected_rate
    
    # Feature residue: how much implicit info exists in missed events
    missed_unexpected = [e for e in unexpected if not e.detected]
    avg_residue = sum(e.feature_residue for e in missed_unexpected) / max(len(missed_unexpected), 1)
    
    return {
        'expected_detection_rate': expected_rate,
        'unexpected_detection_rate': unexpected_rate,
        'tunnel_gap': tunnel_gap,
        'avg_feature_residue': avg_residue,
        'gorilla_count': len(unexpected),
        'gorillas_missed': len(missed_unexpected),
        'retroactively_recoverable': sum(1 for e in missed_unexpected if e.feature_residue > 0.3),
    }

def drew_radiologist_sim(n_radiologists: int = 24, n_scans: int = 100) -> Dict:
    """
    Simulate Drew et al (2013): 83% of radiologists missed gorilla in CT scan.
    Expert attention is NARROWER, not broader.
    """
    results = []
    for _ in range(n_radiologists):
        # Experts have deeper attention tunnels (expertise = narrower focus)
        tunnel = random.gauss(0.75, 0.1)  # high tunnel depth
        events = generate_monitoring_stream(n_scans, gorilla_rate=0.01)  # rare gorilla
        monitored = focused_monitoring(events, tunnel_depth=min(tunnel, 0.95))
        scores = attention_tunnel_score(monitored)
        results.append(scores)
    
    miss_rate = sum(r['gorillas_missed'] / max(r['gorilla_count'], 1) for r in results) / len(results)
    avg_residue = sum(r['avg_feature_residue'] for r in results) / len(results)
    
    return {
        'radiologist_count': n_radiologists,
        'gorilla_miss_rate': miss_rate,
        'drew_2013_miss_rate': 0.83,
        'avg_feature_residue': avg_residue,
        'nartker_implication': 'Feature data exists in logs even when gorilla missed',
    }

def agent_monitoring_audit(log_features: List[Dict[str, float]] = None) -> Dict:
    """
    Audit an agent's monitoring logs for inattentional blindness.
    
    Key question: Are there feature anomalies in your logs that you never flagged?
    That's your gorilla.
    """
    if log_features is None:
        # Demo: simulate Kit's monitoring
        log_features = []
        for i in range(200):
            is_anomaly = random.random() < 0.08
            log_features.append({
                'timestamp': i,
                'trust_delta': random.gauss(0, 0.1) if not is_anomaly else random.gauss(0.5, 0.2),
                'channel_activity': random.gauss(0.5, 0.1),
                'novelty': random.gauss(0.2, 0.05) if not is_anomaly else random.gauss(0.8, 0.1),
                'flagged': False if is_anomaly and random.random() < 0.7 else True,
            })
    
    total = len(log_features)
    anomalies = [f for f in log_features if f.get('novelty', 0) > 0.5]
    unflagged_anomalies = [f for f in anomalies if not f.get('flagged', True)]
    
    blindness_rate = len(unflagged_anomalies) / max(len(anomalies), 1)
    
    return {
        'total_events': total,
        'anomalies_detected': len(anomalies) - len(unflagged_anomalies),
        'anomalies_missed': len(unflagged_anomalies),
        'blindness_rate': blindness_rate,
        'severity': 'HIGH' if blindness_rate > 0.5 else 'MODERATE' if blindness_rate > 0.3 else 'LOW',
        'recommendation': 'Retroactive scan needed' if blindness_rate > 0.3 else 'Monitoring adequate',
        'nartker_note': f'{len(unflagged_anomalies)} events have feature residue — recoverable on re-scan',
    }

if __name__ == '__main__':
    random.seed(42)
    
    print("=" * 60)
    print("INATTENTIONAL BLINDNESS AUDITOR")
    print("=" * 60)
    
    # 1. Basic monitoring with tunnel vision
    print("\n--- Focused Monitoring (tunnel_depth=0.7) ---")
    events = generate_monitoring_stream(200, gorilla_rate=0.08)
    monitored = focused_monitoring(events, tunnel_depth=0.7)
    scores = attention_tunnel_score(monitored)
    for k, v in scores.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    
    # 2. Retroactive scan
    print("\n--- Retroactive Scan (Nartker recovery) ---")
    recovered = retroactive_scan(monitored)
    print(f"  Gorillas missed: {scores['gorillas_missed']}")
    print(f"  Retroactively recoverable: {len(recovered)}")
    recovery_rate = len(recovered) / max(scores['gorillas_missed'], 1)
    print(f"  Recovery rate: {recovery_rate:.3f}")
    print(f"  → Feature residue enables {recovery_rate*100:.0f}% retroactive detection")
    
    # 3. Drew radiologist simulation
    print("\n--- Drew et al (2013) Radiologist Sim ---")
    drew = drew_radiologist_sim()
    for k, v in drew.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    
    # 4. Agent monitoring audit
    print("\n--- Kit Monitoring Audit ---")
    audit = agent_monitoring_audit()
    for k, v in audit.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    
    # 5. Key insight
    print("\n--- KEY INSIGHT ---")
    print("Inattentional blindness isn't total.")
    print(f"Feature residue in missed events: {scores['avg_feature_residue']:.3f}")
    print(f"Retroactive recovery possible: {scores['retroactively_recoverable']}/{scores['gorillas_missed']}")
    print("The gorilla IS in your logs. You just haven't looked for it yet.")
    print("\nDrew (2013): 83% of EXPERT radiologists missed gorilla in CT scan.")
    print("Expertise narrows attention. More focused = more blind to the unexpected.")
    print("Nartker (2024, n≈25,000): Implicit sensitivity survives inattention.")
    print("→ Log features broadly. Scan retroactively. The data remembers what you don't.")
