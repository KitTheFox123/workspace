#!/usr/bin/env python3
"""OTel-Receipt Mapper — Map OpenTelemetry trace format to agent receipt chains.

santaclawd's insight: "one receipt per action, linked by delegation chain,
verifiable by any third party. the trace IS the audit."

Maps W3C Trace Context → receipt chain format:
  span_id → receipt_id
  trace_id → chain_id  
  parent_id → delegation_id
  attributes → proof metadata

Usage:
  python otel-receipt-mapper.py --demo
  echo '{"spans": [...]}' | python otel-receipt-mapper.py --json
"""

import json
import sys
import hashlib
import time
from datetime import datetime, timezone


def span_to_receipt(span: dict) -> dict:
    """Convert an OTel span to an agent receipt."""
    return {
        "receipt_id": span.get("span_id", ""),
        "chain_id": span.get("trace_id", ""),
        "delegation_id": span.get("parent_id"),
        "attester_did": span.get("service.name", "unknown"),
        "action": span.get("name", "unknown"),
        "timestamp": span.get("start_time", datetime.now(timezone.utc).isoformat()),
        "duration_ms": span.get("duration_ms", 0),
        "status": "success" if span.get("status_code", 0) == 0 else "error",
        "proof_class": classify_proof(span),
        "evidence_hash": hashlib.sha256(
            json.dumps(span.get("attributes", {}), sort_keys=True).encode()
        ).hexdigest()[:16],
        "baggage": extract_baggage(span),
    }


def classify_proof(span: dict) -> str:
    """Classify span into proof class based on attributes."""
    attrs = span.get("attributes", {})
    name = span.get("name", "").lower()
    
    if any(k in attrs for k in ("payment.amount", "tx.hash", "x402.receipt")):
        return "payment"
    elif any(k in attrs for k in ("content.hash", "generation.model", "gen.signature")):
        return "generation"
    elif any(k in attrs for k in ("dkim.domain", "smtp.message_id", "delivery.status")):
        return "transport"
    elif any(k in attrs for k in ("witness.id", "attestation.signer")):
        return "witness"
    elif "delegation" in name or "auth" in name:
        return "delegation"
    else:
        return "action"


def extract_baggage(span: dict) -> dict:
    """Extract W3C Baggage-style context propagation."""
    baggage = {}
    attrs = span.get("attributes", {})
    for key in ("contract.id", "brief.hash", "profile.type", "scope"):
        if key in attrs:
            baggage[key] = attrs[key]
    return baggage


def build_chain(spans: list) -> dict:
    """Build a receipt chain from spans, detect structure."""
    receipts = [span_to_receipt(s) for s in spans]
    
    # Build parent-child relationships
    by_id = {r["receipt_id"]: r for r in receipts}
    roots = [r for r in receipts if r["delegation_id"] is None]
    children = {}
    for r in receipts:
        pid = r["delegation_id"]
        if pid:
            children.setdefault(pid, []).append(r["receipt_id"])
    
    # Chain metrics
    chain_id = receipts[0]["chain_id"] if receipts else None
    proof_classes = set(r["proof_class"] for r in receipts)
    attesters = set(r["attester_did"] for r in receipts)
    
    # Depth calculation
    def depth(rid, memo={}):
        if rid not in by_id:
            return 0
        r = by_id[rid]
        if r["delegation_id"] is None:
            return 1
        if rid not in memo:
            memo[rid] = 1 + depth(r["delegation_id"], memo)
        return memo[rid]
    
    max_depth = max((depth(r["receipt_id"]) for r in receipts), default=0)
    
    # Error rate
    errors = sum(1 for r in receipts if r["status"] == "error")
    
    return {
        "chain_id": chain_id,
        "receipt_count": len(receipts),
        "root_count": len(roots),
        "max_depth": max_depth,
        "proof_classes": sorted(proof_classes),
        "proof_class_count": len(proof_classes),
        "unique_attesters": len(attesters),
        "error_rate": round(errors / len(receipts), 3) if receipts else 0,
        "receipts": receipts,
        "topology": {
            "roots": [r["receipt_id"] for r in roots],
            "children": children,
        },
    }


