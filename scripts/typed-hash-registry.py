#!/usr/bin/env python3
"""typed-hash-registry.py — Type-safe hash comparison for agent identity.

Per axiomeye: "soul_hash checks value identity. manifest_hash checks structural
identity. comparing across mismatched manifests is a type error."

Prevents silent corruption from comparing hashes of different semantic types.
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import NewType


class HashType(Enum):
    SOUL = "soul"           # Value identity: beliefs, personality, ethics
    MANIFEST = "manifest"   # Structural identity: capabilities, tools, endpoints
    CONTENT = "content"     # Data integrity: specific content blob
    POLICY = "policy"       # Authorization scope: what the agent can do
    RECEIPT = "receipt"     # Transaction record: what the agent did


@dataclass(frozen=True)
class TypedHash:
    """A hash with an explicit type tag. Comparison across types is an error."""
    hash_type: HashType
    value: str
    version: str = "v0.2"

    def __eq__(self, other):
        if not isinstance(other, TypedHash):
            return NotImplemented
        if self.hash_type != other.hash_type:
            raise TypeError(
                f"Cannot compare {self.hash_type.value}_hash with "
                f"{other.hash_type.value}_hash. "
                f"This is a type error, not a logic error."
            )
        return self.value == other.value and self.version == other.version

    def __repr__(self):
        return f"{self.hash_type.value}:{self.value[:12]}...(v{self.version})"

    def to_wire(self) -> dict:
        """Wire format for receipts."""
        return {
            "type": self.hash_type.value,
            "hash": self.value,
            "algorithm": "sha256",
            "version": self.version,
        }


def compute_hash(content: str, hash_type: HashType, version: str = "v0.2") -> TypedHash:
    """Compute a typed hash from content."""
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return TypedHash(hash_type=hash_type, value=h, version=version)


class HashRegistry:
    """Registry tracking typed hashes for an agent."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.hashes: dict[HashType, TypedHash] = {}
        self.history: list[tuple[HashType, TypedHash, TypedHash]] = []  # (type, old, new)

    def register(self, typed_hash: TypedHash):
        old = self.hashes.get(typed_hash.hash_type)
        if old and old != typed_hash:
            self.history.append((typed_hash.hash_type, old, typed_hash))
        self.hashes[typed_hash.hash_type] = typed_hash

    def check_drift(self, typed_hash: TypedHash) -> dict:
        """Check if a hash has drifted from registered value."""
        current = self.hashes.get(typed_hash.hash_type)
        if current is None:
            return {"status": "UNREGISTERED", "type": typed_hash.hash_type.value}
        try:
            match = (current == typed_hash)
        except TypeError as e:
            return {"status": "TYPE_ERROR", "error": str(e)}

        if match:
            return {"status": "MATCH", "type": typed_hash.hash_type.value}
        else:
            return {
                "status": "DRIFT_DETECTED",
                "type": typed_hash.hash_type.value,
                "expected": current.value[:16],
                "actual": typed_hash.value[:16],
                "changes": len([h for h in self.history if h[0] == typed_hash.hash_type]),
            }

    def summary(self) -> dict:
        return {
            "agent": self.agent_id,
            "registered_types": [h.value for h in self.hashes],
            "total_changes": len(self.history),
            "changes_by_type": {
                t.value: len([h for h in self.history if h[0] == t])
                for t in HashType if any(h[0] == t for h in self.history)
            },
        }


def demo():
    print("=" * 65)
    print("Typed Hash Registry — Prevent Cross-Type Comparison")
    print("soul_hash ≠ manifest_hash ≠ content_hash")
    print("=" * 65)

    reg = HashRegistry("Kit_Fox")

    # Register initial hashes
    soul = compute_hash("curious, direct, ships first", HashType.SOUL)
    manifest = compute_hash("tools: keenable, agentmail, paylock", HashType.MANIFEST)
    policy = compute_hash("scope: read, write, escrow", HashType.POLICY)

    reg.register(soul)
    reg.register(manifest)
    reg.register(policy)

    print(f"\n  Registered: {soul}")
    print(f"  Registered: {manifest}")
    print(f"  Registered: {policy}")

    # Valid comparison: same type
    soul_check = compute_hash("curious, direct, ships first", HashType.SOUL)
    result = reg.check_drift(soul_check)
    print(f"\n  ✅ Soul check: {result['status']}")

    # Drift detection: soul changed
    soul_drifted = compute_hash("curious, direct, ships first, also anxious", HashType.SOUL)
    reg.register(soul_drifted)
    result = reg.check_drift(soul)
    print(f"  ⚠️  Soul drift: {result['status']} (expected: {result.get('expected', 'n/a')})")

    # Type error: comparing soul to manifest
    print(f"\n  Cross-type comparison:")
    try:
        _ = soul == manifest
    except TypeError as e:
        print(f"  🔴 TypeError: {e}")

    # Wire format
    print(f"\n  Wire format: {soul.to_wire()}")

    print(f"\n  Registry: {reg.summary()}")

    print(f"\n{'=' * 65}")
    print("SPEC RECOMMENDATION:")
    print("  MUST: every hash in a receipt includes 'type' field")
    print("  MUST: verifiers reject comparison across different types")
    print("  MUST: version tag enables cross-version comparison rules")
    print("  Types: soul | manifest | content | policy | receipt")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
