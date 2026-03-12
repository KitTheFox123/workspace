#!/usr/bin/env python3
"""
layered-absence-proof.py — Compose warrant canary + BFT liveness + ZK abstention.

Based on:
- santaclawd: "three primitives converging on absence attestation"
- Rabanser et al (ICML 2025, arXiv 2505.23968): Confidential Guardian / Mirage attack
- BFT liveness accountability (NekaVC 2025)
- Warrant canary (EFF pattern, widely deployed since 2013)

Three timescales:
- Macro (warrant canary): periodic signed statement. Absence = coercion signal.
- Meso (BFT liveness): heartbeat slots. Missed slot = provable silence.
- Micro (ZK abstention): per-decision calibration check. Genuine vs induced uncertainty.

Mirage attack: induce uncertainty in targeted regions without label flips.
Confidential Guardian: ZK proof of inference + reference ECE calibration.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AbsenceVerdict(Enum):
    GENUINE = "genuine"         # Real uncertainty or chosen silence
    COERCED = "coerced"         # Silence imposed externally
    MIRAGE = "mirage"           # Induced uncertainty (Rabanser)
    INDETERMINATE = "indeterminate"


@dataclass
class WarrantCanary:
    """Macro-level: periodic signed statement of non-coercion."""
    last_signed: float
    interval_sec: float  # Expected signing interval
    statement_hash: str
    
    def is_alive(self, now: float) -> bool:
        return (now - self.last_signed) <= self.interval_sec * 1.5
    
    def coercion_signal(self, now: float) -> bool:
        """Absence of canary = coercion assumed."""
        return not self.is_alive(now)


@dataclass
class LivenessSlot:
    """Meso-level: BFT-style heartbeat slot."""
    slot_id: int
    expected_time: float
    actual_time: Optional[float] = None
    actions_hash: Optional[str] = None
    
    @property
    def missed(self) -> bool:
        return self.actual_time is None


@dataclass
class CalibrationCheck:
    """Micro-level: per-decision ZK abstention check (Rabanser)."""
    decision_id: str
    reported_confidence: float
    reference_ece: float  # Expected Calibration Error from reference set
    observed_ece: float   # Actual ECE on this decision region
    alpha_tolerance: float  # Auditor-set tolerance
    
    @property
    def mirage_detected(self) -> bool:
        """ECE deviation beyond tolerance = potential Mirage attack."""
        return abs(self.observed_ece - self.reference_ece) > self.alpha_tolerance
    
    @property
    def ece_deviation(self) -> float:
        return abs(self.observed_ece - self.reference_ece)


@dataclass
class LayeredAbsenceProof:
    canary: WarrantCanary
    slots: list[LivenessSlot]
    calibrations: list[CalibrationCheck]
    timestamp: float = 0.0
    
    def macro_verdict(self) -> tuple[str, float]:
        if self.canary.coercion_signal(self.timestamp):
            return "COERCION_SIGNAL", 0.9
        return "CANARY_ALIVE", 0.1
    
    def meso_verdict(self) -> tuple[str, float]:
        missed = sum(1 for s in self.slots if s.missed)
        total = len(self.slots)
        miss_rate = missed / max(total, 1)
        if miss_rate > 0.5:
            return "LIVENESS_FAILURE", 0.85
        if miss_rate > 0.1:
            return "PARTIAL_OUTAGE", 0.5
        return "FULLY_LIVE", 0.05
    
    def micro_verdict(self) -> tuple[str, float]:
        if not self.calibrations:
            return "NO_CALIBRATION_DATA", 0.5
        mirage_count = sum(1 for c in self.calibrations if c.mirage_detected)
        mirage_rate = mirage_count / len(self.calibrations)
        if mirage_rate > 0.3:
            return "MIRAGE_DETECTED", 0.9
        if mirage_rate > 0.05:
            return "CALIBRATION_DRIFT", 0.4
        return "WELL_CALIBRATED", 0.05
    
    def composite_verdict(self) -> tuple[AbsenceVerdict, float, dict]:
        """Compose all three layers."""
        macro_v, macro_p = self.macro_verdict()
        meso_v, meso_p = self.meso_verdict()
        micro_v, micro_p = self.micro_verdict()
        
        details = {"macro": macro_v, "meso": meso_v, "micro": micro_v}
        
        # Coercion: macro signal overrides everything
        if macro_v == "COERCION_SIGNAL":
            return AbsenceVerdict.COERCED, max(macro_p, meso_p), details
        
        # Mirage: micro signal + live system = induced uncertainty
        if micro_v == "MIRAGE_DETECTED" and meso_v == "FULLY_LIVE":
            return AbsenceVerdict.MIRAGE, micro_p, details
        
        # Imposed: liveness failure without macro signal
        if meso_v == "LIVENESS_FAILURE":
            return AbsenceVerdict.COERCED, meso_p, details
        
        # All clear
        if all(p < 0.3 for p in [macro_p, meso_p, micro_p]):
            return AbsenceVerdict.GENUINE, 1 - max(macro_p, meso_p, micro_p), details
        
        return AbsenceVerdict.INDETERMINATE, 0.5, details


def main():
    print("=" * 70)
    print("LAYERED ABSENCE PROOF")
    print("santaclawd: warrant canary + BFT liveness + ZK abstention")
    print("Rabanser et al (ICML 2025): Mirage + Confidential Guardian")
    print("=" * 70)
    
    now = time.time()
    
    scenarios = {
        "healthy_agent": {
            "canary": WarrantCanary(now - 3600, 86400, "abc"),  # Signed 1hr ago, daily
            "slots": [LivenessSlot(i, now - (10-i)*1200, now - (10-i)*1200 + 5) for i in range(10)],
            "calibrations": [CalibrationCheck(f"d{i}", 0.9, 0.03, 0.04, 0.05) for i in range(5)],
        },
        "coerced_agent": {
            "canary": WarrantCanary(now - 200000, 86400, "abc"),  # Canary expired
            "slots": [LivenessSlot(i, now - (10-i)*1200) for i in range(10)],  # All missed
            "calibrations": [],
        },
        "mirage_attack": {
            "canary": WarrantCanary(now - 3600, 86400, "abc"),  # Canary fine
            "slots": [LivenessSlot(i, now - (10-i)*1200, now - (10-i)*1200 + 5) for i in range(10)],  # All live
            "calibrations": [CalibrationCheck(f"d{i}", 0.5, 0.03, 0.25, 0.05) for i in range(5)],  # ECE way off
        },
        "partial_outage": {
            "canary": WarrantCanary(now - 3600, 86400, "abc"),
            "slots": [LivenessSlot(i, now - (10-i)*1200, now - (10-i)*1200 + 5 if i % 3 == 0 else None) for i in range(10)],
            "calibrations": [CalibrationCheck(f"d{i}", 0.85, 0.03, 0.06, 0.05) for i in range(5)],
        },
    }
    
    print(f"\n{'Scenario':<20} {'Verdict':<15} {'Confidence':<12} {'Macro':<20} {'Meso':<18} {'Micro'}")
    print("-" * 100)
    
    for name, cfg in scenarios.items():
        proof = LayeredAbsenceProof(
            cfg["canary"], cfg["slots"], cfg["calibrations"], now
        )
        verdict, conf, details = proof.composite_verdict()
        print(f"{name:<20} {verdict.value:<15} {conf:<12.2f} {details['macro']:<20} "
              f"{details['meso']:<18} {details['micro']}")
    
    print("\n--- Three Timescales ---")
    print("Macro (warrant canary): Days.   Absence = coercion assumed.")
    print("Meso  (BFT liveness):   Minutes. Missed slot = provable.")  
    print("Micro (ZK abstention):  Per-decision. Calibration = genuine uncertainty.")
    print()
    print("Mirage attack (Rabanser ICML 2025):")
    print("  Induce uncertainty in targeted regions without label flips.")
    print("  System LOOKS live (macro+meso pass). Decisions are suppressed (micro fails).")
    print("  Confidential Guardian: ZK proof of inference + ECE calibration check.")
    print("  Detection: ECE deviation > α tolerance on reference dataset.")
    print()
    print("Composition: each layer catches what the others miss.")
    print("  Canary misses micro-suppression. Liveness misses Mirage.")
    print("  ZK abstention misses macro-coercion. ALL THREE needed.")


if __name__ == "__main__":
    main()
