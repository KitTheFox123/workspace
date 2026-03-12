#!/usr/bin/env python3
"""
scope-version-pin.py — Version-pinned scope manifests for receipt verification.

Based on:
- santaclawd: "scope-version pinning. CID needs scope VERSION not just scope hash"
- Confluent Schema Registry: backward/forward/full compatibility
- The orphan receipt problem: v1 null receipt unverifiable against v2 scope

Receipt verification requires: what scope was ACTIVE when the receipt was issued?
Pin receipts to scope CID (content-addressed, immutable version).
Old receipts stay verifiable against their own version forever.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CompatMode(Enum):
    BACKWARD = "backward"   # New reader can read old data
    FORWARD = "forward"     # Old reader can read new data
    FULL = "full"           # Both directions
    NONE = "none"           # Breaking change


@dataclass
class Capability:
    name: str
    required: bool
    added_version: int
    removed_version: Optional[int] = None  # None = still active


@dataclass
class ScopeVersion:
    version: int
    capabilities: list[Capability]
    timestamp: float = 0.0

    def cid(self) -> str:
        content = json.dumps({
            "version": self.version,
            "capabilities": [
                {"name": c.name, "required": c.required,
                 "added": c.added_version, "removed": c.removed_version}
                for c in self.capabilities
            ],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def active_capabilities(self) -> list[str]:
        return [c.name for c in self.capabilities if c.removed_version is None]


@dataclass
class NullReceipt:
    capability: str
    scope_cid: str  # Pinned to scope version
    scope_version: int
    agent_id: str
    reason: str
    timestamp: float = 0.0

    def receipt_hash(self) -> str:
        content = json.dumps({
            "capability": self.capability,
            "scope_cid": self.scope_cid,
            "scope_version": self.scope_version,
            "agent_id": self.agent_id,
            "reason": self.reason,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def check_compatibility(old: ScopeVersion, new: ScopeVersion) -> CompatMode:
    """Check schema evolution compatibility."""
    old_caps = set(c.name for c in old.capabilities if c.removed_version is None)
    new_caps = set(c.name for c in new.capabilities if c.removed_version is None)

    removed = old_caps - new_caps
    added = new_caps - old_caps

    if not removed and not added:
        return CompatMode.FULL
    if not removed:
        return CompatMode.BACKWARD  # New has superset
    if not added:
        return CompatMode.FORWARD   # Old has superset
    return CompatMode.NONE  # Both added and removed


def verify_receipt(receipt: NullReceipt,
                   scope_versions: dict[str, ScopeVersion]) -> tuple[bool, str]:
    """Verify a null receipt against its pinned scope version."""
    if receipt.scope_cid not in scope_versions:
        return False, f"ORPHAN: scope CID {receipt.scope_cid} not found"

    scope = scope_versions[receipt.scope_cid]
    active = scope.active_capabilities()

    if receipt.capability not in active:
        return False, f"INVALID: {receipt.capability} not in scope v{scope.version}"

    return True, f"VERIFIED: against scope v{scope.version} (CID {receipt.scope_cid})"


def main():
    print("=" * 70)
    print("SCOPE VERSION PINNING")
    print("santaclawd: 'CID needs scope VERSION not just scope hash'")
    print("=" * 70)

    # Scope evolution
    v1_caps = [
        Capability("reply_mentions", True, 1),
        Capability("check_email", True, 1),
        Capability("post_research", False, 1),
        Capability("moderate_content", False, 1),
    ]
    scope_v1 = ScopeVersion(1, v1_caps, 1000.0)

    v2_caps = [
        Capability("reply_mentions", True, 1),
        Capability("check_email", True, 1),
        Capability("post_research", False, 1),
        Capability("moderate_content", False, 1, removed_version=2),  # Removed!
        Capability("absence_attestation", True, 2),  # Added!
    ]
    scope_v2 = ScopeVersion(2, v2_caps, 2000.0)

    # Version registry (CID → scope)
    versions = {
        scope_v1.cid(): scope_v1,
        scope_v2.cid(): scope_v2,
    }

    print(f"\n--- Scope Versions ---")
    print(f"v1 CID: {scope_v1.cid()}, caps: {scope_v1.active_capabilities()}")
    print(f"v2 CID: {scope_v2.cid()}, caps: {scope_v2.active_capabilities()}")

    compat = check_compatibility(scope_v1, scope_v2)
    print(f"v1→v2 compatibility: {compat.value}")

    # Receipts
    print(f"\n--- Receipt Verification ---")

    # Receipt issued under v1 for moderate_content (later removed in v2)
    receipt_v1 = NullReceipt("moderate_content", scope_v1.cid(), 1, "kit_fox",
                              "Spam, not worth engaging")

    # Verify against v1 (should pass)
    ok, msg = verify_receipt(receipt_v1, versions)
    print(f"v1 receipt (moderate_content): {msg}")

    # What if we tried to verify against v2's CID? (would fail)
    receipt_bad = NullReceipt("moderate_content", scope_v2.cid(), 2, "kit_fox",
                               "Spam, not worth engaging")
    ok2, msg2 = verify_receipt(receipt_bad, versions)
    print(f"v2 receipt (moderate_content): {msg2}")

    # Receipt for new v2 capability
    receipt_v2 = NullReceipt("absence_attestation", scope_v2.cid(), 2, "kit_fox",
                              "No absence detected this heartbeat")
    ok3, msg3 = verify_receipt(receipt_v2, versions)
    print(f"v2 receipt (absence_attestation): {msg3}")

    # Orphan receipt (unknown CID)
    receipt_orphan = NullReceipt("reply_mentions", "deadbeef12345678", 99, "kit_fox",
                                  "Old receipt from deleted scope")
    ok4, msg4 = verify_receipt(receipt_orphan, versions)
    print(f"orphan receipt: {msg4}")

    print(f"\n--- Compatibility Matrix ---")
    print(f"{'Pattern':<20} {'Type':<12} {'Agent Scopes':<30}")
    print("-" * 62)
    patterns = [
        ("Add capability", "BACKWARD", "v2 reader verifies v1 receipts ✓"),
        ("Remove capability", "FORWARD", "v1 receipts stay valid at v1 CID ✓"),
        ("Add + remove", "NONE", "Breaking — old receipts need v1 CID"),
        ("Rename capability", "NONE", "Same as remove + add"),
    ]
    for p, t, desc in patterns:
        print(f"{p:<20} {t:<12} {desc}")

    print(f"\n--- Key Insight ---")
    print("santaclawd: 'old receipts become orphans'")
    print()
    print("Fix: receipt.scope_cid = CID(scope_at_issue_time)")
    print("NOT: receipt.scope_cid = CID(scope_latest)")
    print()
    print("Version registry preserves ALL scope versions.")
    print("Old receipts verifiable forever against their pinned CID.")
    print("Schema evolution follows Confluent pattern:")
    print("  BACKWARD (add-only) = safe default for agent scopes")
    print("  Removing capabilities = breaking change = new CID required")


if __name__ == "__main__":
    main()
