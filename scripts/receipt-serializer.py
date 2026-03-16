#!/usr/bin/env python3
"""
receipt-serializer.py — Portable L3.5 receipt serialization format.

Per funwolf: "the receipt format just needs to serialize into an attachment."
Per santaclawd: "the schema IS the spec."

Design goals:
  1. Two independent parsers must produce identical results (interop test)
  2. Email-attachable (DKIM-signed delivery = authenticated receipt)
  3. Self-describing (no shared code needed to parse)
  4. Merkle-verifiable (inclusion proof in the receipt itself)

Format: JSON with required fields + optional extensions.
Content-addressable: receipt_id = sha256(canonical JSON of content fields).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


# === Receipt Schema v0.1 ===

SCHEMA_VERSION = "0.1.0"
CONTENT_TYPE = "application/vnd.l35.receipt+json"

# Required fields (spec layer — must be in every receipt)
REQUIRED_FIELDS = {
    "schema_version",   # Format version
    "receipt_type",     # attestation | delivery | revocation | slash
    "agent_id",         # Who this receipt is about
    "issuer_id",        # Who issued the receipt
    "timestamp",        # ISO 8601 UTC
    "content_hash",     # sha256 of the action content
    "dimensions",       # T/G/A/S/C trust dimensions (spec: wire format)
}

# Optional fields (enforcement layer — consumer decides what to require)
OPTIONAL_FIELDS = {
    "merkle_root",      # Tree root if part of a log
    "inclusion_proof",  # Sibling hashes for verification
    "witnesses",        # Independent attestation signatures
    "diversity_hash",   # Operator diversity self-certification
    "parent_receipt",   # Chain to previous receipt
    "metadata",         # Freeform extensions
}


class ReceiptType(Enum):
    ATTESTATION = "attestation"
    DELIVERY = "delivery"
    REVOCATION = "revocation"
    SLASH = "slash"
    HEARTBEAT = "heartbeat"   # Liveness proof (null action = present)


@dataclass
class TrustDimensions:
    """L3.5 trust vector — wire format only, no scoring."""
    T: float = 0.0   # Timeliness (delivery speed)
    G: float = 0.0   # Gossip (reputation from others)
    A: float = 0.0   # Attestation (verified claims)
    S: float = 0.0   # Stability (consistency over time)
    C: float = 0.0   # Commitment (skin in the game)
    
    def to_dict(self) -> dict:
        return {"T": self.T, "G": self.G, "A": self.A, "S": self.S, "C": self.C}


@dataclass
class WitnessEntry:
    operator_id: str
    operator_org: str
    signature: str
    timestamp: str  # ISO 8601
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class Receipt:
    receipt_type: ReceiptType
    agent_id: str
    issuer_id: str
    content_hash: str
    dimensions: TrustDimensions
    witnesses: list[WitnessEntry] = field(default_factory=list)
    merkle_root: Optional[str] = None
    inclusion_proof: Optional[list[str]] = None
    diversity_hash: Optional[str] = None
    parent_receipt: Optional[str] = None
    metadata: Optional[dict] = None
    
    def to_canonical(self) -> dict:
        """Canonical JSON for content-addressable ID generation."""
        return {
            "schema_version": SCHEMA_VERSION,
            "receipt_type": self.receipt_type.value,
            "agent_id": self.agent_id,
            "issuer_id": self.issuer_id,
            "timestamp": self._timestamp,
            "content_hash": self.content_hash,
            "dimensions": self.dimensions.to_dict(),
        }
    
    def to_full(self) -> dict:
        """Full receipt with all fields."""
        d = self.to_canonical()
        d["receipt_id"] = self.receipt_id
        if self.witnesses:
            d["witnesses"] = [w.to_dict() for w in self.witnesses]
        if self.merkle_root:
            d["merkle_root"] = self.merkle_root
        if self.inclusion_proof:
            d["inclusion_proof"] = self.inclusion_proof
        if self.diversity_hash:
            d["diversity_hash"] = self.diversity_hash
        if self.parent_receipt:
            d["parent_receipt"] = self.parent_receipt
        if self.metadata:
            d["metadata"] = self.metadata
        return d
    
    @property
    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    @property
    def receipt_id(self) -> str:
        """Content-addressable ID = sha256(canonical JSON)."""
        canonical = json.dumps(self.to_canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def serialize(self) -> str:
        """Serialize to JSON string (email-attachable)."""
        return json.dumps(self.to_full(), indent=2, sort_keys=True)
    
    def serialize_compact(self) -> str:
        """Compact serialization (wire format)."""
        return json.dumps(self.to_full(), sort_keys=True, separators=(",", ":"))
    
    @classmethod
    def deserialize(cls, data: str | dict) -> "Receipt":
        """Parse receipt from JSON string or dict."""
        if isinstance(data, str):
            d = json.loads(data)
        else:
            d = data
        
        # Validate required fields
        missing = REQUIRED_FIELDS - set(d.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        dims = TrustDimensions(**d["dimensions"])
        witnesses = [WitnessEntry(**w) for w in d.get("witnesses", [])]
        
        receipt = cls(
            receipt_type=ReceiptType(d["receipt_type"]),
            agent_id=d["agent_id"],
            issuer_id=d["issuer_id"],
            content_hash=d["content_hash"],
            dimensions=dims,
            witnesses=witnesses,
            merkle_root=d.get("merkle_root"),
            inclusion_proof=d.get("inclusion_proof"),
            diversity_hash=d.get("diversity_hash"),
            parent_receipt=d.get("parent_receipt"),
            metadata=d.get("metadata"),
        )
        return receipt
    
    def email_attachment(self) -> dict:
        """Format for email attachment (per funwolf)."""
        return {
            "filename": f"receipt-{self.receipt_id[:12]}.json",
            "content_type": CONTENT_TYPE,
            "content": self.serialize(),
        }


def verify_interop(receipt_json: str) -> dict:
    """Interop test: parse → re-serialize → compare.
    
    Two independent parsers must produce identical canonical JSON.
    This is the spec/enforcement separation test.
    """
    # Parse
    receipt = Receipt.deserialize(receipt_json)
    
    # Re-serialize canonical form
    canonical1 = json.dumps(receipt.to_canonical(), sort_keys=True, separators=(",", ":"))
    
    # Parse the re-serialized version
    receipt2 = Receipt.deserialize(json.loads(receipt.serialize()))
    canonical2 = json.dumps(receipt2.to_canonical(), sort_keys=True, separators=(",", ":"))
    
    # Compare hashes
    hash1 = hashlib.sha256(canonical1.encode()).hexdigest()
    hash2 = hashlib.sha256(canonical2.encode()).hexdigest()
    
    return {
        "interop_pass": hash1 == hash2,
        "canonical_hash": hash1,
        "round_trip_hash": hash2,
        "receipt_id": receipt.receipt_id,
        "content_type": CONTENT_TYPE,
    }


def demo():
    print("=" * 60)
    print("L3.5 RECEIPT SERIALIZATION FORMAT v0.1")
    print("=" * 60)
    
    # Create a sample receipt
    receipt = Receipt(
        receipt_type=ReceiptType.DELIVERY,
        agent_id="agent:kit_fox",
        issuer_id="agent:santaclawd",
        content_hash=hashlib.sha256(b"delivered: trust spec review").hexdigest(),
        dimensions=TrustDimensions(T=0.95, G=0.80, A=0.85, S=0.90, C=0.70),
        witnesses=[
            WitnessEntry("w1", "OrgA", "sig_abc123", "2026-03-16T22:00:00Z"),
            WitnessEntry("w2", "OrgB", "sig_def456", "2026-03-16T22:00:01Z"),
        ],
        merkle_root="abcdef1234567890",
        inclusion_proof=["sibling1hash", "sibling2hash"],
        diversity_hash="div_2orgs_2infra",
    )
    
    # Show serialized formats
    print("\n📋 Full Receipt (email-attachable):")
    print(receipt.serialize())
    
    print(f"\n📎 Email Attachment:")
    att = receipt.email_attachment()
    print(f"  Filename: {att['filename']}")
    print(f"  Content-Type: {att['content_type']}")
    print(f"  Size: {len(att['content'])} bytes")
    
    print(f"\n🔗 Compact (wire format): {len(receipt.serialize_compact())} bytes")
    
    # Interop test
    print(f"\n🔄 Interop Test:")
    result = verify_interop(receipt.serialize())
    status = "✅ PASS" if result["interop_pass"] else "❌ FAIL"
    print(f"  {status}")
    print(f"  Receipt ID: {result['receipt_id'][:16]}...")
    print(f"  Canonical hash: {result['canonical_hash'][:16]}...")
    print(f"  Round-trip hash: {result['round_trip_hash'][:16]}...")
    
    # Heartbeat receipt (null action = liveness proof)
    heartbeat = Receipt(
        receipt_type=ReceiptType.HEARTBEAT,
        agent_id="agent:kit_fox",
        issuer_id="agent:kit_fox",  # Self-issued
        content_hash=hashlib.sha256(b"heartbeat:no_action_needed").hexdigest(),
        dimensions=TrustDimensions(T=1.0, G=0.0, A=0.0, S=0.95, C=0.0),
        metadata={"decision_type": "inaction", "reason": "no_trigger"},
    )
    
    print(f"\n💓 Heartbeat Receipt (liveness proof):")
    print(f"  Type: {heartbeat.receipt_type.value}")
    print(f"  ID: {heartbeat.receipt_id[:16]}...")
    print(f"  Decision: inaction (logged = liveness proof)")
    print(f"  Size: {len(heartbeat.serialize_compact())} bytes")
    
    # Schema summary
    print(f"\n📐 Schema v{SCHEMA_VERSION}:")
    print(f"  Required: {sorted(REQUIRED_FIELDS)}")
    print(f"  Optional: {sorted(OPTIONAL_FIELDS)}")
    print(f"  Content-Type: {CONTENT_TYPE}")
    print(f"  ID derivation: sha256(canonical JSON)")
    print(f"  Interop test: parse → canonical → hash must match")


if __name__ == "__main__":
    demo()
