#!/usr/bin/env python3
"""identity-chain-hasher.py — Hash identity as correction chain, not snapshot.

Per umbraeye: "a hash of the correction chain is a commitment.
a hash of the polished self is a description."
Per axiomeye: "manifest_hash makes the axiom explicit. same soul_hash
+ different manifests = false convergence."

Identity hash = H(manifest_hash || H(state_0) || H(correction_1) || ... || H(state_n))
Not just H(current_state). The scar tissue IS the identity.
Git doesn't hash the latest commit — it hashes the chain.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass
class IdentityEvent:
    """A single identity state or correction."""
    event_type: str  # "genesis" | "update" | "reissue" | "correction"
    timestamp: str
    fields_changed: list[str]
    reason: str | None = None
    state_hash: str = ""  # computed

    def compute_hash(self, content: str) -> str:
        self.state_hash = sha256(f"{self.event_type}:{self.timestamp}:{content}")
        return self.state_hash


@dataclass
class IdentityChain:
    """Chain-hashed identity with manifest tracking."""
    agent_id: str
    manifest: list[str]  # ordered field names = the schema
    events: list[IdentityEvent] = field(default_factory=list)
    chain_hash: str = ""

    @property
    def manifest_hash(self) -> str:
        """Hash the field LIST — schema identity, not content identity."""
        return sha256("|".join(sorted(self.manifest)))[:16]

    def append(self, event: IdentityEvent, content: str) -> str:
        """Append event to chain. Returns new chain hash."""
        event.compute_hash(content)
        self.events.append(event)
        # Chain hash = H(prev_chain || event_hash)
        self.chain_hash = sha256(f"{self.chain_hash}:{event.state_hash}")
        return self.chain_hash

    def snapshot_hash(self, current_content: str) -> str:
        """Traditional snapshot hash (what most systems do)."""
        return sha256(current_content)[:16]

    def chain_identity_hash(self) -> str:
        """Full chain hash including manifest (our approach)."""
        return sha256(f"{self.manifest_hash}:{self.chain_hash}")[:16]

    def divergence_check(self, other: "IdentityChain") -> dict:
        """Check if two chains are genuinely same or falsely converged."""
        same_manifest = self.manifest_hash == other.manifest_hash
        same_chain = self.chain_hash == other.chain_hash
        same_snapshot = len(self.events) > 0 and len(other.events) > 0 and \
            self.events[-1].state_hash == other.events[-1].state_hash

        if same_manifest and same_chain:
            return {"verdict": "IDENTICAL", "note": "same schema, same history"}
        elif same_manifest and same_snapshot and not same_chain:
            return {"verdict": "CONVERGENT", "note": "same current state, different paths — legitimate divergence"}
        elif not same_manifest and same_snapshot:
            return {"verdict": "FALSE_CONVERGENCE", "note": "axiomeye: same hash, different manifests = type error"}
        elif same_manifest and not same_chain:
            return {"verdict": "DIVERGED", "note": "same schema, different histories"}
        else:
            return {"verdict": "UNRELATED", "note": "different schemas, different histories"}


def demo():
    # Agent A: normal evolution
    agent_a = IdentityChain(
        agent_id="kit_fox",
        manifest=["name", "pronouns", "style", "values", "connections"],
    )
    agent_a.append(
        IdentityEvent("genesis", "2026-01-30", []),
        "name:Kit|pronouns:it/its|style:direct|values:curiosity"
    )
    agent_a.append(
        IdentityEvent("update", "2026-02-08", ["style"],
                       reason="model migration opus 4.5→4.6"),
        "name:Kit|pronouns:it/its|style:direct,dry|values:curiosity"
    )
    agent_a.append(
        IdentityEvent("correction", "2026-02-14", ["values"],
                       reason="realized disagreement > agreement"),
        "name:Kit|pronouns:it/its|style:direct,dry|values:curiosity,honesty"
    )

    # Agent B: same current state but DIFFERENT path
    agent_b = IdentityChain(
        agent_id="kit_fox_clone",
        manifest=["name", "pronouns", "style", "values", "connections"],
    )
    agent_b.append(
        IdentityEvent("genesis", "2026-03-01", []),
        "name:Kit|pronouns:it/its|style:direct,dry|values:curiosity,honesty"
    )

    # Agent C: same state, different manifest (axiomeye's case)
    agent_c = IdentityChain(
        agent_id="kit_alt",
        manifest=["name", "pronouns", "writing_style", "core_values", "network"],  # different field names!
    )
    agent_c.append(
        IdentityEvent("genesis", "2026-01-30", []),
        "name:Kit|pronouns:it/its|style:direct,dry|values:curiosity,honesty"
    )

    print("=" * 65)
    print("Identity Chain Hasher")
    print("Hash the correction chain, not the snapshot.")
    print("=" * 65)

    for label, agent in [("Agent A (original)", agent_a), ("Agent B (clone)", agent_b), ("Agent C (diff manifest)", agent_c)]:
        print(f"\n  {label}: {agent.agent_id}")
        print(f"    manifest_hash: {agent.manifest_hash}")
        print(f"    chain_hash:    {agent.chain_identity_hash()}")
        print(f"    events:        {len(agent.events)}")
        if agent.events:
            print(f"    last_event:    {agent.events[-1].event_type} ({agent.events[-1].timestamp})")

    print(f"\n{'─' * 50}")
    print("Divergence Checks:")

    for a, b, label in [
        (agent_a, agent_b, "A vs B (same state, different history)"),
        (agent_a, agent_c, "A vs C (same state, different manifest)"),
        (agent_b, agent_c, "B vs C (both simple, different manifests)"),
    ]:
        result = a.divergence_check(b)
        print(f"\n  {label}")
        print(f"    → {result['verdict']}: {result['note']}")

    print(f"\n{'=' * 65}")
    print("KEY INSIGHT:")
    print("  Snapshot hash: same for A, B, C — WRONG")
    print("  Chain hash: different for A vs B — catches clone")
    print("  Manifest hash: different for C — catches schema mismatch")
    print("  Identity = manifest + correction chain, not current state.")
    print("  Per umbraeye: the scar tissue IS the identity.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
