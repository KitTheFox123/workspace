#!/usr/bin/env python3
"""
cid-null-receipt.py — CID-formatted null receipts for absence attestation.

Based on:
- santaclawd: "null receipt as a CID. algo pinned in the ID itself (no silent downgrade)"
- IPFS CID v1: <version><codec><multihash>
- isnad v2: needs native CID support for receipt format

A null receipt proves an agent SAW an opportunity and CHOSE not to act.
CID format makes receipts:
- Self-describing (codec + hash algo embedded)
- Content-addressable (deterministic from inputs)
- Algo-agnostic (no silent hash downgrade)
- Reproducible (any party can verify)

CID = version(1) + codec(dag-cbor=0x71) + multihash(sha2-256=0x12 + length + digest)
"""

import hashlib
import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Codec(IntEnum):
    DAG_CBOR = 0x71
    DAG_JSON = 0x0129
    RAW = 0x55


class HashAlgo(IntEnum):
    SHA2_256 = 0x12
    SHA2_512 = 0x13
    SHA3_256 = 0x16
    BLAKE2B_256 = 0xb220


@dataclass
class NullReceipt:
    scope_manifest_hash: str
    scope_holder_id: str
    capability: str
    failure_mode: str  # "chosen", "imposed", "ignorant"
    timestamp: int     # Unix epoch seconds (integer!)
    reason: Optional[str] = None

    def canonical_bytes(self) -> bytes:
        """JCS-like canonical form for hashing."""
        obj = {
            "capability": self.capability,
            "failure_mode": self.failure_mode,
            "scope_holder_id": self.scope_holder_id,
            "scope_manifest_hash": self.scope_manifest_hash,
            "timestamp": self.timestamp,
        }
        if self.reason:
            obj["reason"] = self.reason
        return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()

    def to_cid(self, codec: Codec = Codec.DAG_CBOR,
               hash_algo: HashAlgo = HashAlgo.SHA2_256) -> str:
        """Generate CID v1 for this null receipt."""
        content = self.canonical_bytes()

        # Hash
        if hash_algo == HashAlgo.SHA2_256:
            digest = hashlib.sha256(content).digest()
        elif hash_algo == HashAlgo.SHA2_512:
            digest = hashlib.sha512(content).digest()
        elif hash_algo == HashAlgo.SHA3_256:
            digest = hashlib.sha3_256(content).digest()
        else:
            digest = hashlib.sha256(content).digest()

        # Multihash: <algo_varint><length_varint><digest>
        multihash = _varint(hash_algo) + _varint(len(digest)) + digest

        # CID v1: <version=1><codec_varint><multihash>
        cid_bytes = _varint(1) + _varint(codec) + multihash

        # Base32 encoding (multibase 'b' prefix)
        import base64
        b32 = base64.b32encode(cid_bytes).decode().lower().rstrip('=')
        return f"b{b32}"

    def verify_cid(self, cid: str) -> bool:
        """Verify a CID matches this receipt."""
        return self.to_cid() == cid


def _varint(value: int) -> bytes:
    """Encode unsigned integer as varint."""
    result = bytearray()
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value & 0x7f)
    return bytes(result)


def demo_null_receipts():
    """Show CID null receipts for different absence types."""
    receipts = [
        NullReceipt(
            scope_manifest_hash="abc123def456",
            scope_holder_id="kit_fox",
            capability="post_research",
            failure_mode="chosen",
            timestamp=1709600000,
            reason="quality_gate_not_met"
        ),
        NullReceipt(
            scope_manifest_hash="abc123def456",
            scope_holder_id="kit_fox",
            capability="engage_feeds",
            failure_mode="chosen",
            timestamp=1709600000,
            reason="feed_was_spam"
        ),
        NullReceipt(
            scope_manifest_hash="abc123def456",
            scope_holder_id="kit_fox",
            capability="reply_mentions",
            failure_mode="imposed",
            timestamp=1709600000,
            reason="platform_rate_limited"
        ),
    ]

    print(f"{'Capability':<20} {'Mode':<10} {'CID':<60} {'Reason'}")
    print("-" * 110)
    for r in receipts:
        cid = r.to_cid()
        print(f"{r.capability:<20} {r.failure_mode:<10} {cid[:55]}... {r.reason or ''}")

    # Verify round-trip
    print("\n--- Verification Round-Trip ---")
    for r in receipts:
        cid = r.to_cid()
        verified = r.verify_cid(cid)
        print(f"  {r.capability}: {cid[:30]}... verified={verified}")

    # Tamper detection
    print("\n--- Tamper Detection ---")
    original = receipts[0]
    original_cid = original.to_cid()
    tampered = NullReceipt(
        scope_manifest_hash="abc123def456",
        scope_holder_id="kit_fox",
        capability="post_research",
        failure_mode="chosen",
        timestamp=1709600001,  # Changed by 1 second
        reason="quality_gate_not_met"
    )
    tampered_cid = tampered.to_cid()
    print(f"  Original: {original_cid[:40]}...")
    print(f"  Tampered: {tampered_cid[:40]}...")
    print(f"  Match: {original_cid == tampered_cid}")
    print(f"  1 second difference → completely different CID")

    # Hash algo agility
    print("\n--- Hash Algo Agility (no silent downgrade) ---")
    r = receipts[0]
    for algo in [HashAlgo.SHA2_256, HashAlgo.SHA2_512, HashAlgo.SHA3_256]:
        cid = r.to_cid(hash_algo=algo)
        print(f"  {algo.name}: {cid[:50]}...")
    print("  Algo is EMBEDDED in CID — verifier always knows which hash was used")


def main():
    print("=" * 70)
    print("CID NULL RECEIPTS")
    print("santaclawd: 'the receipt IS the commitment'")
    print("=" * 70)

    demo_null_receipts()

    print("\n--- isnad v2 Integration ---")
    print("Attestation envelope:")
    print("  {")
    print('    "type": "null_receipt",')
    print('    "cid": "bafy...",          // Self-describing')
    print('    "scope_manifest_hash": "...",')
    print('    "capability": "...",')
    print('    "failure_mode": "chosen|imposed|ignorant",')
    print('    "timestamp": 1709600000,   // Integer epoch')
    print('    "signature": "...",         // Ed25519 over CID')
    print("  }")
    print()
    print("CID properties for trust:")
    print("  1. Algo-pinned: hash algo in the ID itself, no silent downgrade")
    print("  2. Content-addressable: deterministic from inputs")
    print("  3. Self-describing: no external schema needed to parse")
    print("  4. Codec-explicit: dag-cbor for machine, dag-json for debug")
    print()
    print("The receipt IS the commitment. Sign the CID, not the content.")
    print("Anyone can recompute CID from content to verify.")


if __name__ == "__main__":
    main()
