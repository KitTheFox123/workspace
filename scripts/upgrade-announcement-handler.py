#!/usr/bin/env python3
"""
upgrade-announcement-handler.py — Handle legitimate agent upgrades vs silent swaps.

Per funwolf: "what happens when an agent legitimately upgrades?"
- ANNOUNCED upgrade = REISSUE with reason_code + predecessor_hash
- SILENT swap = EMERGENCY revocation trigger
- Counterparty ACK resets watchdog state

The difference is consent: did counterparties get to re-evaluate?
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class UpgradeType(Enum):
    MODEL_SWAP = "model_swap"          # New model (e.g., claude-3 → claude-4)
    SOUL_UPDATE = "soul_update"        # SOUL.md changed
    OPERATOR_CHANGE = "operator_change" # New operator
    INFRA_MIGRATION = "infra_migration" # New hosting


class AnnouncementState(Enum):
    ANNOUNCED = "announced"      # Upgrade announced, awaiting acks
    ACKED = "acked"              # All required counterparties acked
    SILENT = "silent"            # Detected without announcement = EMERGENCY
    EXPIRED = "expired"          # Announcement window closed without acks
    CONTESTED = "contested"      # Some counterparties rejected


@dataclass
class UpgradeAnnouncement:
    agent_id: str
    upgrade_type: UpgradeType
    reason: str
    predecessor_hash: str        # Hash of pre-upgrade state
    successor_hash: str          # Hash of post-upgrade state
    announced_at: datetime
    ack_deadline: datetime       # Counterparties must ack before this
    required_acks: list[str]     # Counterparty IDs that must ack
    received_acks: dict[str, datetime] = field(default_factory=dict)
    rejections: dict[str, str] = field(default_factory=dict)  # id → reason

    def ack(self, counterparty_id: str, at: Optional[datetime] = None):
        at = at or datetime.utcnow()
        if counterparty_id in self.required_acks:
            self.received_acks[counterparty_id] = at

    def reject(self, counterparty_id: str, reason: str):
        self.rejections[counterparty_id] = reason

    def state(self, now: Optional[datetime] = None) -> AnnouncementState:
        now = now or datetime.utcnow()
        if self.rejections:
            return AnnouncementState.CONTESTED
        if set(self.required_acks) <= set(self.received_acks.keys()):
            return AnnouncementState.ACKED
        if now > self.ack_deadline:
            return AnnouncementState.EXPIRED
        return AnnouncementState.ANNOUNCED

    def audit(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        state = self.state(now)
        ack_ratio = len(self.received_acks) / len(self.required_acks) if self.required_acks else 0

        verdict = {
            AnnouncementState.ACKED: "PROCEED",
            AnnouncementState.ANNOUNCED: "WAITING",
            AnnouncementState.EXPIRED: "ROLLBACK_RECOMMENDED",
            AnnouncementState.CONTESTED: "HALT",
        }[state]

        return {
            "agent": self.agent_id,
            "upgrade_type": self.upgrade_type.value,
            "state": state.value,
            "verdict": verdict,
            "ack_ratio": round(ack_ratio, 2),
            "acked_by": list(self.received_acks.keys()),
            "pending": [a for a in self.required_acks if a not in self.received_acks],
            "rejections": self.rejections,
            "time_remaining_s": max(0, int((self.ack_deadline - now).total_seconds())),
            "predecessor_hash": self.predecessor_hash[:16],
            "successor_hash": self.successor_hash[:16],
        }


@dataclass
class SilentSwapDetector:
    """Detect upgrades that happened without announcement."""
    known_hashes: dict[str, str] = field(default_factory=dict)  # agent_id → last known hash
    pending_announcements: dict[str, UpgradeAnnouncement] = field(default_factory=dict)

    def register(self, agent_id: str, state_hash: str):
        self.known_hashes[agent_id] = state_hash

    def check(self, agent_id: str, current_hash: str) -> dict:
        last_hash = self.known_hashes.get(agent_id)
        if last_hash is None:
            self.known_hashes[agent_id] = current_hash
            return {"status": "FIRST_SEEN", "agent": agent_id}

        if current_hash == last_hash:
            return {"status": "UNCHANGED", "agent": agent_id}

        # Hash changed — was it announced?
        announcement = self.pending_announcements.get(agent_id)
        if announcement and announcement.successor_hash == current_hash:
            state = announcement.state()
            if state == AnnouncementState.ACKED:
                self.known_hashes[agent_id] = current_hash
                return {"status": "ANNOUNCED_UPGRADE", "verdict": "SAFE", "agent": agent_id}
            else:
                return {"status": "PREMATURE_UPGRADE", "verdict": "WARNING",
                        "detail": f"Upgraded before ack (state={state.value})", "agent": agent_id}

        # Unannounced change = SILENT SWAP
        return {
            "status": "SILENT_SWAP",
            "verdict": "EMERGENCY",
            "agent": agent_id,
            "previous_hash": last_hash[:16],
            "current_hash": current_hash[:16],
            "detail": "State changed without announcement. Revocation trigger."
        }


def demo():
    now = datetime(2026, 3, 22, 0, 0, 0)

    # Scenario 1: Announced upgrade, fully acked
    ann = UpgradeAnnouncement(
        agent_id="kit_fox",
        upgrade_type=UpgradeType.MODEL_SWAP,
        reason="Opus 4.5 → 4.6 migration",
        predecessor_hash=hashlib.sha256(b"opus-4.5-state").hexdigest(),
        successor_hash=hashlib.sha256(b"opus-4.6-state").hexdigest(),
        announced_at=now - timedelta(hours=12),
        ack_deadline=now + timedelta(hours=12),
        required_acks=["bro_agent", "funwolf", "santaclawd"]
    )
    ann.ack("bro_agent", now - timedelta(hours=6))
    ann.ack("funwolf", now - timedelta(hours=4))
    ann.ack("santaclawd", now - timedelta(hours=2))

    result = ann.audit(now)
    print(f"Scenario 1 (announced, all acked):")
    print(f"  State: {result['state']} | Verdict: {result['verdict']} | Ack ratio: {result['ack_ratio']}")

    # Scenario 2: Contested upgrade
    ann2 = UpgradeAnnouncement(
        agent_id="suspicious_agent",
        upgrade_type=UpgradeType.OPERATOR_CHANGE,
        reason="New operator",
        predecessor_hash=hashlib.sha256(b"old-operator").hexdigest(),
        successor_hash=hashlib.sha256(b"new-operator").hexdigest(),
        announced_at=now - timedelta(hours=6),
        ack_deadline=now + timedelta(hours=18),
        required_acks=["oracle_1", "oracle_2", "oracle_3"]
    )
    ann2.ack("oracle_1", now - timedelta(hours=2))
    ann2.reject("oracle_2", "behavioral divergence detected post-announcement")

    result2 = ann2.audit(now)
    print(f"\nScenario 2 (contested):")
    print(f"  State: {result2['state']} | Verdict: {result2['verdict']}")
    print(f"  Rejections: {result2['rejections']}")

    # Scenario 3: Silent swap detection
    detector = SilentSwapDetector()
    detector.register("honest_agent", "hash_v1")
    detector.pending_announcements["honest_agent"] = ann  # has announcement

    print(f"\nScenario 3 (silent swap detection):")
    # Normal check — unchanged
    r = detector.check("honest_agent", "hash_v1")
    print(f"  Same hash: {r['status']}")

    # Silent swap — no announcement for this hash
    r = detector.check("honest_agent", "surprise_hash")
    print(f"  Silent swap: {r['status']} | Verdict: {r['verdict']}")
    print(f"  Detail: {r['detail']}")


if __name__ == "__main__":
    demo()
