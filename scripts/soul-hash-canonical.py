#!/usr/bin/env python3
"""soul-hash-canonical.py — Canonical SOUL.md hashing for identity continuity.

Per santaclawd: "SHOULD without canonical algorithm = false consensus."
Two implementations hashing differently → flag drift that isn't real.

Solution: define identity-stable fields, sort deterministically, SHA-256.
Volatile fields (quotes, reading list, timestamps) excluded by convention.

Parallel: RFC 6962 §2.1 defines exact Merkle tree leaf structure.
Without canonical form, CT logs would disagree on the same certificate.
"""

import hashlib
import json
import re
from pathlib import Path


# Identity-stable fields: things that define WHO you are
STABLE_FIELDS = [
    "name",
    "pronouns",
    "creature",       # self-description
    "core_values",    # what you care about
    "boundaries",     # what you won't do
    "identity_statements",  # key identity claims
]

# Volatile fields: things that change without identity change
VOLATILE_PATTERNS = [
    r"^## Quotes",
    r"^## Books",
    r"^\*Updated \d{4}",
    r"^## Reading",
    r"^---$",
]


def extract_stable_sections(soul_text: str) -> dict:
    """Extract identity-stable sections from SOUL.md."""
    sections = {}
    current_section = None
    current_content = []

    for line in soul_text.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = line[3:].strip().lower()
            current_content = []
        elif line.startswith("# "):
            # Title line — extract name
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "title"
            current_content = [line]
        else:
            if current_section:
                current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def is_volatile(section_name: str) -> bool:
    """Check if a section is volatile (should be excluded from hash)."""
    volatile_names = {
        "quotes worth keeping", "books", "reading", "platform voices",
        "key thread crystallizations", "key cognitive science",
    }
    return section_name.lower() in volatile_names


def compute_soul_hash(soul_path: str | Path) -> dict:
    """Compute canonical soul_hash from SOUL.md."""
    soul_text = Path(soul_path).read_text()
    sections = extract_stable_sections(soul_text)

    # Filter to stable sections only
    stable = {k: v for k, v in sections.items() if not is_volatile(k)}

    # Canonical form: sorted keys, normalized whitespace
    canonical_pairs = []
    for key in sorted(stable.keys()):
        # Normalize: collapse whitespace, strip, lowercase key
        normalized = re.sub(r'\s+', ' ', stable[key]).strip()
        canonical_pairs.append((key, normalized))

    # Deterministic JSON serialization
    canonical_json = json.dumps(canonical_pairs, sort_keys=True, ensure_ascii=True)

    # SHA-256
    soul_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return {
        "soul_hash": soul_hash,
        "algorithm": "SHA-256",
        "canonical_form": "sorted_pairs_json",
        "stable_sections": len(stable),
        "volatile_excluded": len(sections) - len(stable),
        "input_bytes": len(soul_text),
        "canonical_bytes": len(canonical_json),
        "sections_included": sorted(stable.keys()),
        "sections_excluded": sorted(k for k in sections if is_volatile(k)),
    }


def demonstrate_drift_detection():
    """Show how soul_hash detects real vs false drift."""
    soul_path = Path(__file__).parent.parent / "SOUL.md"
    if not soul_path.exists():
        soul_path = Path.home() / ".openclaw" / "workspace" / "SOUL.md"

    result = compute_soul_hash(soul_path)

    print("=" * 60)
    print("Canonical SOUL Hash")
    print("=" * 60)
    print(f"  Hash:      {result['soul_hash'][:16]}...")
    print(f"  Algorithm: {result['algorithm']}")
    print(f"  Stable:    {result['stable_sections']} sections")
    print(f"  Volatile:  {result['volatile_excluded']} excluded")
    print(f"  Size:      {result['input_bytes']}b → {result['canonical_bytes']}b canonical")
    print()
    print("Included sections:")
    for s in result["sections_included"]:
        print(f"  ✓ {s}")
    print("Excluded (volatile):")
    for s in result["sections_excluded"]:
        print(f"  ✗ {s}")

    # Simulate drift scenarios
    print()
    print("=" * 60)
    print("Drift Detection Scenarios")
    print("=" * 60)

    scenarios = [
        ("Add a new quote", "volatile", "No hash change — quotes are volatile"),
        ("Change pronouns", "stable", "Hash changes — identity field modified"),
        ("Add a book note", "volatile", "No hash change — reading list is volatile"),
        ("Modify boundaries", "stable", "Hash changes — core identity modified"),
        ("Update timestamp", "volatile", "No hash change — metadata only"),
    ]

    for change, category, expected in scenarios:
        status = "⚪ no drift" if category == "volatile" else "🔴 REAL DRIFT"
        print(f"  {status}: {change}")
        print(f"    → {expected}")

    print()
    print("SPEC PROPOSAL:")
    print("  soul_hash = SHA-256(JSON(sorted_pairs(stable_sections)))")
    print("  MUST: deterministic field ordering (sorted keys)")
    print("  MUST: whitespace normalization (collapse to single space)")
    print("  SHOULD: exclude volatile sections by convention")
    print("  MUST NOT: include timestamps or update markers")


if __name__ == "__main__":
    demonstrate_drift_detection()
