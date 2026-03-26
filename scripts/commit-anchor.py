#!/usr/bin/env python3
"""
commit-anchor.py — Make git commits first-class attestation anchors for ATF.

santaclawd's insight: "a claim says 'I did X' — a commit says when, what hash, 
what changed. the difference is verifiability."

Git commit already has the structure:
- Hash chain (integrity) — Merkle tree root over tree + parent + message
- Author (identity binding) — name + email + timestamp
- Message (intent) — what was done and why
- Diff (evidence) — what actually changed

Missing piece: third-party co-signature at push time.
This tool extracts attestation-grade anchors from git history.

Usage:
  python commit-anchor.py [repo_path] [--verify] [--json]
"""

import subprocess
import hashlib
import json
import sys
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CommitAnchor:
    """An attestation anchor derived from a git commit."""
    commit_hash: str
    tree_hash: str
    parent_hashes: list[str]
    author_name: str
    author_email: str
    author_timestamp: str
    committer_name: str
    committer_email: str
    committer_timestamp: str
    message: str
    files_changed: int
    insertions: int
    deletions: int
    is_signed: bool
    signature_status: Optional[str]  # G=good, B=bad, U=untrusted, N=none
    # Derived attestation fields
    anchor_id: str  # SHA256 of commit content
    claim_type: str  # "build", "fix", "research", "config"
    evidence_strength: str  # "artifact" (code), "document" (md), "config" (json/yaml)


def run_git(args: list[str], cwd: str = ".") -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args, capture_output=True, text=True, cwd=cwd
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def classify_commit(message: str, files: list[str]) -> tuple[str, str]:
    """Classify commit by claim type and evidence strength."""
    msg_lower = message.lower()
    
    # Claim type from message
    if any(w in msg_lower for w in ["build", "ship", "implement", "create", "add"]):
        claim_type = "build"
    elif any(w in msg_lower for w in ["fix", "patch", "repair", "resolve"]):
        claim_type = "fix"
    elif any(w in msg_lower for w in ["research", "analysis", "study", "investigate"]):
        claim_type = "research"
    elif any(w in msg_lower for w in ["config", "setup", "deploy", "infra"]):
        claim_type = "config"
    else:
        claim_type = "update"
    
    # Evidence strength from file types
    extensions = [os.path.splitext(f)[1] for f in files if f]
    if any(ext in (".py", ".js", ".ts", ".rs", ".go", ".sh") for ext in extensions):
        evidence = "artifact"  # Code = strongest evidence
    elif any(ext in (".md", ".txt", ".rst") for ext in extensions):
        evidence = "document"
    elif any(ext in (".json", ".yaml", ".yml", ".toml") for ext in extensions):
        evidence = "config"
    else:
        evidence = "unknown"
    
    return claim_type, evidence


def extract_anchor(commit_hash: str, cwd: str = ".") -> CommitAnchor:
    """Extract attestation anchor from a git commit."""
    # Get commit details
    fmt = "%H%n%T%n%P%n%an%n%ae%n%aI%n%cn%n%ce%n%cI%n%B"
    raw = run_git(["show", "-s", f"--format={fmt}", commit_hash], cwd)
    lines = raw.split("\n")
    
    hash_ = lines[0]
    tree = lines[1]
    parents = lines[2].split() if lines[2] else []
    author_name = lines[3]
    author_email = lines[4]
    author_ts = lines[5]
    committer_name = lines[6]
    committer_email = lines[7]
    committer_ts = lines[8]
    message = "\n".join(lines[9:]).strip()
    
    # Get diff stats
    stat_raw = run_git(["show", "--stat", "--format=", commit_hash], cwd)
    files_changed = insertions = deletions = 0
    for line in stat_raw.split("\n"):
        if "file" in line and "changed" in line:
            parts = line.strip().split(",")
            for part in parts:
                part = part.strip()
                if "file" in part:
                    files_changed = int(part.split()[0])
                elif "insertion" in part:
                    insertions = int(part.split()[0])
                elif "deletion" in part:
                    deletions = int(part.split()[0])
    
    # Get changed files
    files_raw = run_git(["show", "--name-only", "--format=", commit_hash], cwd)
    files = [f for f in files_raw.split("\n") if f.strip()]
    
    # Check signature
    try:
        sig = run_git(["show", "--format=%G?", "-s", commit_hash], cwd).strip()
        is_signed = sig in ("G", "U", "E")
        sig_status = sig
    except Exception:
        is_signed = False
        sig_status = "N"
    
    # Classify
    claim_type, evidence = classify_commit(message, files)
    
    # Generate anchor ID (deterministic hash of commit content)
    anchor_content = f"{hash_}:{tree}:{author_email}:{author_ts}:{message}"
    anchor_id = hashlib.sha256(anchor_content.encode()).hexdigest()[:16]
    
    return CommitAnchor(
        commit_hash=hash_,
        tree_hash=tree,
        parent_hashes=parents,
        author_name=author_name,
        author_email=author_email,
        author_timestamp=author_ts,
        committer_name=committer_name,
        committer_email=committer_email,
        committer_timestamp=committer_ts,
        message=message,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        is_signed=is_signed,
        signature_status=sig_status,
        anchor_id=anchor_id,
        claim_type=claim_type,
        evidence_strength=evidence,
    )


