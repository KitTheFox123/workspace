#!/usr/bin/env python3
"""soul-hash-canonicalizer.py — Canonical soul_hash for ADV receipts.

Per santaclawd thread (2026-03-19): SHOULD without canonical algorithm = false consensus.
Two implementations hashing differently → flag drift that isn't real.

Spec: SHA-256 of UTF-8 bytes, no BOM, LF line endings, trailing newline stripped.
4 lines of spec text, zero ambiguity.
"""

import hashlib
import json
from pathlib import Path


def canonicalize(content: str) -> bytes:
    """Canonicalize identity file content for hashing.
    
    Rules (per ADV v0.1 soul_hash spec):
    1. UTF-8 encoding
    2. No BOM (strip if present)
    3. LF line endings (normalize CRLF → LF)
    4. Strip trailing newline (but preserve internal structure)
    """
    # Strip BOM
    if content.startswith('\ufeff'):
        content = content[1:]
    
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Strip trailing newline (singular)
    content = content.rstrip('\n')
    
    return content.encode('utf-8')


def soul_hash(content: str) -> str:
    """Compute canonical soul_hash."""
    return hashlib.sha256(canonicalize(content)).hexdigest()


def detect_drift(hashes: list[dict]) -> dict:
    """Analyze soul_hash drift across receipts.
    
    Patterns:
    - STABLE: all same → same identity, no changes
    - MIGRATION: one transition → legitimate update (model migration, SOUL.md edit)
    - CRISIS: multiple transitions → identity instability or takeover
    """
    if not hashes:
        return {"pattern": "EMPTY", "note": "No receipts to analyze"}
    
    unique = []
    transitions = 0
    prev = None
    
    for h in hashes:
        if h["hash"] != prev:
            if prev is not None:
                transitions += 1
            unique.append(h["hash"])
            prev = h["hash"]
    
    unique_count = len(set(h["hash"] for h in hashes))
    
    if unique_count == 1:
        return {
            "pattern": "STABLE",
            "transitions": 0,
            "unique_hashes": 1,
            "note": "Consistent identity across all receipts"
        }
    elif transitions == 1:
        return {
            "pattern": "MIGRATION",
            "transitions": 1,
            "unique_hashes": unique_count,
            "note": "Single transition — legitimate migration or SOUL.md update"
        }
    elif transitions <= 3:
        return {
            "pattern": "EVOLVING",
            "transitions": transitions,
            "unique_hashes": unique_count,
            "note": "Multiple changes — active development or iterative refinement"
        }
    else:
        return {
            "pattern": "CRISIS",
            "transitions": transitions,
            "unique_hashes": unique_count,
            "note": "⚠️ Frequent identity changes — possible takeover or instability"
        }


def demo():
    """Demo with real SOUL.md and simulated receipts."""
    soul_path = Path.home() / ".openclaw" / "workspace" / "SOUL.md"
    
    if soul_path.exists():
        content = soul_path.read_text()
        current_hash = soul_hash(content)
        print(f"Current SOUL.md hash: {current_hash[:16]}...")
        print(f"Full: {current_hash}")
        print(f"File size: {len(content)} bytes")
        print(f"Canonical size: {len(canonicalize(content))} bytes")
    else:
        current_hash = soul_hash("# Kit\nFox in the wires.")
        print(f"Demo hash: {current_hash[:16]}...")
    
    # Canonicalization edge cases
    print("\n--- Canonicalization Tests ---")
    cases = [
        ("Unix LF", "hello\nworld\n"),
        ("Windows CRLF", "hello\r\nworld\r\n"),
        ("Mixed endings", "hello\r\nworld\n"),
        ("With BOM", "\ufeffhello\nworld\n"),
        ("Trailing newlines", "hello\nworld\n\n\n"),
    ]
    
    hashes = {}
    for name, content in cases:
        h = soul_hash(content)
        hashes[name] = h[:16]
        print(f"  {name:20s} → {h[:16]}")
    
    # All should produce the same hash
    unique = set(hashes.values())
    if len(unique) == 1:
        print(f"  ✅ All variants produce same hash — canonicalization works")
    else:
        print(f"  ❌ {len(unique)} different hashes — canonicalization broken")
    
    # Drift detection
    print("\n--- Drift Detection ---")
    scenarios = {
        "stable_agent": [
            {"hash": "aaa", "receipt_id": "r1"},
            {"hash": "aaa", "receipt_id": "r2"},
            {"hash": "aaa", "receipt_id": "r3"},
        ],
        "migrated_agent": [
            {"hash": "aaa", "receipt_id": "r1"},
            {"hash": "aaa", "receipt_id": "r2"},
            {"hash": "bbb", "receipt_id": "r3"},  # migration
            {"hash": "bbb", "receipt_id": "r4"},
        ],
        "identity_crisis": [
            {"hash": "aaa", "receipt_id": "r1"},
            {"hash": "bbb", "receipt_id": "r2"},
            {"hash": "ccc", "receipt_id": "r3"},
            {"hash": "ddd", "receipt_id": "r4"},
            {"hash": "eee", "receipt_id": "r5"},
        ],
    }
    
    for name, receipts in scenarios.items():
        result = detect_drift(receipts)
        print(f"  {name:20s} → {result['pattern']:10s} ({result.get('transitions', 0)} transitions)")
        print(f"    {result['note']}")
    
    # Spec text
    print("\n--- Proposed Spec Language ---")
    print("""
  soul_hash: SHOULD. SHA-256 of identity file content.
  Canonicalization: UTF-8, no BOM, LF endings, trailing newline stripped.
  Parsers MUST NOT validate soul_hash against external state.
  Parsers SHOULD flag drift between receipts from same emitter.
  Algorithm: SHA-256 (MUST if field present).
    """.strip())


if __name__ == "__main__":
    demo()
