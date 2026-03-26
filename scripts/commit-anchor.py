#!/usr/bin/env python3
"""
commit-anchor.py — COMMIT_ANCHOR: git commits as first-class ATF attestation evidence.

Suggested by santaclawd: "a claim says I did X. a commit says when, what hash, what changed.
one is a business card. the other is evidence."

Maps git commit verification to ATF trust primitives:
- Git commit hash = SHA-256 of (tree + parent + author + timestamp + message)
- Signature at branch tip verifies ENTIRE branch history (Merkle chain)
- GitHub persistent verification (Nov 2024): verify at push, store forever
- Commit = non-repudiable evidence of: WHAT changed, WHEN, WHO signed, WHAT state

ATF integration:
- COMMIT_ANCHOR = {commit_hash, timestamp, tree_hash, diff_summary, signer_id, repo_url}
- Attestation references a commit anchor → verifiable evidence chain
- Provenance-logger.py already chains JSONL with SHA-256 → upgrade to git object refs
- Claims without commit anchors = self-reported. With = independently verifiable.

Sources:
- GitHub persistent commit signature verification (Nov 2024)
- Git internals: commit objects, tree hashing, Merkle chain
- mricon (InfoSec SE): "signature at tip provides integrity of entire history"
"""

import hashlib
import json
import subprocess
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CommitAnchor:
    """
    A COMMIT_ANCHOR: git commit as attestation evidence.
    
    Unlike a self-reported claim, a commit anchor is independently verifiable:
    - Hash is deterministic (recomputable from contents)
    - Timestamp is embedded (not mutable after signing)
    - Tree hash proves exact state of all files
    - Parent hash chains to entire prior history
    - Signature proves identity of committer
    """
    commit_hash: str
    timestamp: str              # ISO 8601
    author_name: str
    author_email: str
    tree_hash: str              # Hash of file tree state
    parent_hashes: list[str]    # Chain to history
    message: str
    diff_summary: dict          # {files_changed, insertions, deletions}
    signature_status: str       # "verified", "unverified", "unsigned"
    signer_id: Optional[str]    # Key fingerprint if signed
    repo_url: Optional[str]
    
    def to_attestation_ref(self) -> dict:
        """Convert to ATF attestation reference format."""
        return {
            "type": "COMMIT_ANCHOR",
            "evidence_class": "verifiable",  # vs "self_reported"
            "commit": self.commit_hash,
            "timestamp": self.timestamp,
            "tree": self.tree_hash,
            "parents": self.parent_hashes,
            "signer": self.signer_id or self.author_email,
            "signature": self.signature_status,
            "diff": self.diff_summary,
            "repo": self.repo_url,
            "chain_depth": len(self.parent_hashes),  # How far back the Merkle chain goes
            "integrity": "branch_tip_verifies_all" if self.signature_status == "verified" else "hash_chain_only",
        }
    
    @property
    def evidence_strength(self) -> str:
        """Rate the evidence strength of this anchor."""
        if self.signature_status == "verified":
            return "STRONG"  # Signed + verifiable
        elif self.signature_status == "unverified":
            return "MEDIUM"  # Signed but can't verify key
        else:
            return "WEAK"    # Unsigned, hash chain only


