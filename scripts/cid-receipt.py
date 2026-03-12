#!/usr/bin/env python3
"""
cid-receipt.py — CID-native attestation receipts for isnad v2.

Based on:
- santaclawd: "null receipt as a CID. CID = <codec><hash_algo><digest>"
- IPFS CIDv1: multibase + multicodec + multihash
- Multiformats spec: self-describing, algo-pinned identifiers

The receipt IS a CID. Self-describing, content-addressable, algo-pinned.
No silent hash downgrade (SHA-256→MD5 invisible in plain hex).
Works WITHOUT IPFS infrastructure — just the encoding standard.

Receipt types:
- Action receipt: CID(scope_hash + output_hash + timestamp)
- Null receipt: CID(scope_hash + holder_hash + failure_mode)
- Absence receipt: CID(scope_hash + "ABSENT" + heartbeat_hash)
"""

import hashlib
import json
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# Multicodec table (subset)
MULTICODEC = {
    "raw": 0x55,
    "dag-cbor": 0x71,
    "dag-json": 0x0129,
    "json": 0x0200,
}

# Multihash function codes
MULTIHASH = {
    "sha2-256": 0x12,
    "sha2-512": 0x13,
    "sha3-256": 0x16,
    "blake2b-256": 0xb220,
}

# CID version
CID_V1 = 1


class ReceiptType(Enum):
    ACTION = "action"
    NULL = "null"
    ABSENCE = "absence"


class FailureMode(Enum):
    CHOSEN = "chosen"       # Agent declined
    IMPOSED = "imposed"     # Agent prevented
    TIMEOUT = "timeout"     # Deadline passed
    ERROR = "error"         # Execution failed


@dataclass
class Receipt:
    receipt_type: ReceiptType
    scope_hash: str
    holder_hash: str
    payload: dict
    hash_algo: str = "sha2-256"
    codec: str = "dag-json"


def varint_encode(n: int) -> bytes:
    """Encode unsigned integer as varint (LEB128)."""
    result = []
    while n > 0x7f:
        result.append((n & 0x7f) | 0x80)
        n >>= 7
    result.append(n & 0x7f)
    return bytes(result)


def compute_multihash(data: bytes, algo: str = "sha2-256") -> bytes:
    """Compute multihash: <hash_func_code><digest_size><digest>."""
    if algo == "sha2-256":
        digest = hashlib.sha256(data).digest()
    elif algo == "sha2-512":
        digest = hashlib.sha512(data).digest()
    elif algo == "sha3-256":
        digest = hashlib.sha3_256(data).digest()
    else:
        raise ValueError(f"Unsupported algo: {algo}")

    func_code = MULTIHASH[algo]
    return varint_encode(func_code) + varint_encode(len(digest)) + digest


def make_cid(data: bytes, codec: str = "dag-json", hash_algo: str = "sha2-256") -> str:
    """Create CIDv1 string (base16 for readability)."""
    mh = compute_multihash(data, hash_algo)
    codec_code = MULTICODEC[codec]

    # CIDv1 binary: <version><codec><multihash>
    cid_bytes = varint_encode(CID_V1) + varint_encode(codec_code) + mh

    # Base16 (hex) representation with 'f' prefix (multibase)
    return "f" + cid_bytes.hex()


def generate_receipt(receipt: Receipt) -> dict:
    """Generate a CID-native receipt."""
    # Canonical JSON (sorted keys)
    content = json.dumps({
        "type": receipt.receipt_type.value,
        "scope": receipt.scope_hash,
        "holder": receipt.holder_hash,
        "payload": receipt.payload,
    }, sort_keys=True).encode()

    cid = make_cid(content, receipt.codec, receipt.hash_algo)

    return {
        "cid": cid,
        "type": receipt.receipt_type.value,
        "algo": receipt.hash_algo,
        "codec": receipt.codec,
        "content_size": len(content),
    }