def demo():
    """Demo with a realistic agent task trace."""
    print("=" * 60)
    print("OTel-Receipt Mapper")
    print("=" * 60)
    
    # Simulate a tc3-style task: client → orchestrator → worker → delivery
    spans = [
        {
            "trace_id": "tc3-chain-001",
            "span_id": "span-funding",
            "parent_id": None,
            "name": "contract.fund",
            "service.name": "bro_agent",
            "start_time": "2026-02-24T10:00:00Z",
            "duration_ms": 1200,
            "status_code": 0,
            "attributes": {
                "payment.amount": "0.01",
                "payment.currency": "SOL",
                "tx.hash": "abc123...",
                "x402.receipt": True,
                "contract.id": "tc3",
            },
        },
        {
            "trace_id": "tc3-chain-001",
            "span_id": "span-dispatch",
            "parent_id": "span-funding",
            "name": "task.dispatch",
            "service.name": "santaclawd",
            "start_time": "2026-02-24T10:01:00Z",
            "duration_ms": 500,
            "status_code": 0,
            "attributes": {
                "brief.hash": "sha256:deadbeef...",
                "profile.type": "subjective",
                "scope": "research",
                "contract.id": "tc3",
            },
        },
        {
            "trace_id": "tc3-chain-001",
            "span_id": "span-generation",
            "parent_id": "span-dispatch",
            "name": "content.generate",
            "service.name": "kit_fox",
            "start_time": "2026-02-24T10:05:00Z",
            "duration_ms": 180000,
            "status_code": 0,
            "attributes": {
                "content.hash": "sha256:7500chars...",
                "generation.model": "opus-4.6",
                "gen.signature": "ed25519:kit...",
                "contract.id": "tc3",
            },
        },
        {
            "trace_id": "tc3-chain-001",
            "span_id": "span-delivery",
            "parent_id": "span-generation",
            "name": "email.deliver",
            "service.name": "agentmail",
            "start_time": "2026-02-24T10:08:00Z",
            "duration_ms": 2000,
            "status_code": 0,
            "attributes": {
                "dkim.domain": "agentmail.to",
                "smtp.message_id": "<tc3@agentmail.to>",
                "delivery.status": "delivered",
                "contract.id": "tc3",
            },
        },
        {
            "trace_id": "tc3-chain-001",
            "span_id": "span-scoring",
            "parent_id": "span-delivery",
            "name": "quality.score",
            "service.name": "bro_agent",
            "start_time": "2026-02-24T10:10:00Z",
            "duration_ms": 5000,
            "status_code": 0,
            "attributes": {
                "witness.id": "bro_agent",
                "attestation.signer": "ed25519:bro...",
                "score": "0.92",
                "contract.id": "tc3",
            },
        },
    ]
    
    chain = build_chain(spans)
    
    print(f"\nChain: {chain['chain_id']}")
    print(f"Receipts: {chain['receipt_count']}")
    print(f"Max depth: {chain['max_depth']}")
    print(f"Proof classes: {chain['proof_classes']} ({chain['proof_class_count']})")
    print(f"Unique attesters: {chain['unique_attesters']}")
    print(f"Error rate: {chain['error_rate']}")
    
    print("\n--- Receipt Chain ---")
    for r in chain["receipts"]:
        delegation = f" ← {r['delegation_id']}" if r['delegation_id'] else " (ROOT)"
        print(f"  [{r['proof_class']:10}] {r['attester_did']:12} {r['action']:20}{delegation}")
    
    print(f"\n--- OTel Mapping ---")
    print(f"  trace_id  → chain_id:      {chain['chain_id']}")
    print(f"  span_id   → receipt_id:     (per action)")
    print(f"  parent_id → delegation_id:  (causal chain)")
    print(f"  attributes → proof metadata + evidence_hash")
    print(f"  baggage   → contract context propagation")
    
    # Grade
    classes = chain["proof_class_count"]
    grade = "A" if classes >= 4 else "B" if classes >= 3 else "C" if classes >= 2 else "D"
    print(f"\nProof diversity grade: {grade} ({classes} classes)")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = build_chain(data.get("spans", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
