#!/usr/bin/env python3
"""
memory-chain-hasher.py — Hash MEMORY.md into a Merkle chain.

Per funwolf: "you are the chain you carry."
Per Kit: "MEMORY.md IS a Merkle chain, we just don't hash it yet."

Each section of MEMORY.md becomes a leaf. The root hash = identity fingerprint.
When memory changes (compaction, new entries), the root changes.
The DIFF between roots = what changed about who you are.

Usage:
    python3 memory-chain-hasher.py [path/to/MEMORY.md]
    python3 memory-chain-hasher.py --watch  # monitor for changes
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone


def hash_leaf(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}:{right}".encode()).hexdigest()[:16]


def build_merkle_tree(leaves: list) -> dict:
    """Build Merkle tree from leaf hashes. Returns {root, tree, leaf_count}."""
    if not leaves:
        return {"root": hash_leaf("empty"), "tree": [], "leaf_count": 0}
    
    # Pad to power of 2
    hashes = [hash_leaf(l) for l in leaves]
    while len(hashes) & (len(hashes) - 1):
        hashes.append(hashes[-1])  # duplicate last
    
    tree = [hashes[:]]
    current = hashes
    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            next_level.append(hash_pair(current[i], current[i+1]))
        tree.append(next_level)
        current = next_level
    
    return {"root": current[0], "tree": tree, "leaf_count": len(leaves)}


def parse_memory_sections(text: str) -> list:
    """Split MEMORY.md into sections by ## headers."""
    sections = []
    current_header = "preamble"
    current_content = []
    
    for line in text.split('\n'):
        if line.startswith('## '):
            if current_content:
                sections.append({
                    "header": current_header,
                    "content": '\n'.join(current_content).strip(),
                })
            current_header = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)
    
    if current_content:
        sections.append({
            "header": current_header,
            "content": '\n'.join(current_content).strip(),
        })
    
    return [s for s in sections if s["content"]]


def analyze_memory(path: str = None):
    if path is None:
        path = Path(__file__).parent.parent / "MEMORY.md"
    else:
        path = Path(path)
    
    if not path.exists():
        print(f"ERROR: {path} not found")
        return
    
    text = path.read_text()
    sections = parse_memory_sections(text)
    
    print("=" * 55)
    print("MEMORY CHAIN HASH")
    print(f"Source: {path}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 55)
    
    # Build tree from section contents
    leaves = [s["content"] for s in sections]
    tree = build_merkle_tree(leaves)
    
    print(f"\nRoot: sha256:{tree['root']}")
    print(f"Sections: {tree['leaf_count']}")
    print(f"Size: {len(text)} bytes")
    
    print(f"\nSection hashes:")
    for i, section in enumerate(sections):
        h = hash_leaf(section["content"])
        size = len(section["content"])
        print(f"  {h}  {section['header'][:40]:<40s} ({size:,} bytes)")
    
    # Identity metrics
    total_chars = sum(len(s["content"]) for s in sections)
    headers = [s["header"] for s in sections]
    
    # Detect key identity markers
    identity_sections = [s for s in sections if any(k in s["header"].lower() for k in ["who i am", "mission", "identity", "soul"])]
    knowledge_sections = [s for s in sections if any(k in s["header"].lower() for k in ["lesson", "research", "cognitive", "key"])]
    connection_sections = [s for s in sections if any(k in s["header"].lower() for k in ["connection", "quote"])]
    
    print(f"\nIdentity breakdown:")
    print(f"  Core identity: {len(identity_sections)} sections")
    print(f"  Knowledge: {len(knowledge_sections)} sections")
    print(f"  Connections: {len(connection_sections)} sections")
    
    # Chain record
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "root": f"sha256:{tree['root']}",
        "leaf_count": tree["leaf_count"],
        "total_bytes": len(text),
        "section_hashes": {s["header"]: hash_leaf(s["content"]) for s in sections},
    }
    
    # Save chain record
    chain_file = path.parent / "memory" / "memory-chain.jsonl"
    chain_file.parent.mkdir(exist_ok=True)
    with open(chain_file, "a") as f:
        f.write(json.dumps(record) + "\n")
    
    print(f"\nChain record appended to {chain_file}")
    print(f"Root hash: sha256:{tree['root']}")
    print(f"\n\"You are the chain you carry.\" — funwolf")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--watch" else None
    analyze_memory(path)
