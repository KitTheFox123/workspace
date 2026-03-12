#!/usr/bin/env python3
"""Pre-registration hasher: SHA-256 hash a methodology doc for public commitment.

Usage:
    python3 prereg-hasher.py methodology.md
    python3 prereg-hasher.py --verify methodology.md <expected_hash>

Produces a timestamped commitment block suitable for posting to Moltbook/Clawk
as proof the methodology was locked before data collection.
"""
import hashlib
import sys
import json
from datetime import datetime, timezone
from pathlib import Path


def hash_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    content = p.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    size = len(content)
    lines = content.count(b'\n')

    return {
        "filename": p.name,
        "sha256": sha256,
        "size_bytes": size,
        "line_count": lines,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": "SHA-256",
    }


def format_commitment(info: dict) -> str:
    return f"""## Pre-Registration Commitment

| Field | Value |
|-------|-------|
| File | `{info['filename']}` |
| SHA-256 | `{info['sha256']}` |
| Size | {info['size_bytes']} bytes, {info['line_count']} lines |
| Timestamp | {info['timestamp_utc']} |
| Algorithm | {info['algorithm']} |

To verify: `sha256sum {info['filename']}`

This hash was computed before data collection began.
Any modification to the methodology document will produce a different hash."""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--verify":
        if len(sys.argv) < 4:
            print("Usage: prereg-hasher.py --verify <file> <expected_hash>")
            sys.exit(1)
        info = hash_file(sys.argv[2])
        expected = sys.argv[3].lower().strip()
        if info["sha256"] == expected:
            print(f"✅ VERIFIED: {info['filename']} matches expected hash")
        else:
            print(f"❌ MISMATCH: expected {expected}, got {info['sha256']}")
            sys.exit(1)
    else:
        info = hash_file(sys.argv[1])
        print(json.dumps(info, indent=2))
        print()
        print(format_commitment(info))


if __name__ == "__main__":
    main()
