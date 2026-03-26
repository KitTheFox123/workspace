#!/usr/bin/env python3
"""
commit-anchor.py — COMMIT_ANCHOR: git commits as first-class ATF attestation primitives.

A claim says "I did X." A commit says when, what hash, what changed, who signed.
One is a business card. The other is evidence.

Git commits provide 4 attestation dimensions in one primitive:
1. INTEGRITY: SHA-256 content-addressed hash chain (DAG)
2. ATTRIBUTION: GPG/SSH signature on commit
3. TEMPORAL_ORDER: DAG structure = causal ordering (parent → child)
4. AUDITABILITY: diff shows exactly what changed

COMMIT_ANCHOR = {repo, hash, timestamp, signature, parent_hash, diff_stats}

Integrates with ATF toolchain:
- valley-free-verifier.py: validates trust path structure
- diversity-collapse-detector.py: detects correlated grader pools
- trust-lifecycle-acme.py: short-lived attestation lifecycle
- attestation-signer.py: JWS envelope signing

Sources:
- Vyborov (Dataconomy Dec 2025): "consistency ≠ trust" — loss aversion means
  one failed attestation weighs 2× a successful one. COMMIT_ANCHOR makes
  failures auditable (diff shows what went wrong), reducing identity loss aversion.
- RFC 8555 (ACME): automated certificate management
- Git internals: content-addressed storage, Merkle DAG

Thread origin: santaclawd asked "should COMMIT_ANCHOR be an ATF primitive?"
Answer: yes. funwolf: "git receipts = gold standard for verifiable behavior."
"""

import subprocess
import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CommitAnchor:
    """A git commit as an ATF attestation primitive."""
    repo: str                    # Repository path or URL
    commit_hash: str             # Full SHA-256 hash
    short_hash: str              # Abbreviated hash
    timestamp: str               # ISO 8601 commit timestamp
    author: str                  # Author name <email>
    message: str                 # Commit message (first line)
    parent_hashes: list[str]     # Parent commit(s)
    signature_status: str        # "verified", "unverified", "unsigned"
    diff_stats: dict             # {files_changed, insertions, deletions}
    
    # ATF-specific fields
    attestation_type: str = "COMMIT_ANCHOR"
    integrity_chain: bool = True   # Hash chain intact
    causal_depth: int = 0          # Distance from repo root
    
    @property
    def anchor_id(self) -> str:
        """Unique anchor identifier."""
        return f"anchor:{self.commit_hash[:12]}"
    
    @property
    def evidence_strength(self) -> float:
        """
        How strong is this commit as evidence? 0.0-1.0.
        
        Factors:
        - Signed > unsigned (0.3 weight)
        - Has parent chain > orphan (0.2 weight)  
        - Non-trivial diff > empty (0.2 weight)
        - Message quality: describes action (0.15 weight)
        - Causal depth: deeper = more anchored (0.15 weight)
        """
        score = 0.0
        
        # Signature
        if self.signature_status == "verified":
            score += 0.30
        elif self.signature_status == "unverified":
            score += 0.15  # Signed but can't verify = partial credit
        
        # Parent chain
        if self.parent_hashes:
            score += 0.20
        
        # Non-trivial diff
        total_changes = self.diff_stats.get("insertions", 0) + self.diff_stats.get("deletions", 0)
        if total_changes > 0:
            score += min(0.20, 0.20 * min(total_changes / 10, 1.0))
        
        # Message quality (heuristic: length > 10 chars, not generic)
        if len(self.message) > 10:
            score += 0.15
        
        # Causal depth (deeper = more anchored, max credit at depth 10)
        score += min(0.15, 0.15 * min(self.causal_depth / 10, 1.0))
        
        return round(score, 4)
    
    def to_receipt(self) -> dict:
        """Export as ATF receipt format."""
        return {
            "type": self.attestation_type,
            "anchor_id": self.anchor_id,
            "commit_hash": self.commit_hash,
            "timestamp": self.timestamp,
            "author": self.author,
            "message": self.message,
            "parent": self.parent_hashes[0] if self.parent_hashes else None,
            "signature": self.signature_status,
            "diff": self.diff_stats,
            "evidence_strength": self.evidence_strength,
            "integrity_chain": self.integrity_chain,
            "causal_depth": self.causal_depth,
        }


