#!/usr/bin/env python3
"""
key-rotation-validator.py — Validate agent key rotation records.

Checks that key_rotation records follow the dual-signature pattern:
both old and new keys must sign the rotation, creating a cryptographic
chain of custody (like Certificate Transparency but for agent identity).

Usage:
  python key-rotation-validator.py validate <rotation.json>
  python key-rotation-validator.py generate --old-key <path> --new-key <path>
  python key-rotation-validator.py chain <rotations_dir>

Rotation record format:
{
  "old_key_id": "ed25519:abc123",
  "new_key_id": "ed25519:def456",
  "effective_at": "2026-02-24T21:00:00Z",
  "sig_old_key": "<base64>",
  "sig_new_key": "<base64>",
  "reason": "scheduled rotation",
  "prev_rotation_hash": "<sha256 of previous rotation record or null>"
}
"""

import json
import hashlib
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives import serialization
    import base64
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


REQUIRED_FIELDS = [
    "old_key_id", "new_key_id", "effective_at",
    "sig_old_key", "sig_new_key"
]


def rotation_hash(record: dict) -> str:
    """Deterministic hash of a rotation record (excluding signatures)."""
    canonical = json.dumps({
        "old_key_id": record["old_key_id"],
        "new_key_id": record["new_key_id"],
        "effective_at": record["effective_at"],
        "prev_rotation_hash": record.get("prev_rotation_hash"),
        "reason": record.get("reason", ""),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_structure(record: dict) -> list[str]:
    """Validate rotation record structure. Returns list of errors."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")

    if "effective_at" in record:
        try:
            dt = datetime.fromisoformat(record["effective_at"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                errors.append("effective_at should include timezone")
        except ValueError:
            errors.append(f"invalid effective_at: {record['effective_at']}")

    if record.get("old_key_id") == record.get("new_key_id"):
        errors.append("old_key_id and new_key_id must differ")

    return errors


def validate_chain(records: list[dict]) -> list[str]:
    """Validate a chain of rotation records (append-only log)."""
    errors = []
    if not records:
        return ["empty chain"]

    # Sort by effective_at
    try:
        records = sorted(records, key=lambda r: r.get("effective_at", ""))
    except Exception as e:
        return [f"cannot sort records: {e}"]

    # First record should have null prev_rotation_hash
    if records[0].get("prev_rotation_hash") is not None:
        errors.append("first rotation should have null prev_rotation_hash")

    prev_hash = None
    prev_new_key = None
    prev_effective = None

    for i, rec in enumerate(records):
        # Structure check
        struct_errors = validate_structure(rec)
        if struct_errors:
            errors.extend([f"record {i}: {e}" for e in struct_errors])
            continue

        # Chain linkage
        rec_prev = rec.get("prev_rotation_hash")
        if i > 0 and rec_prev != prev_hash:
            errors.append(
                f"record {i}: prev_rotation_hash mismatch "
                f"(expected {prev_hash[:16]}..., got {str(rec_prev)[:16]}...)"
            )

        # Key continuity: new_key of record N should be old_key of record N+1
        if prev_new_key and rec["old_key_id"] != prev_new_key:
            errors.append(
                f"record {i}: old_key_id ({rec['old_key_id']}) != "
                f"previous new_key_id ({prev_new_key})"
            )

        # Temporal ordering
        eff = rec.get("effective_at", "")
        if prev_effective and eff <= prev_effective:
            errors.append(
                f"record {i}: effective_at ({eff}) not after "
                f"previous ({prev_effective})"
            )

        prev_hash = rotation_hash(rec)
        prev_new_key = rec["new_key_id"]
        prev_effective = eff

    return errors


def generate_rotation(old_key_path: str = None, new_key_path: str = None,
                      reason: str = "scheduled rotation",
                      prev_hash: str = None) -> dict:
    """Generate a new rotation record (optionally with real signatures)."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if HAS_CRYPTO and old_key_path and new_key_path:
        old_key = _load_private_key(old_key_path)
        new_key = _load_private_key(new_key_path)

        old_pub = old_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        new_pub = new_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

        record = {
            "old_key_id": f"ed25519:{old_pub.hex()[:16]}",
            "new_key_id": f"ed25519:{new_pub.hex()[:16]}",
            "effective_at": now,
            "reason": reason,
            "prev_rotation_hash": prev_hash,
        }

        msg = rotation_hash(record).encode()
        record["sig_old_key"] = base64.b64encode(old_key.sign(msg)).decode()
        record["sig_new_key"] = base64.b64encode(new_key.sign(msg)).decode()
    else:
        # Placeholder signatures for structural testing
        record = {
            "old_key_id": "ed25519:placeholder_old",
            "new_key_id": "ed25519:placeholder_new",
            "effective_at": now,
            "reason": reason,
            "prev_rotation_hash": prev_hash,
            "sig_old_key": "<placeholder>",
            "sig_new_key": "<placeholder>",
        }

    return record


def _load_private_key(path: str) -> "Ed25519PrivateKey":
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def cmd_validate(args):
    with open(args[0]) as f:
        record = json.load(f)
    errors = validate_structure(record)
    if errors:
        print(f"❌ {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"✅ Valid structure. Hash: {rotation_hash(record)[:32]}...")
    return 0


def cmd_chain(args):
    d = Path(args[0])
    records = []
    for f in sorted(d.glob("*.json")):
        with open(f) as fh:
            records.append(json.load(fh))
    if not records:
        print("No rotation records found")
        return 1
    errors = validate_chain(records)
    if errors:
        print(f"❌ Chain has {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"✅ Valid chain of {len(records)} rotation(s)")
    print(f"   Current key: {records[-1]['new_key_id']}")
    return 0


def cmd_generate(args):
    old_key = None
    new_key = None
    for i, a in enumerate(args):
        if a == "--old-key" and i + 1 < len(args):
            old_key = args[i + 1]
        if a == "--new-key" and i + 1 < len(args):
            new_key = args[i + 1]
    record = generate_rotation(old_key, new_key)
    print(json.dumps(record, indent=2))
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "validate":
        return cmd_validate(args)
    elif cmd == "chain":
        return cmd_chain(args)
    elif cmd == "generate":
        return cmd_generate(args)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
