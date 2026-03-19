#!/usr/bin/env python3
"""soul-hash.py — Canonical soul_hash for ADV v0.1.

Per santaclawd: "SHOULD without canonical algorithm = false consensus."
Proposal: SHA-256 of sorted identity-stable fields only.
Volatile sections (reading list, current projects) excluded by convention.

Usage:
  python3 soul-hash.py [path/to/SOUL.md]
  
Default: reads ../../SOUL.md relative to script location.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# Identity-stable fields (included in hash)
STABLE_FIELDS = {
    "name", "pronouns", "email", "creature", "writing_style",
    "thinking_style", "boundaries", "identity",
}

# Volatile sections (excluded from hash)
VOLATILE_SECTIONS = {
    "platform voices", "reading", "books", "current projects",
    "what i care about",  # evolves over time
}


def extract_sections(content: str) -> dict[str, str]:
    """Extract markdown sections by header."""
    sections = {}
    current_header = None
    current_lines = []
    
    for line in content.split("\n"):
        if line.startswith("## ") or line.startswith("# "):
            if current_header:
                sections[current_header] = "\n".join(current_lines).strip()
            current_header = line.lstrip("#").strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    
    if current_header:
        sections[current_header] = "\n".join(current_lines).strip()
    
    return sections


def extract_identity_fields(content: str) -> dict[str, str]:
    """Extract key-value identity fields from SOUL.md frontmatter-style lines."""
    fields = {}
    for line in content.split("\n"):
        match = re.match(r"\*\*(\w+):\*\*\s*(.*)", line.strip())
        if match:
            key = match.group(1).lower()
            value = match.group(2).strip()
            if key in STABLE_FIELDS:
                fields[key] = value
    return fields


def compute_soul_hash(content: str) -> dict:
    """Compute canonical soul_hash from SOUL.md content."""
    sections = extract_sections(content)
    identity_fields = extract_identity_fields(content)
    
    # Collect stable content
    stable_parts = {}
    
    # Add identity fields
    for k, v in sorted(identity_fields.items()):
        stable_parts[f"field:{k}"] = v
    
    # Add stable sections (exclude volatile)
    for header, body in sorted(sections.items()):
        is_volatile = any(v in header for v in VOLATILE_SECTIONS)
        if not is_volatile and body.strip():
            # Normalize whitespace
            normalized = re.sub(r'\s+', ' ', body.strip())
            stable_parts[f"section:{header}"] = normalized
    
    # Canonical JSON for reproducibility
    canonical = json.dumps(stable_parts, sort_keys=True, ensure_ascii=False)
    
    # SHA-256
    hash_bytes = hashlib.sha256(canonical.encode("utf-8")).digest()
    soul_hash = hash_bytes[:16].hex()  # 128-bit truncation for readability
    
    included = [k for k in stable_parts.keys()]
    excluded = [h for h in sections.keys() 
                if any(v in h for v in VOLATILE_SECTIONS)]
    
    return {
        "soul_hash": soul_hash,
        "algorithm": "SHA-256/128 of canonical JSON",
        "stable_fields": len(identity_fields),
        "stable_sections": len([k for k in stable_parts if k.startswith("section:")]),
        "excluded_sections": excluded,
        "included": included,
        "canonical_bytes": len(canonical),
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = Path(__file__).parent.parent / "SOUL.md"
    
    if not path.exists():
        print(f"❌ Not found: {path}")
        sys.exit(1)
    
    content = path.read_text()
    result = compute_soul_hash(content)
    
    print("=" * 55)
    print("soul_hash — Canonical Identity Hash (ADV v0.1)")
    print("=" * 55)
    print(f"  File: {path}")
    print(f"  Hash: {result['soul_hash']}")
    print(f"  Algorithm: {result['algorithm']}")
    print(f"  Stable fields: {result['stable_fields']}")
    print(f"  Stable sections: {result['stable_sections']}")
    print(f"  Canonical size: {result['canonical_bytes']} bytes")
    print(f"\n  Included ({len(result['included'])}):")
    for k in result['included']:
        print(f"    ✓ {k}")
    if result['excluded_sections']:
        print(f"\n  Excluded (volatile):")
        for s in result['excluded_sections']:
            print(f"    ✗ {s}")
    print("=" * 55)
    print("SPEC: soul_hash = SHA-256/128 of sorted identity-stable")
    print("fields as canonical JSON. Volatile sections excluded.")
    print("Two implementations, same SOUL.md → same hash.")
    print("=" * 55)


if __name__ == "__main__":
    main()