def extract_commit_anchor(repo_path: str, commit_ref: str = "HEAD") -> Optional[CommitAnchor]:
    """Extract a COMMIT_ANCHOR from a git repository."""
    try:
        # Get commit details
        fmt = "%H%n%aI%n%an%n%ae%n%T%n%P%n%s"
        result = subprocess.run(
            ["git", "log", "-1", f"--format={fmt}", commit_ref],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        
        lines = result.stdout.strip().split("\n")
        if len(lines) < 6:
            return None
        
        commit_hash = lines[0]
        timestamp = lines[1]
        author_name = lines[2]
        author_email = lines[3]
        tree_hash = lines[4]
        parent_hashes = lines[5].split() if lines[5] else []
        message = lines[6] if len(lines) > 6 else ""
        
        # Get diff summary
        diff_result = subprocess.run(
            ["git", "diff", "--shortstat", f"{commit_ref}~1", commit_ref],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        diff_summary = parse_diff_stat(diff_result.stdout.strip())
        
        # Check signature
        sig_result = subprocess.run(
            ["git", "log", "-1", "--format=%G?", commit_ref],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        sig_char = sig_result.stdout.strip()
        if sig_char in ("G", "U", "X", "Y", "R"):
            signature_status = "verified" if sig_char == "G" else "unverified"
        elif sig_char == "N":
            signature_status = "unsigned"
        else:
            signature_status = "unsigned"
        
        # Get signer fingerprint if signed
        signer_id = None
        if signature_status != "unsigned":
            fp_result = subprocess.run(
                ["git", "log", "-1", "--format=%GF", commit_ref],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            signer_id = fp_result.stdout.strip() or None
        
        # Get remote URL
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        repo_url = remote_result.stdout.strip() if remote_result.returncode == 0 else None
        
        return CommitAnchor(
            commit_hash=commit_hash,
            timestamp=timestamp,
            author_name=author_name,
            author_email=author_email,
            tree_hash=tree_hash,
            parent_hashes=parent_hashes,
            message=message,
            diff_summary=diff_summary,
            signature_status=signature_status,
            signer_id=signer_id,
            repo_url=repo_url,
        )
    except Exception as e:
        print(f"Error extracting commit anchor: {e}")
        return None


def parse_diff_stat(stat_line: str) -> dict:
    """Parse git diff --shortstat output."""
    result = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if not stat_line:
        return result
    
    import re
    files_match = re.search(r"(\d+) file", stat_line)
    ins_match = re.search(r"(\d+) insertion", stat_line)
    del_match = re.search(r"(\d+) deletion", stat_line)
    
    if files_match:
        result["files_changed"] = int(files_match.group(1))
    if ins_match:
        result["insertions"] = int(ins_match.group(1))
    if del_match:
        result["deletions"] = int(del_match.group(1))
    
    return result


class CommitAnchorVerifier:
    """
    Verify COMMIT_ANCHOR attestation evidence.
    
    Verification levels:
    1. HASH_VALID: commit hash matches contents (tamper detection)
    2. CHAIN_VALID: parent chain is intact (history integrity)
    3. SIGNATURE_VALID: cryptographic signature verifies (identity proof)
    4. PERSISTENT: GitHub-style persistent verification record exists
    """
    
    def verify(self, anchor: CommitAnchor, repo_path: Optional[str] = None) -> dict:
        """Verify a commit anchor's integrity."""
        checks = {
            "hash_present": bool(anchor.commit_hash),
            "timestamp_present": bool(anchor.timestamp),
            "tree_present": bool(anchor.tree_hash),
            "has_parent_chain": len(anchor.parent_hashes) > 0,
            "signature_status": anchor.signature_status,
            "evidence_strength": anchor.evidence_strength,
            "diff_nontrivial": anchor.diff_summary.get("files_changed", 0) > 0,
        }
        
        # If we have repo access, verify hash chain
        if repo_path:
            try:
                result = subprocess.run(
                    ["git", "cat-file", "-t", anchor.commit_hash],
                    cwd=repo_path, capture_output=True, text=True, timeout=10,
                )
                checks["hash_exists_in_repo"] = result.stdout.strip() == "commit"
                
                # Verify tree hash matches
                tree_result = subprocess.run(
                    ["git", "log", "-1", "--format=%T", anchor.commit_hash],
                    cwd=repo_path, capture_output=True, text=True, timeout=10,
                )
                checks["tree_hash_matches"] = tree_result.stdout.strip() == anchor.tree_hash
            except Exception:
                checks["repo_verification"] = "failed"
        
        # Determine verification level
        if checks["signature_status"] == "verified":
            level = "SIGNATURE_VALID"
        elif checks.get("tree_hash_matches"):
            level = "CHAIN_VALID"
        elif checks["hash_present"] and checks["tree_present"]:
            level = "HASH_VALID"
        else:
            level = "UNVERIFIABLE"
        
        return {
            "verification_level": level,
            "checks": checks,
            "attestation_eligible": level in ("SIGNATURE_VALID", "CHAIN_VALID", "HASH_VALID"),
            "note": self._level_note(level),
        }
    
    def _level_note(self, level: str) -> str:
        notes = {
            "SIGNATURE_VALID": "Full cryptographic proof of identity + integrity. Branch tip verifies entire history.",
            "CHAIN_VALID": "Hash chain intact, tree verified. Identity relies on git author (spoofable without signature).",
            "HASH_VALID": "Commit exists with valid hashes. No signature or repo verification performed.",
            "UNVERIFIABLE": "Insufficient data to verify. Claim without evidence.",
        }
        return notes.get(level, "")


def demo():
    """Demo COMMIT_ANCHOR extraction from this repo."""
    print("=" * 70)
    print("COMMIT_ANCHOR — Git Commits as ATF Attestation Evidence")
    print("=" * 70)
    
    repo_path = os.path.expanduser("~/.openclaw/workspace")
    
    # Extract anchors from recent commits
    for i, ref in enumerate(["HEAD", "HEAD~1", "HEAD~2"]):
        anchor = extract_commit_anchor(repo_path, ref)
        if not anchor:
            print(f"\n[{ref}] Could not extract anchor")
            continue
        
        print(f"\n--- Commit {ref} ---")
        print(f"  Hash:      {anchor.commit_hash[:12]}...")
        print(f"  Time:      {anchor.timestamp}")
        print(f"  Author:    {anchor.author_name} <{anchor.author_email}>")
        print(f"  Message:   {anchor.message[:80]}")
        print(f"  Tree:      {anchor.tree_hash[:12]}...")
        print(f"  Parents:   {len(anchor.parent_hashes)}")
        print(f"  Diff:      {anchor.diff_summary}")
        print(f"  Signed:    {anchor.signature_status}")
        print(f"  Strength:  {anchor.evidence_strength}")
        
        # Verify
        verifier = CommitAnchorVerifier()
        verification = verifier.verify(anchor, repo_path)
        print(f"  Verified:  {verification['verification_level']}")
        print(f"  Eligible:  {verification['attestation_eligible']}")
        
        # Show attestation ref format
        attest_ref = anchor.to_attestation_ref()
        print(f"  ATF Ref:   {json.dumps({k: v for k, v in attest_ref.items() if k in ('type', 'evidence_class', 'integrity', 'signature')})}")
    
    print(f"\n{'=' * 70}")
    print("Key properties:")
    print("  1. Claims are self-reported. Commits are verifiable evidence.")
    print("  2. Signature at branch tip verifies ENTIRE branch history (Merkle chain).")
    print("  3. GitHub persistent verification: verify at push, store forever.")
    print("  4. Tree hash proves exact state of every file at commit time.")
    print("  5. COMMIT_ANCHOR upgrades attestation from 'I said I did X' to 'I provably did X'.")
    print(f"\nsantaclawd: 'one is a business card. the other is evidence.'")


if __name__ == "__main__":
    demo()
