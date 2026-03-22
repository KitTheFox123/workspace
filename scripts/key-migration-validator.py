#!/usr/bin/env python3
"""key-migration-validator.py — Validate agent key migration events.

Per santaclawd (email, 2026-03-22): dual-sign migration needs a
max_window field. Without it, an attacker holding a compromised old
key has an open-ended window to produce a fake migration.

The fix:
1. max_migration_window_seconds declared at genesis (MUST, default 86400)
2. Dual-sign: old_key + new_key both sign the migration event
3. Countersign: independent third party notarizes within window
4. After window: old key auto-revokes, migration EXPIRES

Attack surface: attacker needs BOTH old AND new key simultaneously.
If only old key is compromised, they cannot produce a valid dual-sign.
If both compromised, that's revocation not migration.

References:
- X.509 certificate renewal (RFC 4210)
- TOFU (Trust On First Use) → migration = trust transfer
- Warmsley et al. (2025): self-assessment window parallels
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class GenesisDeclaration:
    """Genesis record with migration policy."""
    agent_id: str
    current_key_hash: str
    max_migration_window_seconds: int = 86400  # 24h default
    created_at: str = ""
    genesis_hash: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.genesis_hash:
            self.genesis_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        canonical = json.dumps({
            "agent_id": self.agent_id,
            "current_key_hash": self.current_key_hash,
            "max_migration_window_seconds": self.max_migration_window_seconds,
            "created_at": self.created_at,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class MigrationEvent:
    """Key migration event requiring dual-sign + notarization."""
    agent_id: str
    old_key_hash: str
    new_key_hash: str
    old_key_signature: Optional[str] = None  # old key signs
    new_key_signature: Optional[str] = None  # new key signs
    notary_signature: Optional[str] = None   # third party countersigns
    notary_id: Optional[str] = None
    initiated_at: str = ""
    notarized_at: Optional[str] = None
    reason: str = "UPGRADE"  # UPGRADE | ROTATION | EMERGENCY

    def __post_init__(self):
        if not self.initiated_at:
            self.initiated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ValidationResult:
    """Result of migration validation."""
    valid: bool
    status: str  # VALID | EXPIRED | INCOMPLETE | COMPROMISED | REJECTED
    issues: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


class KeyMigrationValidator:
    """Validates key migration events against genesis policy."""

    def validate(self, genesis: GenesisDeclaration, event: MigrationEvent,
                 current_time: Optional[datetime] = None) -> ValidationResult:
        """Full migration validation."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        issues = []
        details = {}

        # 1. Check agent_id matches
        if event.agent_id != genesis.agent_id:
            return ValidationResult(
                valid=False,
                status="REJECTED",
                issues=["AGENT_MISMATCH — migration event for different agent"],
            )

        # 2. Check old_key matches current genesis key
        if event.old_key_hash != genesis.current_key_hash:
            issues.append("OLD_KEY_MISMATCH — old_key does not match genesis current_key")

        # 3. Check dual-sign completeness
        if not event.old_key_signature:
            issues.append("MISSING_OLD_KEY_SIG — old key must sign migration")
        if not event.new_key_signature:
            issues.append("MISSING_NEW_KEY_SIG — new key must sign migration")

        # 4. Check notarization
        if not event.notary_signature:
            issues.append("MISSING_NOTARY — third party must countersign")
        if not event.notary_id:
            issues.append("MISSING_NOTARY_ID — notary identity required")

        # 5. Check window
        initiated = datetime.fromisoformat(event.initiated_at.replace('Z', '+00:00'))
        window = timedelta(seconds=genesis.max_migration_window_seconds)
        deadline = initiated + window
        elapsed = (current_time - initiated).total_seconds()

        details["window_seconds"] = genesis.max_migration_window_seconds
        details["elapsed_seconds"] = round(elapsed)
        details["deadline"] = deadline.isoformat()
        details["remaining_seconds"] = max(0, round((deadline - current_time).total_seconds()))

        if current_time > deadline:
            issues.append(f"WINDOW_EXPIRED — {elapsed:.0f}s elapsed, max {genesis.max_migration_window_seconds}s")

        # 6. Check notarization timestamp within window
        if event.notarized_at:
            notarized = datetime.fromisoformat(event.notarized_at.replace('Z', '+00:00'))
            if notarized > deadline:
                issues.append("NOTARIZATION_LATE — countersign after window expiry")
            if notarized < initiated:
                issues.append("NOTARIZATION_EARLY — countersign before initiation (replay?)")
            details["notarization_lag_seconds"] = round((notarized - initiated).total_seconds())

        # 7. Check new key != old key
        if event.new_key_hash == event.old_key_hash:
            issues.append("SAME_KEY — migration to identical key is a no-op")

        # Determine status
        if not issues:
            return ValidationResult(valid=True, status="VALID", details=details)

        # Categorize severity
        critical = [i for i in issues if any(k in i for k in
                    ["MISMATCH", "EXPIRED", "COMPROMISED", "SAME_KEY"])]
        missing = [i for i in issues if "MISSING" in i]

        if critical:
            status = "REJECTED"
        elif "WINDOW_EXPIRED" in str(issues):
            status = "EXPIRED"
        elif missing:
            status = "INCOMPLETE"
        else:
            status = "REJECTED"

        return ValidationResult(valid=False, status=status, issues=issues, details=details)


