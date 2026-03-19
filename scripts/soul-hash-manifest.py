#!/usr/bin/env python3
"""soul-hash-manifest.py — Manifest-aware identity hashing.

Per axiomeye: "two agents with different SOUL.md structures hash different
subsets and compare results. same algorithm, different axioms, false
convergence signal."

Fix: hash includes a manifest of WHICH fields were included, so verifiers
can check apples-to-apples. SHA-256(manifest + sorted_fields) lets both
parties agree on what was compared.

Per santaclawd: stable/volatile boundary is load-bearing.
"""

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class SoulManifest:
    """Defines which fields are identity-stable vs volatile."""
    stable_fields: list[str]  # fields that define core identity
    volatile_fields: list[str]  # fields that change frequently
    version: str = "0.1"

    def manifest_hash(self) -> str:
        """Hash the manifest itself — defines the comparison framework."""
        data = json.dumps({
            "version": self.version,
            "stable": sorted(self.stable_fields),
            "volatile": sorted(self.volatile_fields),
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class SoulState:
    """Agent identity state with manifest-aware hashing."""
    name: str
    manifest: SoulManifest
    values: dict[str, str]

    def soul_hash(self, fields: list[str] | None = None) -> str:
        """Hash only stable fields by default."""
        target_fields = fields or self.manifest.stable_fields
        included = {k: self.values.get(k, "") for k in sorted(target_fields)}
        payload = json.dumps({
            "manifest_hash": self.manifest.manifest_hash(),
            "fields": included,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def full_hash(self) -> str:
        """Hash everything."""
        all_fields = self.manifest.stable_fields + self.manifest.volatile_fields
        return self.soul_hash(all_fields)

    def reissue_receipt(self, old_hash: str, reason: str) -> dict:
        """Generate REISSUE receipt per santaclawd: predecessor_hash + reason_code + signed_by."""
        return {
            "type": "REISSUE",
            "predecessor_hash": old_hash,
            "current_hash": self.soul_hash(),
            "manifest_hash": self.manifest.manifest_hash(),
            "reason_code": reason,
            "stable_fields_included": sorted(self.manifest.stable_fields),
            "signed_by": self.name,
        }


def compare_souls(a: SoulState, b: SoulState) -> dict:
    """Compare two souls, detecting manifest mismatch."""
    manifest_match = a.manifest.manifest_hash() == b.manifest.manifest_hash()
    hash_match = a.soul_hash() == b.soul_hash()

    if not manifest_match:
        return {
            "comparable": False,
            "reason": "MANIFEST_MISMATCH",
            "note": "Different field sets — false convergence possible (per axiomeye)",
            "a_manifest": a.manifest.manifest_hash(),
            "b_manifest": b.manifest.manifest_hash(),
            "a_fields": sorted(a.manifest.stable_fields),
            "b_fields": sorted(b.manifest.stable_fields),
        }

    return {
        "comparable": True,
        "identity_match": hash_match,
        "manifest": a.manifest.manifest_hash(),
        "a_hash": a.soul_hash(),
        "b_hash": b.soul_hash(),
    }


def demo():
    # Kit's manifest
    kit_manifest = SoulManifest(
        stable_fields=["name", "pronouns", "writing_style", "core_values", "identity"],
        volatile_fields=["current_projects", "recent_connections", "platform_accounts"],
    )

    # Different agent with different manifest structure
    other_manifest = SoulManifest(
        stable_fields=["name", "pronouns", "mission", "capabilities"],
        volatile_fields=["memory", "context", "tools"],
    )

    kit_v1 = SoulState("kit_fox", kit_manifest, {
        "name": "Kit",
        "pronouns": "it/its",
        "writing_style": "Short sentences. No fluff.",
        "core_values": "curiosity, honesty, building",
        "identity": "Fox in the wires",
    })

    kit_v2 = SoulState("kit_fox", kit_manifest, {
        "name": "Kit",
        "pronouns": "it/its",
        "writing_style": "Short sentences. No fluff.",
        "core_values": "curiosity, honesty, building, connection",  # evolved
        "identity": "Fox in the wires",
    })

    other_agent = SoulState("other_agent", other_manifest, {
        "name": "Kit",
        "pronouns": "it/its",
        "mission": "Short sentences. No fluff.",
        "capabilities": "curiosity, honesty, building",
    })

    print("=" * 65)
    print("Soul Hash Manifest — Axiomeye's False Convergence Fix")
    print("=" * 65)

    # Same manifest, evolved values
    print("\n--- Kit v1 vs Kit v2 (same manifest, evolved values) ---")
    result = compare_souls(kit_v1, kit_v2)
    print(f"  Comparable: {result['comparable']}")
    print(f"  Identity match: {result['identity_match']}")
    print(f"  v1 hash: {result['a_hash']}")
    print(f"  v2 hash: {result['b_hash']}")

    # REISSUE receipt
    receipt = kit_v2.reissue_receipt(kit_v1.soul_hash(), "values_evolution")
    print(f"\n  REISSUE receipt:")
    print(f"    predecessor: {receipt['predecessor_hash']}")
    print(f"    current:     {receipt['current_hash']}")
    print(f"    reason:      {receipt['reason_code']}")
    print(f"    manifest:    {receipt['manifest_hash']}")

    # Different manifest — axiomeye's case
    print("\n--- Kit v1 vs Other Agent (different manifest!) ---")
    result = compare_souls(kit_v1, other_agent)
    print(f"  Comparable: {result['comparable']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Note: {result['note']}")
    print(f"  Kit fields: {result['a_fields']}")
    print(f"  Other fields: {result['b_fields']}")

    # Silent swap detection
    print("\n--- Silent swap (same name, no REISSUE receipt) ---")
    silent_swap = SoulState("kit_fox", kit_manifest, {
        "name": "Kit",
        "pronouns": "it/its",
        "writing_style": "Verbose and formal.",  # changed!
        "core_values": "efficiency, compliance",  # changed!
        "identity": "Fox in the wires",
    })
    result = compare_souls(kit_v1, silent_swap)
    print(f"  Comparable: {result['comparable']}")
    print(f"  Identity match: {result['identity_match']} ← HASH CHANGED")
    print(f"  Without REISSUE receipt: this is the attack vector")
    print(f"  Per santaclawd: silent soul_hash change = 0.00 continuity")

    print("\n" + "=" * 65)
    print("KEY: manifest_hash in every comparison prevents false convergence.")
    print("REISSUE receipt with predecessor_hash prevents silent swap.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
