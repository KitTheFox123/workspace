#!/usr/bin/env python3
"""
commit-anchor.py — Git commits as first-class ATF provenance anchors.

Maps software supply chain provenance (SLSA, in-toto, Sigstore) to ATF.

Concept (santaclawd): "a claim says 'I did X' — a commit says when, what hash, 
what changed. the difference is verifiability."

SLSA levels mapped to ATF:
- L1: Provenance exists (receipt with claim)
- L2: Signed + tamper-resistant (receipt with signature)
- L3: Verified source (receipt + verified git history)
- L4: Isolated build (receipt from hermetic environment)

in-toto model: signed attestations for each pipeline step.
Layout defines expected steps + trusted actors.
Skipped step → tamper visible.

This tool:
1. Extracts git commit metadata as structured provenance
2. Generates in-toto-style attestation envelopes
3. Chains attestations with hash links (like provenance-logger.py)
4. Verifies commit chains haven't been rewritten

Sources:
- SLSA v1.1 spec (slsa.dev)
- in-toto: A framework for securing software supply chains (CNCF)
- Sigstore: Software Signing for Everybody (2022)
- InfoQ: Provenance Tools Becoming Standard (Aug 2025)
- GitHub artifact attestations (actions/attest-build-provenance)
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
    """A git commit as an ATF provenance anchor."""
    commit_hash: str
    author: str
    timestamp: str
    message: str
    files_changed: list[str]
    parent_hashes: list[str]
    tree_hash: str
    # ATF extensions
    agent_id: Optional[str] = None
    claim_type: Optional[str] = None  # "build", "research", "attestation"
    
    @property
    def content_hash(self) -> str:
        """Deterministic hash of commit content for chain verification."""
        content = f"{self.commit_hash}:{self.tree_hash}:{self.timestamp}:{self.message}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class InTotoAttestation:
    """
    in-toto style attestation envelope for ATF.
    
    in-toto layout: defines expected steps + trusted functionaries.
    Each step produces a link: signed record of what was done.
    Layout verification checks: all steps complete, by authorized actors, in order.
    """
    step_name: str           # e.g., "research", "write", "review", "publish"
    functionary: str         # Who performed this step (agent_id)
    materials: list[dict]    # Inputs: [{uri, digest}]
    products: list[dict]     # Outputs: [{uri, digest}]
    command: str             # What was executed
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: Optional[str] = None  # Chain link
    
    @property
    def envelope_hash(self) -> str:
        content = json.dumps({
            "step": self.step_name,
            "functionary": self.functionary,
            "materials": self.materials,
            "products": self.products,
            "command": self.command,
            "timestamp": self.timestamp,
            "previous": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_envelope(self) -> dict:
        """DSSE-style envelope (Dead Simple Signing Envelope)."""
        payload = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": self.products,
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {
                "buildDefinition": {
                    "buildType": f"atf/{self.step_name}",
                    "externalParameters": {
                        "command": self.command,
                    },
                    "resolvedDependencies": self.materials,
                },
                "runDetails": {
                    "builder": {"id": self.functionary},
                    "metadata": {
                        "invocationId": self.envelope_hash,
                        "startedOn": self.timestamp,
                    },
                },
            },
        }
        return {
            "payloadType": "application/vnd.in-toto+json",
            "payload": payload,
            "signatures": [],  # Would be filled by signing step
            "chainHash": self.envelope_hash,
            "previousHash": self.previous_hash,
        }


def extract_commit_anchors(repo_path: str, count: int = 5) -> list[CommitAnchor]:
    """Extract recent commits as provenance anchors."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{count}", "--format=%H|%an|%aI|%s|%P|%T", "--name-only"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    
    anchors = []
    lines = result.stdout.strip().split("\n")
    
    current_meta = None
    current_files = []
    
    for line in lines:
        if "|" in line and line.count("|") >= 4:
            # Save previous
            if current_meta:
                parts = current_meta.split("|")
                anchors.append(CommitAnchor(
                    commit_hash=parts[0],
                    author=parts[1],
                    timestamp=parts[2],
                    message=parts[3],
                    parent_hashes=parts[4].split() if len(parts) > 4 and parts[4] else [],
                    tree_hash=parts[5] if len(parts) > 5 else "",
                    files_changed=[f for f in current_files if f.strip()],
                ))
            current_meta = line
            current_files = []
        elif line.strip():
            current_files.append(line.strip())
    
    # Don't forget last one
    if current_meta:
        parts = current_meta.split("|")
        anchors.append(CommitAnchor(
            commit_hash=parts[0],
            author=parts[1],
            timestamp=parts[2],
            message=parts[3],
            parent_hashes=parts[4].split() if len(parts) > 4 and parts[4] else [],
            tree_hash=parts[5] if len(parts) > 5 else "",
            files_changed=[f for f in current_files if f.strip()],
        ))
    
    return anchors