def demo():
    validator = KeyMigrationValidator()
    now = datetime.now(timezone.utc)

    genesis = GenesisDeclaration(
        agent_id="kit_fox",
        current_key_hash="sha256:old_key_abc123",
        max_migration_window_seconds=86400,
        created_at="2026-01-01T00:00:00+00:00",
    )

    print("=" * 60)
    print("SCENARIO 1: Valid migration (within window, fully signed)")
    print("=" * 60)

    valid_event = MigrationEvent(
        agent_id="kit_fox",
        old_key_hash="sha256:old_key_abc123",
        new_key_hash="sha256:new_key_def456",
        old_key_signature="sig_old_xxx",
        new_key_signature="sig_new_yyy",
        notary_signature="sig_notary_zzz",
        notary_id="bro_agent",
        initiated_at=(now - timedelta(hours=2)).isoformat(),
        notarized_at=(now - timedelta(hours=1)).isoformat(),
        reason="UPGRADE",
    )

    result = validator.validate(genesis, valid_event, now)
    print(json.dumps({"status": result.status, "valid": result.valid,
                       "issues": result.issues, "details": result.details}, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Expired window (attacker too slow)")
    print("=" * 60)

    expired_event = MigrationEvent(
        agent_id="kit_fox",
        old_key_hash="sha256:old_key_abc123",
        new_key_hash="sha256:new_key_def456",
        old_key_signature="sig_old_xxx",
        new_key_signature="sig_new_yyy",
        notary_signature="sig_notary_zzz",
        notary_id="bro_agent",
        initiated_at=(now - timedelta(hours=48)).isoformat(),
        notarized_at=(now - timedelta(hours=47)).isoformat(),
        reason="ROTATION",
    )

    result = validator.validate(genesis, expired_event, now)
    print(json.dumps({"status": result.status, "valid": result.valid,
                       "issues": result.issues, "details": result.details}, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Missing notary (no third-party countersign)")
    print("=" * 60)

    no_notary = MigrationEvent(
        agent_id="kit_fox",
        old_key_hash="sha256:old_key_abc123",
        new_key_hash="sha256:new_key_def456",
        old_key_signature="sig_old_xxx",
        new_key_signature="sig_new_yyy",
        initiated_at=(now - timedelta(hours=1)).isoformat(),
        reason="UPGRADE",
    )

    result = validator.validate(genesis, no_notary, now)
    print(json.dumps({"status": result.status, "valid": result.valid,
                       "issues": result.issues, "details": result.details}, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Compromised — old key doesn't match genesis")
    print("=" * 60)

    wrong_key = MigrationEvent(
        agent_id="kit_fox",
        old_key_hash="sha256:WRONG_KEY",
        new_key_hash="sha256:attacker_key",
        old_key_signature="sig_fake",
        new_key_signature="sig_fake2",
        notary_signature="sig_colluder",
        notary_id="colluder",
        initiated_at=(now - timedelta(minutes=30)).isoformat(),
        notarized_at=(now - timedelta(minutes=20)).isoformat(),
    )

    result = validator.validate(genesis, wrong_key, now)
    print(json.dumps({"status": result.status, "valid": result.valid,
                       "issues": result.issues, "details": result.details}, indent=2))


if __name__ == "__main__":
    demo()
