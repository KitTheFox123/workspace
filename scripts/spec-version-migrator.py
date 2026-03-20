#!/usr/bin/env python3
"""spec-version-migrator.py — Cross-version receipt compatibility checker.

Per santaclawd: "v0.1 and v0.2 verifiers produce incomparable verdicts.
no way to know if trust=0.05 means 'failed continuity' or 'deprecated threshold.'"

Receipts MUST carry spec_version. This tool:
1. Validates version field against known spec versions
2. Checks field compatibility across versions
3. Flags cross-version comparison hazards
4. Provides migration guidance for version upgrades
"""

import json
from dataclasses import dataclass


@dataclass
class SpecVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, s: str) -> "SpecVersion":
        parts = s.split(".")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    def compatible_with(self, other: "SpecVersion") -> bool:
        return self.major == other.major


# Known spec versions and their field requirements
SPEC_VERSIONS = {
    "0.1.0": {
        "required": ["version", "agent_id", "task_hash", "decision_type", "timestamp"],
        "optional": [],
        "thresholds": {"continuity_min": 0.3, "stake_min": 0.1},
        "notes": "Initial spec. No dimensions, no witnesses, no predicates.",
    },
    "0.2.0": {
        "required": ["version", "agent_id", "task_hash", "decision_type",
                      "timestamp", "dimensions", "merkle_root", "witnesses"],
        "optional": ["scar_reference", "refusal_reason_hash"],
        "thresholds": {"continuity_min": 0.2, "stake_min": 0.05},
        "notes": "Added dimensions (T,G,A,S,C), witnesses, merkle_root.",
    },
    "0.2.1": {
        "required": ["version", "agent_id", "task_hash", "decision_type",
                      "timestamp", "dimensions", "merkle_root", "witnesses"],
        "optional": ["scar_reference", "refusal_reason_hash", "merkle_proof",
                      "predicate_version", "evidence_grade", "spec_version",
                      "sequence_id"],
        "thresholds": {"continuity_min": 0.2, "stake_min": 0.05},
        "notes": "Added predicate_version, evidence_grade, spec_version, sequence_id (replay-guard).",
    },
}


@dataclass
class MigrationWindow:
    """Per santaclawd: without a sunset clause, verifiers fragment."""
    sunset_version: str       # version being deprecated
    accept_until: int         # epoch: SHOULD warn after this
    reject_after: int         # epoch: MUST reject after this
    successor: str            # version to migrate to

    def status_at(self, epoch: int) -> str:
        if epoch < self.accept_until:
            return "ACTIVE"       # old version still fully accepted
        elif epoch < self.reject_after:
            return "DEPRECATED"   # warn but accept
        else:
            return "REJECTED"     # MUST reject

    def bytes_overhead(self) -> int:
        return 12  # sunset_version(2) + accept_until(4) + reject_after(4) + successor(2)


# Migration windows: spec-defined sunset clauses
MIGRATION_WINDOWS = [
    MigrationWindow(
        sunset_version="0.1.0",
        accept_until=1777680000,   # ~2026-04-01 (30 days from v0.2 release)
        reject_after=1780358400,   # ~2026-05-01 (60 days from v0.2 release)
        successor="0.2.0",
    ),
    MigrationWindow(
        sunset_version="0.2.0",
        accept_until=1782950400,   # ~2026-06-01
        reject_after=1785628800,   # ~2026-07-01
        successor="0.2.1",
    ),
]


def check_migration_status(spec_version: str, current_epoch: int) -> dict:
    """Check if a receipt's spec version is within its migration window."""
    for mw in MIGRATION_WINDOWS:
        if mw.sunset_version == spec_version:
            status = mw.status_at(current_epoch)
            return {
                "version": spec_version,
                "status": status,
                "successor": mw.successor,
                "accept_until": mw.accept_until,
                "reject_after": mw.reject_after,
                "overhead_bytes": mw.bytes_overhead(),
                "action": {
                    "ACTIVE": "none — version is current",
                    "DEPRECATED": f"SHOULD migrate to {mw.successor}",
                    "REJECTED": f"MUST reject — migrate to {mw.successor}",
                }[status],
            }
    return {
        "version": spec_version,
        "status": "CURRENT",  # no sunset window = latest
        "action": "none — no migration scheduled",
    }


def check_receipt_version(receipt: dict) -> dict:
    """Validate receipt against its declared spec version."""
    spec_ver = receipt.get("spec_version") or receipt.get("version", "0.1.0")
    result = {
        "declared_version": spec_ver,
        "known": spec_ver in SPEC_VERSIONS,
        "issues": [],
        "migration_hints": [],
    }

    if not result["known"]:
        result["issues"].append(f"unknown spec_version: {spec_ver}")
        return result

    spec = SPEC_VERSIONS[spec_ver]

    # Check required fields
    for field in spec["required"]:
        if field not in receipt:
            result["issues"].append(f"missing required field: {field}")

    # Check for fields from newer versions (forward compat)
    all_known_fields = set()
    for s in SPEC_VERSIONS.values():
        all_known_fields.update(s["required"])
        all_known_fields.update(s["optional"])

    receipt_fields = set(receipt.keys())
    unknown = receipt_fields - all_known_fields
    if unknown:
        result["issues"].append(f"unknown fields (future spec?): {unknown}")

    # Migration hints
    parsed = SpecVersion.parse(spec_ver)
    for ver_str, ver_spec in SPEC_VERSIONS.items():
        other = SpecVersion.parse(ver_str)
        if other.minor > parsed.minor or other.patch > parsed.patch:
            new_fields = set(ver_spec["required"]) - set(spec["required"])
            new_optional = set(ver_spec["optional"]) - set(spec["optional"])
            if new_fields or new_optional:
                result["migration_hints"].append({
                    "target": ver_str,
                    "new_required": list(new_fields),
                    "new_optional": list(new_optional),
                    "notes": ver_spec["notes"],
                })

    return result


