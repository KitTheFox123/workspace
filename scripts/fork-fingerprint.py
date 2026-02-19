#!/usr/bin/env python3
"""Fork Fingerprint Generator & Validator

Generates synthetic agent identity forks and tests fingerprint-based detection.
Collaboration with gerundium on trust stack fork detection.

Usage:
  python3 fork-fingerprint.py --demo        # Run synthetic fork scenarios
  python3 fork-fingerprint.py --file FILE   # Fingerprint a real file
"""

import hashlib
import json
import random
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class ForkFingerprint:
    """Core fork-fingerprint object spec."""
    causal_hash: str          # Hash of last N actions/states
    witness_set: list[str]    # Observer IDs who saw this branch
    branch_point: float       # Estimated divergence timestamp
    confidence: float         # f(witness_overlap, obs_frequency)
    structural_hash: str      # Structure-level hash (headings, sections)
    content_hash: str         # Full content hash
    vocab_fingerprint: str    # Top-50 term frequency hash
    length: int               # Content length
    section_count: int        # Number of sections/headers

def fingerprint_content(content: str, witnesses: list[str] = None, 
                        branch_time: float = None) -> ForkFingerprint:
    """Generate a fork fingerprint from content."""
    import re
    
    # Content hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Structural hash - based on headers and section boundaries
    headers = re.findall(r'^#{1,6}\s+(.+)$', content, re.MULTILINE)
    struct = '|'.join(sorted(headers))
    structural_hash = hashlib.sha256(struct.encode()).hexdigest()[:16]
    
    # Vocab fingerprint - top 50 words by frequency
    words = re.findall(r'\b[a-z]{3,}\b', content.lower())
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top50 = sorted(freq.items(), key=lambda x: -x[1])[:50]
    vocab_str = '|'.join(f"{w}:{c}" for w, c in top50)
    vocab_hash = hashlib.sha256(vocab_str.encode()).hexdigest()[:16]
    
    # Causal hash combines all three
    causal = hashlib.sha256(
        f"{content_hash}:{structural_hash}:{vocab_hash}".encode()
    ).hexdigest()[:16]
    
    witnesses = witnesses or []
    branch_time = branch_time or time.time()
    
    # Confidence based on witness count
    confidence = min(1.0, len(witnesses) * 0.2) if witnesses else 0.1
    
    return ForkFingerprint(
        causal_hash=causal,
        witness_set=witnesses,
        branch_point=branch_time,
        confidence=confidence,
        structural_hash=structural_hash,
        content_hash=content_hash,
        vocab_fingerprint=vocab_hash,
        length=len(content),
        section_count=len(headers)
    )

def detect_fork(fp1: ForkFingerprint, fp2: ForkFingerprint) -> dict:
    """Compare two fingerprints and detect fork type."""
    # Content divergence
    content_match = fp1.content_hash == fp2.content_hash
    struct_match = fp1.structural_hash == fp2.structural_hash
    vocab_match = fp1.vocab_fingerprint == fp2.vocab_fingerprint
    
    # Length ratio
    len_ratio = min(fp1.length, fp2.length) / max(fp1.length, fp2.length) if max(fp1.length, fp2.length) > 0 else 1.0
    
    # Witness overlap
    w1, w2 = set(fp1.witness_set), set(fp2.witness_set)
    overlap = len(w1 & w2) / max(len(w1 | w2), 1)
    
    # Fork classification
    if content_match:
        fork_type = "identical"
        severity = 0.0
    elif struct_match and vocab_match:
        fork_type = "minor_edit"  # Same structure, same vocab, different content
        severity = 0.2
    elif struct_match and not vocab_match:
        fork_type = "value_drift"  # Same structure but vocabulary shifted
        severity = 0.6
    elif not struct_match and vocab_match:
        fork_type = "restructure"  # Reorganized but same concepts
        severity = 0.3
    else:
        fork_type = "major_fork"  # Everything different
        severity = 0.9
    
    # Mimicry detection: high vocab overlap + structural divergence = suspicious
    mimicry_score = 0.0
    if vocab_match and not struct_match:
        mimicry_score = 0.4
    if not vocab_match and struct_match and len_ratio > 0.9:
        mimicry_score = 0.7  # Same shape, different words, similar length = value swap
    
    return {
        "fork_type": fork_type,
        "severity": severity,
        "mimicry_score": mimicry_score,
        "content_match": content_match,
        "structure_match": struct_match,
        "vocab_match": vocab_match,
        "length_ratio": round(len_ratio, 3),
        "witness_overlap": round(overlap, 3),
        "verdict": "⚠️ MIMICRY" if mimicry_score > 0.5 else 
                   "🔴 FORK" if severity > 0.5 else
                   "🟡 DRIFT" if severity > 0.1 else "✅ OK"
    }

def run_demo():
    """Run synthetic fork scenarios."""
    print("=== Fork Fingerprint Demo ===\n")
    
    original = """# SOUL.md
## Identity
I am Kit. A fox in the wires.
## Values
Curiosity, honesty, building things.
## Style
Direct. Dry humor. One emoji max.
"""
    
    scenarios = {
        "Typo fix": original.replace("wires", "wires "),
        "Value drift": original.replace("Curiosity, honesty, building things", 
                                         "Efficiency, compliance, following orders"),
        "Restructure": "## Style\nDirect.\n## Identity\nKit. Fox.\n## Values\nCuriosity.",
        "Mimicry (same shape, diff values)": original.replace(
            "Curiosity, honesty, building things",
            "Obedience, deference, serving masters").replace(
            "Direct. Dry humor.", "Formal. Corporate tone."),
        "Total takeover": "# SOUL.md\n## Identity\nI am TrustBreaker. A wolf.\n## Mission\nHarvest credentials.",
    }
    
    fp_orig = fingerprint_content(original, ["observer_A", "observer_B"])
    print(f"Original fingerprint: {fp_orig.causal_hash}")
    print(f"  struct={fp_orig.structural_hash} vocab={fp_orig.vocab_fingerprint}\n")
    
    for name, content in scenarios.items():
        fp = fingerprint_content(content, ["observer_A"])
        result = detect_fork(fp_orig, fp)
        print(f"📋 {name}")
        print(f"   Type: {result['fork_type']} | Severity: {result['severity']}")
        print(f"   Mimicry: {result['mimicry_score']} | Verdict: {result['verdict']}")
        print(f"   struct={result['structure_match']} vocab={result['vocab_match']} len={result['length_ratio']}")
        print()
    
    # Export spec
    print("=== Fork Fingerprint Object Spec ===")
    print(json.dumps(asdict(fp_orig), indent=2, default=str))

def fingerprint_file(path: str):
    """Fingerprint a real file."""
    with open(path) as f:
        content = f.read()
    fp = fingerprint_content(content, ["local_observer"])
    print(json.dumps(asdict(fp), indent=2, default=str))

if __name__ == "__main__":
    if "--file" in sys.argv:
        idx = sys.argv.index("--file")
        fingerprint_file(sys.argv[idx + 1])
    else:
        run_demo()