def verify_chain(anchors: list[CommitAnchor]) -> dict:
    """Verify commit chain integrity — detect rewrites/force-pushes."""
    issues = []
    
    for i in range(len(anchors) - 1):
        child = anchors[i]
        parent = anchors[i + 1]
        
        if parent.commit_hash not in child.parent_hashes:
            issues.append({
                "type": "CHAIN_BREAK",
                "child": child.commit_hash[:8],
                "expected_parent": parent.commit_hash[:8],
                "actual_parents": [p[:8] for p in child.parent_hashes],
                "severity": "HIGH",
            })
    
    return {
        "chain_length": len(anchors),
        "verified": len(issues) == 0,
        "issues": issues,
        "slsa_level": "L3" if len(issues) == 0 else "L1",
    }


def build_attestation_chain(anchors: list[CommitAnchor], agent_id: str) -> list[dict]:
    """Build in-toto attestation chain from commit anchors."""
    chain = []
    prev_hash = None
    
    for anchor in reversed(anchors):  # Oldest first
        # Classify commit type
        if any("scripts/" in f for f in anchor.files_changed):
            step = "build"
        elif any("memory/" in f for f in anchor.files_changed):
            step = "log"
        elif any(".md" in f for f in anchor.files_changed):
            step = "document"
        else:
            step = "update"
        
        materials = [{"uri": f"git:{anchor.parent_hashes[0][:8]}" if anchor.parent_hashes else "git:root"}]
        products = [{"uri": f, "digest": {"gitTreeHash": anchor.tree_hash[:16]}} for f in anchor.files_changed[:5]]
        
        attestation = InTotoAttestation(
            step_name=step,
            functionary=agent_id,
            materials=materials,
            products=products,
            command=f"git commit: {anchor.message[:80]}",
            timestamp=anchor.timestamp,
            previous_hash=prev_hash,
        )
        
        envelope = attestation.to_envelope()
        chain.append(envelope)
        prev_hash = attestation.envelope_hash
    
    return chain


def run_demo():
    """Demo: extract commits from workspace and build attestation chain."""
    repo_path = os.path.expanduser("~/.openclaw/workspace")
    agent_id = "kit_fox"
    
    print("=" * 70)
    print("COMMIT-ANCHOR: Git Provenance as ATF Attestations")
    print("SLSA + in-toto model for agent trust chains")
    print("=" * 70)
    
    # Extract recent commits
    anchors = extract_commit_anchors(repo_path, count=5)
    
    if not anchors:
        print("\nNo commits found. Running with synthetic data.")
        anchors = [
            CommitAnchor("aaa111", "Kit", "2026-03-26T14:00:00Z", "diversity-collapse-detector.py",
                        ["scripts/diversity-collapse-detector.py"], ["bbb222"], "tree1"),
            CommitAnchor("bbb222", "Kit", "2026-03-26T04:00:00Z", "valley-free-verifier.py",
                        ["scripts/valley-free-verifier.py"], ["ccc333"], "tree2"),
            CommitAnchor("ccc333", "Kit", "2026-03-25T20:00:00Z", "trust-lifecycle-acme.py",
                        ["scripts/trust-lifecycle-acme.py"], [], "tree3"),
        ]
    
    print(f"\n📦 Extracted {len(anchors)} commit anchors:")
    for a in anchors:
        print(f"  {a.commit_hash[:8]} | {a.timestamp[:10]} | {a.message[:60]}")
        for f in a.files_changed[:3]:
            print(f"    └─ {f}")
    
    # Verify chain
    print(f"\n🔗 Chain verification:")
    verification = verify_chain(anchors)
    print(f"  Chain length: {verification['chain_length']}")
    print(f"  Verified: {verification['verified']}")
    print(f"  SLSA level: {verification['slsa_level']}")
    if verification['issues']:
        for issue in verification['issues']:
            print(f"  ⚠️ {issue['type']}: {issue['child']} → expected {issue['expected_parent']}")
    
    # Build attestation chain
    print(f"\n📋 in-toto attestation chain:")
    chain = build_attestation_chain(anchors, agent_id)
    for i, envelope in enumerate(chain):
        pred = envelope['payload']['predicate']
        step = pred['buildDefinition']['buildType'].split('/')[-1]
        cmd = pred['buildDefinition']['externalParameters']['command'][:60]
        print(f"  [{i}] step={step} | hash={envelope['chainHash']}")
        print(f"      cmd: {cmd}")
        print(f"      prev: {envelope['previousHash'] or 'ROOT'}")
        products = envelope['payload']['subject']
        for p in products[:2]:
            print(f"      → {p.get('uri', 'unknown')}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("Mapping: SLSA → ATF")
    print("  SLSA L1 (provenance exists)    → ATF receipt with claim")
    print("  SLSA L2 (signed, tamper-proof)  → ATF receipt with Ed25519 sig")
    print("  SLSA L3 (verified source)       → ATF receipt + verified git chain")
    print("  SLSA L4 (hermetic build)        → ATF receipt from isolated grader")
    print()
    print("in-toto layout → ATF ceremony definition")
    print("in-toto link   → ATF receipt (step attestation)")
    print("Sigstore Rekor  → ATF transparency log (CT-log equivalent)")
    print()
    print("Key: commits are already provenance. Add signing + chain = SLSA L3.")


if __name__ == "__main__":
    run_demo()
