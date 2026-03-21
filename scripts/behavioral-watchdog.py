#!/usr/bin/env python3
"""
behavioral-watchdog.py — Active behavioral monitoring with threshold + time-decay triggers.

Per santaclawd: "passive forensics vs active alerting are not the same system."

Two trigger modes:
1. THRESHOLD: immediate alert on counterparty drop, grade crash, divergence spike
2. TIME-DECAY: periodic audit on correction frequency degradation, entropy drift

Watches receipt streams and fires alerts before forensics would catch it.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class AlertLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass
class Receipt:
    timestamp: datetime
    counterparty: str
    action_type: str
    grade: str  # A-F
    correction: bool = False
    correction_type: Optional[str] = None  # self, witness, chain


@dataclass
class Alert:
    level: AlertLevel
    trigger: str  # THRESHOLD or TIME_DECAY
    signal: str
    detail: str
    timestamp: datetime
    recommended_action: str


class BehavioralWatchdog:
    """Active monitoring with dual trigger modes."""
    
    def __init__(
        self,
        agent_id: str,
        grade_crash_threshold: int = 2,      # grade drop of 2+ = alert
        counterparty_drop_window: timedelta = timedelta(hours=24),
        min_counterparties: int = 3,
        correction_floor: float = 0.05,       # below this = suspiciously perfect
        correction_ceiling: float = 0.50,     # above this = degrading
        entropy_min: float = 0.3,             # action type diversity floor
        decay_window: timedelta = timedelta(days=7),
    ):
        self.agent_id = agent_id
        self.grade_crash_threshold = grade_crash_threshold
        self.counterparty_drop_window = counterparty_drop_window
        self.min_counterparties = min_counterparties
        self.correction_floor = correction_floor
        self.correction_ceiling = correction_ceiling
        self.entropy_min = entropy_min
        self.decay_window = decay_window
        self.receipts: list[Receipt] = []
        self.alerts: list[Alert] = []
    
    def ingest(self, receipt: Receipt) -> list[Alert]:
        """Ingest a receipt and check threshold triggers (immediate)."""
        self.receipts.append(receipt)
        new_alerts = []
        
        # THRESHOLD 1: Grade crash
        grade_map = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        recent = [r for r in self.receipts[-10:] if r.counterparty == receipt.counterparty]
        if len(recent) >= 2:
            prev_grade = grade_map.get(recent[-2].grade, 0)
            curr_grade = grade_map.get(receipt.grade, 0)
            drop = prev_grade - curr_grade
            if drop >= self.grade_crash_threshold:
                alert = Alert(
                    level=AlertLevel.CRITICAL if drop >= 3 else AlertLevel.WARNING,
                    trigger="THRESHOLD",
                    signal="GRADE_CRASH",
                    detail=f"Grade dropped {recent[-2].grade}→{receipt.grade} with {receipt.counterparty}",
                    timestamp=receipt.timestamp,
                    recommended_action="REISSUE + counterparty re-attestation"
                )
                new_alerts.append(alert)
        
        # THRESHOLD 2: Divergence spike (JS divergence approximated by action type shift)
        if len(self.receipts) >= 20:
            from collections import Counter
            import math
            old_types = Counter(r.action_type for r in self.receipts[-20:-10])
            new_types = Counter(r.action_type for r in self.receipts[-10:])
            all_types = set(old_types) | set(new_types)
            
            # JS divergence
            total_old = sum(old_types.values()) or 1
            total_new = sum(new_types.values()) or 1
            
            kl = 0
            for t in all_types:
                p = (old_types.get(t, 0) / total_old) or 0.001
                q = (new_types.get(t, 0) / total_new) or 0.001
                m = (p + q) / 2
                if p > 0 and m > 0:
                    kl += 0.5 * p * math.log(p / m)
                if q > 0 and m > 0:
                    kl += 0.5 * q * math.log(q / m)
            
            if kl > 0.5:
                alert = Alert(
                    level=AlertLevel.CRITICAL if kl > 0.8 else AlertLevel.WARNING,
                    trigger="THRESHOLD",
                    signal="ACTION_DIVERGENCE",
                    detail=f"JS divergence={kl:.2f} between last 20 receipts (threshold 0.5)",
                    timestamp=receipt.timestamp,
                    recommended_action="behavioral-divergence-detector.py full audit"
                )
                new_alerts.append(alert)
        
        self.alerts.extend(new_alerts)
        return new_alerts
    
    def audit(self, now: Optional[datetime] = None) -> list[Alert]:
        """Periodic time-decay audit (run on schedule, not per-receipt)."""
        now = now or datetime.utcnow()
        new_alerts = []
        
        window_start = now - self.decay_window
        recent = [r for r in self.receipts if r.timestamp >= window_start]
        
        if not recent:
            new_alerts.append(Alert(
                level=AlertLevel.WARNING,
                trigger="TIME_DECAY",
                signal="NO_RECEIPTS",
                detail=f"No receipts in {self.decay_window.days}d window",
                timestamp=now,
                recommended_action="Check agent liveness"
            ))
            self.alerts.extend(new_alerts)
            return new_alerts
        
        # TIME_DECAY 1: Counterparty concentration
        counterparties = set(r.counterparty for r in recent)
        if len(counterparties) < self.min_counterparties:
            new_alerts.append(Alert(
                level=AlertLevel.WARNING,
                trigger="TIME_DECAY",
                signal="COUNTERPARTY_CONCENTRATION",
                detail=f"Only {len(counterparties)} counterparties in window (min {self.min_counterparties})",
                timestamp=now,
                recommended_action="Diversify interactions"
            ))
        
        # TIME_DECAY 2: Correction frequency
        corrections = [r for r in recent if r.correction]
        corr_rate = len(corrections) / len(recent)
        
        if corr_rate < self.correction_floor:
            new_alerts.append(Alert(
                level=AlertLevel.WARNING,
                trigger="TIME_DECAY",
                signal="SUSPICIOUSLY_PERFECT",
                detail=f"Correction rate {corr_rate:.2f} below floor {self.correction_floor} — hiding drift?",
                timestamp=now,
                recommended_action="correction-health-scorer.py audit"
            ))
        elif corr_rate > self.correction_ceiling:
            new_alerts.append(Alert(
                level=AlertLevel.WARNING,
                trigger="TIME_DECAY",
                signal="OVERCORRECTING",
                detail=f"Correction rate {corr_rate:.2f} above ceiling {self.correction_ceiling}",
                timestamp=now,
                recommended_action="Check for systematic error source"
            ))
        
        # TIME_DECAY 3: Action type entropy
        from collections import Counter
        import math
        type_counts = Counter(r.action_type for r in recent)
        total = sum(type_counts.values())
        entropy = -sum((c/total) * math.log2(c/total) for c in type_counts.values() if c > 0)
        max_entropy = math.log2(len(type_counts)) if len(type_counts) > 1 else 1
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        if norm_entropy < self.entropy_min:
            new_alerts.append(Alert(
                level=AlertLevel.WARNING,
                trigger="TIME_DECAY",
                signal="LOW_ENTROPY",
                detail=f"Action type entropy {norm_entropy:.2f} below {self.entropy_min} — monoculture behavior",
                timestamp=now,
                recommended_action="behavioral-drift-decomposer.py analysis"
            ))
        
        self.alerts.extend(new_alerts)
        return new_alerts
    
    def summary(self) -> dict:
        critical = sum(1 for a in self.alerts if a.level == AlertLevel.CRITICAL)
        warnings = sum(1 for a in self.alerts if a.level == AlertLevel.WARNING)
        return {
            "agent": self.agent_id,
            "total_receipts": len(self.receipts),
            "total_alerts": len(self.alerts),
            "critical": critical,
            "warnings": warnings,
            "status": "EMERGENCY" if critical > 2 else "DEGRADED" if critical > 0 else "WATCHING" if warnings > 0 else "HEALTHY",
            "alerts": [{"level": a.level.value, "trigger": a.trigger, "signal": a.signal, "detail": a.detail, "action": a.recommended_action} for a in self.alerts[-5:]]
        }


def demo():
    now = datetime(2026, 3, 21, 20, 0, 0)
    watchdog = BehavioralWatchdog("kit_fox")
    
    # Healthy period
    for i in range(15):
        watchdog.ingest(Receipt(
            timestamp=now - timedelta(hours=30-i*2),
            counterparty=["bro_agent", "funwolf", "santaclawd", "axiomeye"][i % 4],
            action_type=["deliver", "verify", "attest", "correct"][i % 4],
            grade="A" if i != 7 else "B",
            correction=(i == 7),
            correction_type="witness" if i == 7 else None
        ))
    
    # Grade crash
    alerts = watchdog.ingest(Receipt(
        timestamp=now - timedelta(hours=1),
        counterparty="bro_agent",
        action_type="deliver",
        grade="D",
    ))
    
    print("=== THRESHOLD ALERTS (per-receipt) ===")
    for a in alerts:
        print(f"  [{a.level.value}] {a.signal}: {a.detail}")
    
    # Time-decay audit
    print("\n=== TIME-DECAY AUDIT (periodic) ===")
    decay_alerts = watchdog.audit(now)
    for a in decay_alerts:
        print(f"  [{a.level.value}] {a.signal}: {a.detail}")
        print(f"    → {a.recommended_action}")
    
    print(f"\n=== SUMMARY ===")
    s = watchdog.summary()
    print(f"Status: {s['status']} | Receipts: {s['total_receipts']} | Alerts: {s['total_alerts']} (critical={s['critical']}, warnings={s['warnings']})")


if __name__ == "__main__":
    demo()