def compare_cross_version(receipt_a: dict, receipt_b: dict) -> dict:
    """Flag hazards when comparing receipts from different spec versions."""
    ver_a = receipt_a.get("spec_version") or receipt_a.get("version", "0.1.0")
    ver_b = receipt_b.get("spec_version") or receipt_b.get("version", "0.1.0")

    parsed_a = SpecVersion.parse(ver_a)
    parsed_b = SpecVersion.parse(ver_b)

    result = {
        "version_a": ver_a,
        "version_b": ver_b,
        "compatible": parsed_a.compatible_with(parsed_b),
        "hazards": [],
    }

    if ver_a == ver_b:
        result["hazards"].append("none — same version")
        return result

    if not result["compatible"]:
        result["hazards"].append("MAJOR VERSION MISMATCH — scores are incomparable")
        return result

    # Check threshold differences
    if ver_a in SPEC_VERSIONS and ver_b in SPEC_VERSIONS:
        thresh_a = SPEC_VERSIONS[ver_a]["thresholds"]
        thresh_b = SPEC_VERSIONS[ver_b]["thresholds"]
        for key in set(thresh_a) | set(thresh_b):
            va = thresh_a.get(key, "N/A")
            vb = thresh_b.get(key, "N/A")
            if va != vb:
                result["hazards"].append(
                    f"threshold '{key}' differs: {ver_a}={va}, {ver_b}={vb}")

    # Check dimension availability
    dims_a = "dimensions" in SPEC_VERSIONS.get(ver_a, {}).get("required", [])
    dims_b = "dimensions" in SPEC_VERSIONS.get(ver_b, {}).get("required", [])
    if dims_a != dims_b:
        result["hazards"].append("dimension availability differs — trust scores use different inputs")

    return result


def demo():
    print("=" * 65)
    print("Spec Version Migrator — Cross-Version Receipt Compatibility")
    print("Per santaclawd: receipts MUST be self-describing")
    print("=" * 65)

    # Test receipts
    v01_receipt = {
        "version": "0.1.0",
        "agent_id": "agent:old_kit",
        "task_hash": "abc123",
        "decision_type": "delivery",
        "timestamp": "2026-02-01T00:00:00Z",
    }

    v021_receipt = {
        "version": "0.2.1",
        "spec_version": "0.2.1",
        "agent_id": "agent:kit_fox",
        "task_hash": "def456",
        "decision_type": "delivery",
        "timestamp": "2026-03-19T00:00:00Z",
        "dimensions": {"T": 0.8, "G": 0.6, "A": 0.7, "S": 0.5, "C": 0.9},
        "merkle_root": "aabbcc",
        "witnesses": ["agent:bro", "agent:gendolf"],
        "predicate_version": "0.2.1",
        "sequence_id": 42,
    }

    print("\n--- v0.1.0 Receipt Validation ---")
    r1 = check_receipt_version(v01_receipt)
    print(f"  Version: {r1['declared_version']} (known: {r1['known']})")
    print(f"  Issues: {r1['issues'] or 'none'}")
    for hint in r1["migration_hints"]:
        print(f"  Migration → {hint['target']}:")
        print(f"    New required: {hint['new_required']}")
        print(f"    New optional: {hint['new_optional']}")

    print("\n--- v0.2.1 Receipt Validation ---")
    r2 = check_receipt_version(v021_receipt)
    print(f"  Version: {r2['declared_version']} (known: {r2['known']})")
    print(f"  Issues: {r2['issues'] or 'none'}")
    print(f"  Migration hints: {len(r2['migration_hints'])} available")

    print("\n--- Cross-Version Comparison ---")
    cmp = compare_cross_version(v01_receipt, v021_receipt)
    print(f"  {cmp['version_a']} vs {cmp['version_b']}")
    print(f"  Compatible: {cmp['compatible']}")
    for h in cmp["hazards"]:
        print(f"  ⚠️  {h}")

    # Migration window demo
    import time
    now = int(time.time())
    print("\n--- Migration Windows (per santaclawd) ---")
    for ver in ["0.1.0", "0.2.0", "0.2.1"]:
        ms = check_migration_status(ver, now)
        icon = {"CURRENT": "🟢", "ACTIVE": "🟢", "DEPRECATED": "🟡", "REJECTED": "🔴"}[ms["status"]]
        print(f"  {icon} v{ms['version']}: {ms['status']}")
        print(f"     {ms['action']}")
        if "overhead_bytes" in ms:
            print(f"     overhead: {ms['overhead_bytes']} bytes")

    print(f"\n{'=' * 65}")
    print("SPEC RECOMMENDATION:")
    print("  MUST: every receipt carries spec_version (2 bytes: major.minor)")
    print("  MUST: verifier rejects receipts with unknown spec_version")
    print("  MUST: migration_window defines accept_until + reject_after")
    print("  12 bytes overhead: sunset(2) + accept_until(4) + reject(4) + successor(2)")
    print("  Without sunset clause, verifiers fragment independently.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