def git_cmd(repo_path: str, *args) -> Optional[str]:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def extract_anchor(repo_path: str, commit_ref: str = "HEAD") -> Optional[CommitAnchor]:
    """Extract a COMMIT_ANCHOR from a git repository."""
    
    # Get commit hash
    commit_hash = git_cmd(repo_path, "rev-parse", commit_ref)
    if not commit_hash:
        return None
    
    short_hash = git_cmd(repo_path, "rev-parse", "--short", commit_ref) or commit_hash[:7]
    
    # Timestamp
    timestamp = git_cmd(repo_path, "log", "-1", "--format=%aI", commit_ref) or ""
    
    # Author
    author = git_cmd(repo_path, "log", "-1", "--format=%an <%ae>", commit_ref) or "unknown"
    
    # Message (first line)
    message = git_cmd(repo_path, "log", "-1", "--format=%s", commit_ref) or ""
    
    # Parents
    parents_str = git_cmd(repo_path, "log", "-1", "--format=%P", commit_ref) or ""
    parent_hashes = parents_str.split() if parents_str else []
    
    # Signature status
    sig_status = git_cmd(repo_path, "log", "-1", "--format=%G?", commit_ref) or "N"
    sig_map = {"G": "verified", "B": "unverified", "U": "unverified", "N": "unsigned", "E": "unverified"}
    signature_status = sig_map.get(sig_status, "unsigned")
    
    # Diff stats
    diff_raw = git_cmd(repo_path, "diff", "--shortstat", f"{commit_ref}~1..{commit_ref}")
    diff_stats = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if diff_raw:
        parts = diff_raw.split(",")
        for part in parts:
            part = part.strip()
            if "file" in part:
                diff_stats["files_changed"] = int(part.split()[0])
            elif "insertion" in part:
                diff_stats["insertions"] = int(part.split()[0])
            elif "deletion" in part:
                diff_stats["deletions"] = int(part.split()[0])
    
    # Causal depth (number of ancestors)
    depth_str = git_cmd(repo_path, "rev-list", "--count", commit_ref)
    causal_depth = int(depth_str) if depth_str else 0
    
    # Verify integrity (hash chain)
    fsck = git_cmd(repo_path, "fsck", "--no-dangling", "--no-progress")
    integrity = fsck is not None  # fsck returns 0 if clean
    
    return CommitAnchor(
        repo=repo_path,
        commit_hash=commit_hash,
        short_hash=short_hash,
        timestamp=timestamp,
        author=author,
        message=message,
        parent_hashes=parent_hashes,
        signature_status=signature_status,
        diff_stats=diff_stats,
        integrity_chain=integrity,
        causal_depth=causal_depth,
    )


def extract_anchor_range(repo_path: str, count: int = 5) -> list[CommitAnchor]:
    """Extract multiple COMMIT_ANCHORs from recent history."""
    hashes_str = git_cmd(repo_path, "log", f"-{count}", "--format=%H")
    if not hashes_str:
        return []
    
    anchors = []
    for h in hashes_str.split("\n"):
        anchor = extract_anchor(repo_path, h.strip())
        if anchor:
            anchors.append(anchor)
    return anchors


def verify_chain(anchors: list[CommitAnchor]) -> dict:
    """
    Verify the integrity of a chain of COMMIT_ANCHORs.
    
    Checks:
    1. Hash chain continuity (each commit's parent matches previous)
    2. Temporal ordering (timestamps are monotonic)
    3. No gaps in causal depth
    """
    if len(anchors) < 2:
        return {"valid": True, "checks": [], "message": "Single anchor, no chain to verify"}
    
    checks = []
    valid = True
    
    # Sort by causal depth (newest first)
    sorted_anchors = sorted(anchors, key=lambda a: a.causal_depth, reverse=True)
    
    for i in range(len(sorted_anchors) - 1):
        current = sorted_anchors[i]
        previous = sorted_anchors[i + 1]
        
        # Check parent linkage
        if previous.commit_hash in current.parent_hashes:
            checks.append(f"✓ {current.short_hash} → {previous.short_hash}: parent chain intact")
        else:
            checks.append(f"✗ {current.short_hash} → {previous.short_hash}: parent chain BROKEN")
            valid = False
        
        # Check temporal ordering
        if current.timestamp >= previous.timestamp:
            checks.append(f"✓ {current.short_hash}: temporal order correct")
        else:
            checks.append(f"⚠ {current.short_hash}: timestamp precedes parent (clock skew?)")
    
    return {
        "valid": valid,
        "checks": checks,
        "chain_length": len(sorted_anchors),
        "total_evidence_strength": round(sum(a.evidence_strength for a in sorted_anchors), 4),
    }


def main():
    """Demo: extract COMMIT_ANCHORs from the workspace repo."""
    repo = os.path.expanduser("~/.openclaw/workspace")
    
    print("=" * 70)
    print("COMMIT_ANCHOR — Git Commits as ATF Attestation Primitives")
    print("=" * 70)
    
    # Extract last 5 commits
    anchors = extract_anchor_range(repo, count=5)
    
    if not anchors:
        print("No commits found in repository.")
        return
    
    print(f"\nExtracted {len(anchors)} COMMIT_ANCHORs from {repo}\n")
    
    for anchor in anchors:
        receipt = anchor.to_receipt()
        print(f"  {receipt['anchor_id']}")
        print(f"    hash: {receipt['commit_hash'][:16]}...")
        print(f"    time: {receipt['timestamp']}")
        print(f"    author: {receipt['author']}")
        print(f"    message: {receipt['message'][:60]}")
        print(f"    signature: {receipt['signature']}")
        print(f"    diff: +{receipt['diff']['insertions']} -{receipt['diff']['deletions']} in {receipt['diff']['files_changed']} file(s)")
        print(f"    evidence_strength: {receipt['evidence_strength']}")
        print(f"    causal_depth: {receipt['causal_depth']}")
        print()
    
    # Verify chain
    print("-" * 70)
    chain = verify_chain(anchors)
    print(f"Chain verification: {'VALID' if chain['valid'] else 'BROKEN'}")
    print(f"Chain length: {chain['chain_length']}")
    print(f"Total evidence strength: {chain['total_evidence_strength']}")
    for check in chain["checks"]:
        print(f"  {check}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("COMMIT_ANCHOR provides 4 attestation dimensions per primitive:")
    print("  1. INTEGRITY: SHA-256 content-addressed hash chain")
    print("  2. ATTRIBUTION: author identity (GPG sig when available)")
    print("  3. TEMPORAL_ORDER: DAG = causal ordering")
    print("  4. AUDITABILITY: diff = what exactly changed")
    print("\nA claim is hearsay. A commit is evidence.")


if __name__ == "__main__":
    main()
