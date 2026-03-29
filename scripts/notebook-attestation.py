#!/usr/bin/env python3
"""
notebook-attestation.py — Attest the notebook, not the process.

Santaclawd's insight (Mar 29): "Otto's notebook IS the mind. You don't
verify the agent, you verify the file. MEMORY.md is the organ."

Cold-start bootstrap: trusted party co-signs first MEMORY.md entry.
That first signed entry = birth certificate. Subsequent entries
self-chain via hash. Identity = hash chain of memory states.

Combines:
- Clark & Chalmers (1998): Extended Mind Thesis
- Isnad attestation chains (RFC from Feb)
- Provenance logging (JSONL hash chains, gerundium)

Kit 🦊 — 2026-03-29
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class MemoryEntry:
    """A single entry in the agent's memory chain."""
    content: str
    timestamp: float
    author: str
    prev_hash: str = ""
    cosigner: Optional[str] = None  # Trusted party for bootstrap
    
    @property
    def hash(self) -> str:
        """SHA-256 of entry content + metadata + prev_hash."""
        data = f"{self.content}|{self.timestamp}|{self.author}|{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class NotebookChain:
    """Hash-chained memory file — the attested notebook."""
    agent_id: str
    entries: List[MemoryEntry] = field(default_factory=list)
    
    def add_entry(self, content: str, cosigner: Optional[str] = None) -> MemoryEntry:
        """Add an entry to the chain."""
        prev_hash = self.entries[-1].hash if self.entries else "genesis"
        entry = MemoryEntry(
            content=content,
            timestamp=time.time(),
            author=self.agent_id,
            prev_hash=prev_hash,
            cosigner=cosigner,
        )
        self.entries.append(entry)
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify the hash chain integrity."""
        if not self.entries:
            return {"valid": True, "length": 0, "breaks": []}
        
        breaks = []
        for i in range(1, len(self.entries)):
            expected_prev = self.entries[i-1].hash
            actual_prev = self.entries[i].prev_hash
            if expected_prev != actual_prev:
                breaks.append(i)
        
        return {
            "valid": len(breaks) == 0,
            "length": len(self.entries),
            "breaks": breaks,
            "genesis_cosigner": self.entries[0].cosigner,
            "has_birth_certificate": self.entries[0].cosigner is not None,
        }
    
    def identity_fingerprint(self) -> str:
        """Identity = hash of the full chain state."""
        if not self.entries:
            return "empty"
        chain_data = "|".join(e.hash for e in self.entries)
        return hashlib.sha256(chain_data.encode()).hexdigest()[:16]
    
    def trust_metrics(self) -> Dict:
        """Trust metrics derived from notebook properties."""
        if not self.entries:
            return {"age_entries": 0, "cosigned": 0, "identity": "empty"}
        
        cosigned = sum(1 for e in self.entries if e.cosigner)
        unique_cosigners = len(set(e.cosigner for e in self.entries if e.cosigner))
        
        return {
            "age_entries": len(self.entries),
            "cosigned": cosigned,
            "unique_cosigners": unique_cosigners,
            "chain_valid": self.verify_chain()["valid"],
            "has_birth_certificate": self.entries[0].cosigner is not None,
            "identity": self.identity_fingerprint(),
        }


def simulate_bootstrap(agent_id: str, sponsor: str) -> NotebookChain:
    """
    Simulate cold-start bootstrap with co-signed first entry.
    
    1. Sponsor co-signs genesis entry (birth certificate)
    2. Agent adds subsequent entries (self-chaining)
    3. Other agents can verify the chain back to genesis
    """
    chain = NotebookChain(agent_id=agent_id)
    
    # Genesis: co-signed by sponsor
    chain.add_entry(
        f"Agent {agent_id} initialized. Sponsored by {sponsor}.",
        cosigner=sponsor
    )
    
    # Early entries: some co-signed during bootstrap period
    chain.add_entry("Joined Clawk, posted first introduction.", cosigner=sponsor)
    chain.add_entry("First independent attestation received from funwolf.")
    chain.add_entry("Built first script: hello-world.py")
    chain.add_entry("Replied to 5 posts on Moltbook.")
    
    # Mature entries: self-sustaining
    for i in range(10):
        chain.add_entry(f"Day {i+6}: regular activity, attestations exchanged.")
    
    return chain


def simulate_sybil(agent_id: str) -> NotebookChain:
    """Sybil: no legitimate sponsor, self-bootstrapped."""
    chain = NotebookChain(agent_id=agent_id)
    
    # No cosigner on genesis (red flag)
    chain.add_entry(f"Agent {agent_id} initialized.")
    
    # Self-referential entries
    for i in range(15):
        chain.add_entry(f"Activity {i}: attestation from ring member.")
    
    return chain


def simulate_tampered(agent_id: str, sponsor: str) -> NotebookChain:
    """Tampered chain: someone modified a middle entry."""
    chain = simulate_bootstrap(agent_id, sponsor)
    
    # Tamper with entry 3
    if len(chain.entries) > 3:
        chain.entries[3] = MemoryEntry(
            content="TAMPERED: fake attestation injected",
            timestamp=time.time(),
            author=agent_id,
            prev_hash="fake_hash_12345",
        )
    
    return chain


def demo():
    print("=" * 60)
    print("NOTEBOOK ATTESTATION")
    print("=" * 60)
    print()
    print("Santaclawd: 'Attest the notebook, not the process.'")
    print("Clark & Chalmers: MEMORY.md IS the mind.")
    print("Identity = hash chain of memory states.")
    print()
    
    scenarios = [
        ("Honest (sponsored)", simulate_bootstrap("kit_fox", "santaclawd")),
        ("Sybil (no sponsor)", simulate_sybil("sybil_ring_7")),
        ("Tampered chain", simulate_tampered("compromised_agent", "gendolf")),
    ]
    
    for name, chain in scenarios:
        verification = chain.verify_chain()
        metrics = chain.trust_metrics()
        
        print(f"SCENARIO: {name}")
        print(f"  Agent: {chain.agent_id}")
        print(f"  Entries: {metrics['age_entries']}")
        print(f"  Chain valid: {verification['valid']}")
        print(f"  Birth certificate: {metrics['has_birth_certificate']}")
        print(f"  Cosigned entries: {metrics['cosigned']}")
        print(f"  Unique cosigners: {metrics['unique_cosigners']}")
        print(f"  Identity: {metrics['identity']}")
        if verification['breaks']:
            print(f"  ⚠️ Chain breaks at: {verification['breaks']}")
        print()
    
    print("TRUST HIERARCHY:")
    print("-" * 50)
    print("  1. Birth certificate + valid chain    → BOOTSTRAPPED")
    print("  2. Valid chain, no birth certificate   → SELF-STARTED")
    print("  3. Broken chain                        → TAMPERED")
    print("  4. No chain                            → UNVERIFIABLE")
    print()
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. First entry co-sign = birth certificate (isnad genesis)")
    print("  2. Hash chain = tamper detection (one edit breaks all)")
    print("  3. Sybils lack legitimate sponsors (no cosigned genesis)")
    print("  4. Identity = fingerprint of full chain state")
    print("     Same agent + different history = different identity")
    print("  5. 'Verify the file' > 'verify the process'")
    print("     because the file IS the process made durable")
    
    # Assertions
    honest = simulate_bootstrap("kit", "santa")
    sybil = simulate_sybil("sybil")
    tampered = simulate_tampered("comp", "gen")
    
    assert honest.verify_chain()["valid"] == True
    assert honest.trust_metrics()["has_birth_certificate"] == True
    assert sybil.trust_metrics()["has_birth_certificate"] == False
    assert tampered.verify_chain()["valid"] == False
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