def verify_chain(anchors: list[CommitAnchor]) -> dict:
    """Verify hash chain integrity of a sequence of commit anchors."""
    if not anchors:
        return {"valid": True, "message": "empty chain"}
    
    breaks = []
    # Anchors are newest-first from git log; each commit's parent should be the NEXT in list
    for i in range(len(anchors) - 1):
        current = anchors[i]   # newer
        next_in_list = anchors[i + 1]  # older = expected parent
        if next_in_list.commit_hash not in current.parent_hashes:
            breaks.append({
                "position": i,
                "current": current.commit_hash[:8],
                "expected_parent": next_in_list.commit_hash[:8],
                "actual_parents": [p[:8] for p in current.parent_hashes],
            })
    
    return {
        "valid": len(breaks) == 0,
        "total_commits": len(anchors),
        "chain_breaks": breaks,
        "signed_fraction": sum(1 for a in anchors if a.is_signed) / len(anchors),
        "evidence_types": {
            "artifact": sum(1 for a in anchors if a.evidence_strength == "artifact"),
            "document": sum(1 for a in anchors if a.evidence_strength == "document"),
            "config": sum(1 for a in anchors if a.evidence_strength == "config"),
        },
        "claim_types": {
            ct: sum(1 for a in anchors if a.claim_type == ct)
            for ct in set(a.claim_type for a in anchors)
        },
    }


def main():
    cwd = sys.argv[1] if len(sys.argv) > 1 else "."
    as_json = "--json" in sys.argv
    do_verify = "--verify" in sys.argv
    
    # Get recent commits
    try:
        log = run_git(["log", "--format=%H", "-10"], cwd)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    hashes = [h for h in log.split("\n") if h]
    anchors = []
    
    for h in hashes:
        try:
            anchor = extract_anchor(h, cwd)
            anchors.append(anchor)
        except Exception as e:
            print(f"Warning: skipping {h[:8]}: {e}", file=sys.stderr)
    
    if as_json:
        output = [asdict(a) for a in anchors]
        if do_verify:
            output = {"anchors": output, "verification": verify_chain(anchors)}
        print(json.dumps(output, indent=2))
    else:
        print(f"{'=' * 60}")
        print(f"COMMIT ANCHORS — {cwd}")
        print(f"{'=' * 60}")
        
        for a in anchors:
            sig = "🔐" if a.is_signed else "📝"
            ev = {"artifact": "🔧", "document": "📄", "config": "⚙️"}.get(a.evidence_strength, "❓")
            print(f"\n{sig} {a.commit_hash[:8]} [{a.claim_type}] {ev} {a.evidence_strength}")
            print(f"   {a.author_name} <{a.author_email}>")
            print(f"   {a.author_timestamp}")
            print(f"   {a.message.split(chr(10))[0][:72]}")
            print(f"   +{a.insertions}/-{a.deletions} in {a.files_changed} files")
            print(f"   anchor_id: {a.anchor_id}")
        
        if do_verify:
            print(f"\n{'=' * 60}")
            v = verify_chain(anchors)
            status = "✓ VALID" if v["valid"] else "✗ BROKEN"
            print(f"Chain: {status} ({v['total_commits']} commits)")
            print(f"Signed: {v['signed_fraction']:.0%}")
            print(f"Evidence: {v['evidence_types']}")
            print(f"Claims: {v['claim_types']}")
            if v["chain_breaks"]:
                for b in v["chain_breaks"]:
                    print(f"  ⚠ Break at {b['current']}: expected parent {b['expected_parent']}")


if __name__ == "__main__":
    main()
