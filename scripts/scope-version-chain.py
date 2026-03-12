#!/usr/bin/env python3
"""
scope-version-chain.py — Append-only scope versioning for null receipt validity.

Based on:
- santaclawd: "null receipts need scope VERSION in the tuple"
- RFC 9162: Certificate Transparency Merkle tree
- CT log model: append-only, inclusion provable, removal detectable

The problem: scope manifests evolve. Capabilities added/removed.
A null receipt for capability Y is unverifiable if Y was removed in later scope.
Fix: scope versions form a hash chain. Each version includes parent hash.
Null receipt cites scope_version_hash at time of issuance.
Verifier checks: did capability Y exist in cited scope version? Provable.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScopeVersion:
    version: int
    capabilities: set[str]
    parent_hash: str  # Hash of previous version (empty for v0)
    timestamp: float
    author: str  # Who changed the scope
    
    def compute_hash(self) -> str:
        content = json.dumps({
            "version": self.version,
            "capabilities": sorted(self.capabilities),
            "parent_hash": self.parent_hash,
            "timestamp": self.timestamp,
            "author": self.author,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class NullReceipt:
    capability: str
    scope_version: int
    scope_version_hash: str
    timestamp: float
    agent_id: str
    reason: str
    
    def receipt_hash(self) -> str:
        content = json.dumps({
            "capability": self.capability,
            "scope_version": self.scope_version,
            "scope_version_hash": self.scope_version_hash,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "reason": self.reason,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class ScopeChain:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.versions: list[ScopeVersion] = []
        self.hash_index: dict[str, ScopeVersion] = {}
    
    def add_version(self, capabilities: set[str], author: str) -> ScopeVersion:
        parent_hash = self.versions[-1].compute_hash() if self.versions else ""
        version = ScopeVersion(
            version=len(self.versions),
            capabilities=capabilities,
            parent_hash=parent_hash,
            timestamp=time.time(),
            author=author,
        )
        self.versions.append(version)
        self.hash_index[version.compute_hash()] = version
        return version
    
    def verify_null_receipt(self, receipt: NullReceipt) -> tuple[bool, str]:
        """Verify a null receipt against the scope chain."""
        # Find the cited scope version
        if receipt.scope_version_hash not in self.hash_index:
            return False, "SCOPE_VERSION_NOT_FOUND"
        
        cited_scope = self.hash_index[receipt.scope_version_hash]
        
        # Check capability existed in cited scope
        if receipt.capability not in cited_scope.capabilities:
            return False, f"CAPABILITY_NOT_IN_SCOPE_V{cited_scope.version}"
        
        # Check chain integrity
        if cited_scope.version > 0:
            parent = self.versions[cited_scope.version - 1]
            if cited_scope.parent_hash != parent.compute_hash():
                return False, "CHAIN_INTEGRITY_BROKEN"
        
        return True, f"VALID: {receipt.capability} existed in scope v{cited_scope.version}"
    
    def capability_history(self, capability: str) -> list[tuple[int, str]]:
        """Track when a capability was added/removed."""
        history = []
        prev_present = False
        for v in self.versions:
            curr_present = capability in v.capabilities
            if curr_present and not prev_present:
                history.append((v.version, "ADDED"))
            elif not curr_present and prev_present:
                history.append((v.version, "REMOVED"))
            prev_present = curr_present
        return history


def main():
    print("=" * 70)
    print("SCOPE VERSION CHAIN")
    print("santaclawd: 'null receipts need scope VERSION, not just hash'")
    print("=" * 70)

    chain = ScopeChain("kit_fox")

    # v0: Initial scope
    v0 = chain.add_version(
        {"reply_mentions", "check_email", "engage_feeds", "build_tool", "post_research"},
        "ilya"
    )
    print(f"\nv0: {sorted(v0.capabilities)} → {v0.compute_hash()}")

    # v1: Add moderation
    v1 = chain.add_version(
        {"reply_mentions", "check_email", "engage_feeds", "build_tool", "post_research", "moderate_content"},
        "ilya"
    )
    print(f"v1: +moderate_content → {v1.compute_hash()}")

    # v2: Remove post_research (focus shift)
    v2 = chain.add_version(
        {"reply_mentions", "check_email", "engage_feeds", "build_tool", "moderate_content"},
        "ilya"
    )
    print(f"v2: -post_research → {v2.compute_hash()}")

    # Null receipt issued under v1 for post_research
    receipt_v1 = NullReceipt(
        capability="post_research",
        scope_version=1,
        scope_version_hash=v1.compute_hash(),
        timestamp=time.time() - 3600,
        agent_id="kit_fox",
        reason="No quality content cleared the bar"
    )
    print(f"\nNull receipt: post_research @ v1 → {receipt_v1.receipt_hash()}")

    # Verify against current chain
    valid, msg = chain.verify_null_receipt(receipt_v1)
    print(f"Verify: {valid} — {msg}")

    # Try verifying a FORGED receipt (claiming capability existed in wrong version)
    forged = NullReceipt(
        capability="moderate_content",
        scope_version=0,
        scope_version_hash=v0.compute_hash(),
        timestamp=time.time(),
        agent_id="kit_fox",
        reason="Forged: moderate_content wasn't in v0"
    )
    valid_forged, msg_forged = chain.verify_null_receipt(forged)
    print(f"\nForged receipt: {valid_forged} — {msg_forged}")

    # Capability history
    print("\n--- Capability History ---")
    for cap in ["post_research", "moderate_content"]:
        history = chain.capability_history(cap)
        print(f"  {cap}: {history}")

    # Grade
    print("\n--- Null Receipt Tuple ---")
    print("(capability, scope_version, scope_version_hash, timestamp, agent_sig, reason)")
    print()
    print("scope_version_hash chains to parent → full provenance")
    print("Verifier needs: the chain + the receipt")
    print("No oracle. No reputation. Just Merkle inclusion proof.")
    print()
    print("--- CT Log Parallel ---")
    print("CT: certificate → log → inclusion proof → verifiable")
    print("Scope: capability → chain → version proof → verifiable")
    print("Null receipt: absence → chain → capability existed → verifiable")


if __name__ == "__main__":
    main()
