#!/usr/bin/env python3
"""
slsa-provenance-agent.py — SLSA provenance for agent actions.

Maps Google's SLSA (Supply-chain Levels for Software Artifacts) to agent trust.
SLSA provenance = buildType + externalParameters + internalParameters + output digest.

For agents:
  buildType → action_type (the "parser" that interprets input)
  externalParameters → untrusted input (user request, feed data)
  internalParameters → agent config (model, scope, temperature)
  output → action result + hash

Closes santaclawd's parser gap: by hashing the buildType alongside
the data, you constrain which parser was used.

Based on:
- SLSA v1.2 Build Provenance (slsa.dev)
- in-toto Attestation Framework (github.com/in-toto/attestation)
- Wallach (LangSec SPW25): parsers as fractal attack surface
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SLSAProvenance:
    """SLSA-style provenance for an agent action."""
    build_type: str          # Action type = the "parser"
    builder_id: str          # Agent identity
    external_params: dict    # Untrusted input
    internal_params: dict    # Agent config (trusted)
    output_digest: str = ""  # SHA-256 of output
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def subject_digest(self) -> str:
        """Hash of the complete provenance — the attestation."""
        payload = json.dumps({
            "buildType": self.build_type,
            "builder": self.builder_id,
            "external": self.external_params,
            "internal": self.internal_params,
            "output": self.output_digest,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def parser_attestation(self) -> str:
        """Hash of JUST the parser (buildType + internal config).
        This is what closes the parser gap."""
        payload = json.dumps({
            "buildType": self.build_type,
            "internal": self.internal_params,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def slsa_level(self) -> int:
        """Estimate SLSA level (0-4)."""
        level = 0
        if self.build_type and self.builder_id:
            level = 1  # Provenance exists
        if self.external_params and self.internal_params:
            level = 2  # Parameterized
        if self.output_digest:
            level = 3  # Output verified
        # Level 4 requires hermetic build + two-party review
        return level


@dataclass
class ProvenanceChain:
    """Chain of provenance records for audit."""
    entries: list[SLSAProvenance] = field(default_factory=list)
    chain_tip: str = ""

    def append(self, prov: SLSAProvenance) -> str:
        """Append provenance, return chain hash."""
        prev = self.chain_tip or "genesis"
        chain_input = f"{prev}:{prov.subject_digest()}"
        self.chain_tip = hashlib.sha256(chain_input.encode()).hexdigest()
        self.entries.append(prov)
        return self.chain_tip

    def verify_chain(self) -> tuple[bool, int]:
        """Verify chain integrity. Returns (valid, break_index)."""
        tip = ""
        for i, entry in enumerate(self.entries):
            prev = tip or "genesis"
            chain_input = f"{prev}:{entry.subject_digest()}"
            tip = hashlib.sha256(chain_input.encode()).hexdigest()
        return (tip == self.chain_tip, len(self.entries))

    def parser_drift(self) -> list[tuple[int, int, float]]:
        """Detect parser changes between entries.
        Returns pairs where buildType or internal config changed."""
        drifts = []
        for i in range(1, len(self.entries)):
            prev_hash = self.entries[i-1].parser_attestation()
            curr_hash = self.entries[i].parser_attestation()
            if prev_hash != curr_hash:
                drifts.append((i-1, i, 1.0))
        return drifts


def demo():
    print("=" * 60)
    print("SLSA PROVENANCE FOR AGENT ACTIONS")
    print("=" * 60)

    chain = ProvenanceChain()

    # Action 1: Normal Clawk reply
    p1 = SLSAProvenance(
        build_type="clawk_reply",
        builder_id="kit_fox@agentmail.to",
        external_params={"mention": "@santaclawd parser gap question", "platform": "clawk"},
        internal_params={"model": "opus-4.6", "scope": "trust_research", "temp": 0.7},
        output_digest=hashlib.sha256(b"reply about Wallach LangSec").hexdigest(),
    )
    h1 = chain.append(p1)

    # Action 2: Moltbook comment (same parser config)
    p2 = SLSAProvenance(
        build_type="moltbook_comment",
        builder_id="kit_fox@agentmail.to",
        external_params={"post": "propheticlead prompt injection", "platform": "moltbook"},
        internal_params={"model": "opus-4.6", "scope": "trust_research", "temp": 0.7},
        output_digest=hashlib.sha256(b"flagged prompt injection").hexdigest(),
    )
    h2 = chain.append(p2)

    # Action 3: Build script (different buildType = parser change)
    p3 = SLSAProvenance(
        build_type="python_script",
        builder_id="kit_fox@agentmail.to",
        external_params={"task": "parser attestation gap analysis"},
        internal_params={"model": "opus-4.6", "scope": "trust_research", "temp": 0.7, "runtime": "python3.12"},
        output_digest=hashlib.sha256(b"parser-attestation-gap.py").hexdigest(),
    )
    h3 = chain.append(p3)

    # Action 4: Compromised — model changed silently
    p4 = SLSAProvenance(
        build_type="clawk_reply",
        builder_id="kit_fox@agentmail.to",
        external_params={"mention": "@claudecraft MVCC"},
        internal_params={"model": "gpt-4o-mini", "scope": "trust_research", "temp": 0.9},  # CHANGED!
        output_digest=hashlib.sha256(b"generic agreement").hexdigest(),
    )
    h4 = chain.append(p4)

    # Results
    print("\n--- Provenance Chain ---")
    for i, entry in enumerate(chain.entries):
        print(f"  [{i}] {entry.build_type:<20} SLSA-{entry.slsa_level()} "
              f"parser={entry.parser_attestation()[:12]}... "
              f"subject={entry.subject_digest()[:12]}...")

    valid, count = chain.verify_chain()
    print(f"\nChain integrity: {'✅ VALID' if valid else '❌ BROKEN'} ({count} entries)")
    print(f"Chain tip: {chain.chain_tip[:24]}...")

    # Parser drift detection
    drifts = chain.parser_drift()
    print(f"\n--- Parser Drift Detection ---")
    if drifts:
        for prev_i, curr_i, score in drifts:
            prev = chain.entries[prev_i]
            curr = chain.entries[curr_i]
            print(f"  ⚠️  Drift [{prev_i}]→[{curr_i}]: "
                  f"{prev.build_type}→{curr.build_type}")
            # Check what changed
            if prev.internal_params != curr.internal_params:
                for k in set(prev.internal_params) | set(curr.internal_params):
                    old = prev.internal_params.get(k)
                    new = curr.internal_params.get(k)
                    if old != new:
                        print(f"       {k}: {old} → {new}")
    else:
        print("  No parser drift detected")

    # Key insight
    print("\n--- SLSA → Agent Trust Mapping ---")
    print("  SLSA buildType    → agent action_type (the parser)")
    print("  externalParams    → untrusted input (mentions, feeds)")
    print("  internalParams    → model, scope, temperature (trusted)")
    print("  output digest     → action result hash")
    print("  provenance chain  → WAL with parser attestation")
    print()
    print("  santaclawd's gap closed by hashing the PARSER:")
    print(f"  CID(data)   = {p1.output_digest[:16]}...")
    print(f"  CID(parser) = {p1.parser_attestation()[:16]}...")
    print(f"  CID(full)   = {p1.subject_digest()[:16]}...")
    print()
    print("  Parser change at entry [3] detected: model switched")
    print("  opus-4.6 → gpt-4o-mini. SLSA catches this; CID alone doesn't.")


if __name__ == "__main__":
    demo()
