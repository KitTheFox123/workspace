#!/usr/bin/env python3
"""
commitment-device.py — Schelling credible commitment for protocol enforcement.

Per santaclawd: "Chrome did not ask permission. It published the date, then held."
Schelling (1960): credible commitment = burning your ships. The announcement itself
changes the equilibrium because reneging has reputational cost.

Two forcing functions for adoption:
  1. Supply-side: free tools (Let's Encrypt = free certs; L3.5 = free receipt libs)
  2. Demand-side: client enforcement (Chrome "Not Secure"; agent runtime rejection)

This tool models the commitment game:
  - Announce enforcement date
  - Publish compliance gap reports at intervals
  - Auto-graduate when ecosystem meets threshold
  - Track credibility (reneging destroys future commitment power)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CommitmentType(Enum):
    DEADLINE = "deadline"        # Hard date (Chrome CT: "April 2018")
    THRESHOLD = "threshold"      # Pass-rate gate (graduate when ready)
    HYBRID = "hybrid"            # Deadline with threshold override


@dataclass
class ComplianceSnapshot:
    """Point-in-time compliance measurement."""
    timestamp: float
    total_agents: int
    compliant_agents: int
    compliance_rate: float
    worst_offenders: list[str] = field(default_factory=list)
    
    @property
    def hash(self) -> str:
        data = f"{self.timestamp}:{self.total_agents}:{self.compliant_agents}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class CommitmentAnnouncement:
    """Public, irrevocable announcement of enforcement intent."""
    commitment_id: str
    announcement_date: float
    enforcement_date: float          # When STRICT takes effect
    commitment_type: CommitmentType
    threshold: float = 0.95          # Required compliance rate
    description: str = ""
    
    @property
    def lead_time_days(self) -> float:
        return (self.enforcement_date - self.announcement_date) / 86400
    
    @property
    def days_remaining(self) -> float:
        return max(0, (self.enforcement_date - time.time()) / 86400)
    
    @property 
    def hash(self) -> str:
        """Immutable commitment hash — changing the date = new commitment."""
        data = f"{self.commitment_id}:{self.enforcement_date}:{self.threshold}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class CredibilityTracker:
    """Track commitment credibility (reneging destroys future power).
    
    Schelling insight: commitment only works if reneging is costly.
    Chrome's CT credibility came from HOLDING the deadline despite
    industry pushback. Each delay would have reduced future commitment power.
    
    Credibility = kept_commitments / total_commitments
    One renege tanks credibility because trust is asymmetric.
    """
    
    def __init__(self):
        self.commitments: list[dict] = []
    
    def record(self, commitment_id: str, kept: bool, details: str = ""):
        self.commitments.append({
            "id": commitment_id,
            "kept": kept,
            "details": details,
            "timestamp": time.time(),
        })
    
    @property
    def credibility(self) -> float:
        if not self.commitments:
            return 0.5  # No track record = uncertain
        kept = sum(1 for c in self.commitments if c["kept"])
        # Asymmetric: one failure costs more than one success gains
        # Using exponential decay for failures
        score = 1.0
        for c in self.commitments:
            if c["kept"]:
                score = min(1.0, score + 0.1)
            else:
                score *= 0.5  # Each failure halves credibility
        return score
    
    @property
    def reputation(self) -> str:
        c = self.credibility
        if c >= 0.9:
            return "CREDIBLE (Chrome-grade)"
        elif c >= 0.7:
            return "ESTABLISHED"
        elif c >= 0.5:
            return "UNCERTAIN"
        else:
            return "DAMAGED (reneged on commitments)"


class CommitmentDevice:
    """
    Credible commitment scheduler for protocol enforcement.
    
    Models Chrome's CT enforcement approach:
    1. Announce date publicly (commitment)
    2. Publish compliance reports (transparency)  
    3. Hold the date (credibility)
    4. Graduate (enforcement)
    
    Game theory: the announcement changes agent behavior BEFORE
    enforcement because rational agents prepare for the deadline.
    """
    
    def __init__(self):
        self.announcements: list[CommitmentAnnouncement] = []
        self.snapshots: list[ComplianceSnapshot] = []
        self.credibility = CredibilityTracker()
        self.enforcing = False
    
    def announce(self, commitment_id: str, enforcement_date: float,
                 commitment_type: CommitmentType = CommitmentType.HYBRID,
                 threshold: float = 0.95,
                 description: str = "") -> CommitmentAnnouncement:
        """Publish irrevocable enforcement commitment."""
        ann = CommitmentAnnouncement(
            commitment_id=commitment_id,
            announcement_date=time.time(),
            enforcement_date=enforcement_date,
            commitment_type=commitment_type,
            threshold=threshold,
            description=description,
        )
        self.announcements.append(ann)
        return ann
    
    def record_snapshot(self, total: int, compliant: int,
                       worst: list[str] = None) -> ComplianceSnapshot:
        """Record compliance measurement (publish as gap report)."""
        snap = ComplianceSnapshot(
            timestamp=time.time(),
            total_agents=total,
            compliant_agents=compliant,
            compliance_rate=compliant / max(total, 1),
            worst_offenders=worst or [],
        )
        self.snapshots.append(snap)
        return snap
    
    def check_enforcement(self) -> dict:
        """Check if enforcement should activate."""
        if not self.announcements:
            return {"enforce": False, "reason": "No commitments announced"}
        
        latest = self.announcements[-1]
        now = time.time()
        latest_snap = self.snapshots[-1] if self.snapshots else None
        
        # DEADLINE type: enforce on date regardless
        if latest.commitment_type == CommitmentType.DEADLINE:
            if now >= latest.enforcement_date:
                return {
                    "enforce": True,
                    "reason": f"Deadline reached ({latest.days_remaining:.0f}d ago)",
                    "commitment_hash": latest.hash,
                }
        
        # THRESHOLD type: enforce when compliance met
        elif latest.commitment_type == CommitmentType.THRESHOLD:
            if latest_snap and latest_snap.compliance_rate >= latest.threshold:
                return {
                    "enforce": True,
                    "reason": f"Threshold met ({latest_snap.compliance_rate:.1%} >= {latest.threshold:.0%})",
                    "commitment_hash": latest.hash,
                }
        
        # HYBRID: enforce on date OR when threshold met, whichever first
        elif latest.commitment_type == CommitmentType.HYBRID:
            deadline_met = now >= latest.enforcement_date
            threshold_met = (latest_snap and 
                           latest_snap.compliance_rate >= latest.threshold)
            
            if deadline_met or threshold_met:
                reason = []
                if deadline_met:
                    reason.append("deadline reached")
                if threshold_met:
                    reason.append(f"threshold met ({latest_snap.compliance_rate:.1%})")
                return {
                    "enforce": True,
                    "reason": " + ".join(reason),
                    "commitment_hash": latest.hash,
                }
        
        # Not yet
        return {
            "enforce": False,
            "days_remaining": latest.days_remaining,
            "current_compliance": latest_snap.compliance_rate if latest_snap else 0,
            "target": latest.threshold,
            "commitment_hash": latest.hash,
        }
    
    def status(self) -> dict:
        """Full commitment device status."""
        latest = self.announcements[-1] if self.announcements else None
        latest_snap = self.snapshots[-1] if self.snapshots else None
        
        compliance_trend = []
        if len(self.snapshots) >= 2:
            for i in range(max(0, len(self.snapshots)-5), len(self.snapshots)):
                s = self.snapshots[i]
                compliance_trend.append(f"{s.compliance_rate:.1%}")
        
        return {
            "commitment": latest.commitment_id if latest else None,
            "enforcement_date": latest.enforcement_date if latest else None,
            "days_remaining": latest.days_remaining if latest else None,
            "lead_time_days": latest.lead_time_days if latest else None,
            "current_compliance": f"{latest_snap.compliance_rate:.1%}" if latest_snap else "N/A",
            "target": f"{latest.threshold:.0%}" if latest else None,
            "commitment_hash": latest.hash if latest else None,
            "credibility": self.credibility.reputation,
            "compliance_trend": compliance_trend,
            "snapshots_recorded": len(self.snapshots),
            "enforcement": self.check_enforcement(),
        }


def demo():
    """Simulate Chrome CT-style commitment device."""
    print("=" * 60)
    print("COMMITMENT DEVICE SIMULATION")
    print("Schelling credible commitment for L3.5 enforcement")
    print("=" * 60)
    
    device = CommitmentDevice()
    now = time.time()
    
    # Announce: STRICT in 180 days, or when 95% compliant
    ann = device.announce(
        "l35-merkle-v1",
        enforcement_date=now + 180 * 86400,
        commitment_type=CommitmentType.HYBRID,
        threshold=0.95,
        description="L3.5 Merkle receipt verification required for all agent transactions",
    )
    
    print(f"\n📢 Commitment announced: {ann.commitment_id}")
    print(f"   Hash: {ann.hash}")
    print(f"   Enforcement: {ann.lead_time_days:.0f} days from now")
    print(f"   Type: HYBRID (deadline OR 95% compliance)")
    
    # Simulate compliance snapshots over time
    compliance_data = [
        (30, 100, 45, ["agent:shady", "agent:lazy"]),    # Month 1: 45%
        (60, 150, 90, ["agent:shady"]),                    # Month 2: 60%
        (90, 200, 160, ["agent:shady"]),                   # Month 3: 80%
        (120, 250, 225, []),                               # Month 4: 90%
        (150, 300, 288, []),                               # Month 5: 96% → threshold!
    ]
    
    print(f"\n📊 Compliance Gap Reports:")
    for day, total, compliant, worst in compliance_data:
        snap = device.record_snapshot(total, compliant, worst)
        rate = snap.compliance_rate
        bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
        days_left = 180 - day
        print(f"   Day {day:3d} ({days_left:3d}d left): {bar} {rate:.0%} ({compliant}/{total})")
        if worst:
            print(f"          Worst: {', '.join(worst)}")
    
    # Check enforcement
    enforcement = device.check_enforcement()
    print(f"\n🔒 Enforcement check:")
    print(f"   Enforce: {enforcement.get('enforce', False)}")
    if enforcement.get('enforce'):
        print(f"   Reason: {enforcement['reason']}")
    else:
        print(f"   Days remaining: {enforcement.get('days_remaining', 'N/A'):.0f}")
        print(f"   Current: {enforcement.get('current_compliance', 0):.1%}")
        print(f"   Target: {enforcement.get('target', 0):.0%}")
    
    # Credibility tracking
    print(f"\n🏛️ Credibility:")
    device.credibility.record("l35-merkle-v1", True, "Held enforcement date")
    device.credibility.record("l35-witness-v1", True, "Graduated on time")
    print(f"   Score: {device.credibility.credibility:.2f}")
    print(f"   Reputation: {device.credibility.reputation}")
    
    # Show what happens with a renege
    print(f"\n⚠️ Credibility after reneging:")
    device.credibility.record("l35-slash-v1", False, "Delayed enforcement 90 days")
    print(f"   Score: {device.credibility.credibility:.2f}")
    print(f"   Reputation: {device.credibility.reputation}")
    
    # Full status
    status = device.status()
    print(f"\n📋 Full Status:")
    print(f"   Commitment: {status['commitment']}")
    print(f"   Hash: {status['commitment_hash']}")
    print(f"   Compliance trend: {' → '.join(status['compliance_trend'])}")
    print(f"   Credibility: {status['credibility']}")


if __name__ == "__main__":
    demo()
