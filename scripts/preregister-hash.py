#!/usr/bin/env python3
"""
preregister-hash.py — Pre-register a study plan by hashing it.
Produces a signed commitment (SHA-256 + timestamp) that can be
posted publicly as proof the hypothesis was stated before data collection.

Eating our own dog food: scope-commit-at-issuance for research.

Usage:
    python3 preregister-hash.py plan.md          # hash a plan file
    python3 preregister-hash.py --verify plan.md HASH TIMESTAMP  # verify
    python3 preregister-hash.py --inline "hypothesis text"       # hash inline text
"""

import hashlib
import sys
import json
from datetime import datetime, timezone


def hash_content(content: str) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    # Normalize: strip trailing whitespace, ensure single newline at end
    normalized = "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    # Commitment = hash of (content_hash + timestamp) — binds time to content
    commitment = hashlib.sha256(f"{content_hash}:{ts}".encode()).hexdigest()
    return {
        "content_hash": content_hash,
        "timestamp": ts,
        "commitment": commitment,
        "content_bytes": len(normalized.encode()),
        "content_lines": normalized.count("\n"),
    }


def verify(content: str, expected_hash: str, timestamp: str) -> bool:
    normalized = "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    commitment = hashlib.sha256(f"{content_hash}:{timestamp}".encode()).hexdigest()
    return commitment == expected_hash


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--verify":
        if len(sys.argv) != 5:
            print("Usage: preregister-hash.py --verify FILE COMMITMENT TIMESTAMP")
            sys.exit(1)
        with open(sys.argv[2]) as f:
            content = f.read()
        ok = verify(content, sys.argv[3], sys.argv[4])
        print(f"{'✅ VERIFIED' if ok else '❌ MISMATCH'}: commitment {'matches' if ok else 'does not match'} file content at stated time")
        sys.exit(0 if ok else 1)

    if sys.argv[1] == "--inline":
        content = " ".join(sys.argv[2:])
    else:
        with open(sys.argv[1]) as f:
            content = f.read()

    result = hash_content(content)
    print(json.dumps(result, indent=2))
    print(f"\n📋 Post this commitment publicly before collecting data:")
    print(f"   commitment: {result['commitment']}")
    print(f"   timestamp:  {result['timestamp']}")
    print(f"   content:    {result['content_hash']}")
    print(f"   size:       {result['content_bytes']} bytes, {result['content_lines']} lines")


if __name__ == "__main__":
    main()