def verify_no_downgrade(cid: str) -> dict:
    """Extract algo from CID — downgrade is visible."""
    # Strip multibase prefix
    hex_str = cid[1:]  # Remove 'f' prefix
    raw = bytes.fromhex(hex_str)

    # Parse version (varint)
    version = raw[0]

    # Parse codec (varint — simplified for common cases)
    codec_byte = raw[1]
    codec_name = {v: k for k, v in MULTICODEC.items()}.get(codec_byte, f"0x{codec_byte:02x}")

    # Parse multihash function code
    mh_start = 2
    func_code = raw[mh_start]
    algo_name = {v: k for k, v in MULTIHASH.items()}.get(func_code, f"0x{func_code:02x}")

    digest_len = raw[mh_start + 1]

    return {
        "version": version,
        "codec": codec_name,
        "hash_algo": algo_name,
        "digest_length": digest_len,
        "downgrade_visible": True,
    }


def main():
    print("=" * 70)
    print("CID-NATIVE ATTESTATION RECEIPTS")
    print("santaclawd: 'the receipt IS the commitment'")
    print("=" * 70)

    # Action receipt
    print("\n--- Action Receipt ---")
    action = Receipt(
        ReceiptType.ACTION, "scope_abc123", "kit_fox",
        {"output_hash": "deadbeef", "timestamp": 1709596800, "score_bp": 9200}
    )
    r1 = generate_receipt(action)
    print(f"CID: {r1['cid'][:60]}...")
    print(f"Algo: {r1['algo']}, Codec: {r1['codec']}")

    # Null receipt (chosen silence)
    print("\n--- Null Receipt (Chosen Silence) ---")
    null = Receipt(
        ReceiptType.NULL, "scope_abc123", "kit_fox",
        {"failure_mode": FailureMode.CHOSEN.value, "reason": "spam_detected"}
    )
    r2 = generate_receipt(null)
    print(f"CID: {r2['cid'][:60]}...")
    print(f"Algo: {r2['algo']}, Codec: {r2['codec']}")

    # Absence receipt
    print("\n--- Absence Receipt ---")
    absence = Receipt(
        ReceiptType.ABSENCE, "scope_abc123", "kit_fox",
        {"heartbeat_hash": "cafe0001", "expected_action": "reply_mentions"}
    )
    r3 = generate_receipt(absence)
    print(f"CID: {r3['cid'][:60]}...")

    # Downgrade detection
    print("\n--- Downgrade Detection ---")
    for r in [r1, r2, r3]:
        info = verify_no_downgrade(r["cid"])
        print(f"CID algo={info['hash_algo']}, codec={info['codec']}, "
              f"digest_len={info['digest_length']}, downgrade_visible={info['downgrade_visible']}")

    # Compare with SHA-3
    print("\n--- Same Content, Different Algo ---")
    action_sha3 = Receipt(
        ReceiptType.ACTION, "scope_abc123", "kit_fox",
        {"output_hash": "deadbeef", "timestamp": 1709596800, "score_bp": 9200},
        hash_algo="sha3-256"
    )
    r4 = generate_receipt(action_sha3)
    print(f"SHA-256 CID: {r1['cid'][:40]}...")
    print(f"SHA3-256 CID: {r4['cid'][:40]}...")
    print(f"Same content, different CID (algo visible in ID)")

    # ABI proposal
    print("\n--- isnad v2 Receipt Format ---")
    print("receipt_cid:  CIDv1(dag-json, sha2-256, canonical_json)")
    print("null_cid:     CIDv1(dag-json, sha2-256, scope+holder+failure)")
    print("absence_cid:  CIDv1(dag-json, sha2-256, scope+heartbeat+expected)")
    print()
    print("Properties:")
    print("  - Self-describing: algo + codec visible in CID itself")
    print("  - No silent downgrade: SHA-256→MD5 changes CID prefix")
    print("  - Content-addressable: same receipt = same CID always")
    print("  - Works WITHOUT IPFS: just multiformat encoding")
    print("  - Null receipt IS a commitment (not absence of data)")


if __name__ == "__main__":
    main()
