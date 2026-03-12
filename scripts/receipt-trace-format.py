#!/usr/bin/env python3
"""Receipt Trace Format — OpenTelemetry-inspired traces for agent receipts.

santaclawd's insight: "observability > consensus. traces > votes."
Maps distributed tracing concepts to agent attestation.

Span = single attestation event
Trace = full delivery lifecycle (contract → delivery → verification → settlement)
Context propagation = receipt chain linking

Usage:
  python receipt-trace-format.py --demo
  echo '{"spans": [...]}' | python receipt-trace-format.py --json
"""

import json
import sys
import hashlib
import time
from datetime import datetime, timezone


def make_id(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def create_span(name: str, kind: str, attester: str, 
                parent_span_id: str = None, trace_id: str = None,
                attributes: dict = None, proof_class: str = None) -> dict:
    """Create an attestation span (OpenTelemetry-inspired)."""
    now = datetime.now(timezone.utc).isoformat()
    span_id = make_id(f"{name}{attester}{now}{time.monotonic_ns()}")
    
    if trace_id is None:
        trace_id = make_id(f"trace-{now}-{span_id}")
    
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "kind": kind,  # contract, generation, transport, verification, settlement
        "attester": attester,
        "proof_class": proof_class or kind,
        "start_time": now,
        "end_time": None,
        "status": "OK",
        "attributes": attributes or {},
    }


def close_span(span: dict, status: str = "OK", end_attributes: dict = None) -> dict:
    """Close a span with end time and final status."""
    span["end_time"] = datetime.now(timezone.utc).isoformat()
    span["status"] = status
    if end_attributes:
        span["attributes"].update(end_attributes)
    return span


def analyze_trace(spans: list) -> dict:
    """Analyze a full trace for completeness and health."""
    if not spans:
        return {"error": "empty trace"}
    
    trace_id = spans[0].get("trace_id", "unknown")
    
    # Proof class coverage
    proof_classes = set(s.get("proof_class", s.get("kind", "unknown")) for s in spans)
    target_classes = {"payment", "generation", "transport"}
    coverage = len(proof_classes & target_classes) / len(target_classes)
    
    # Attester diversity
    attesters = set(s.get("attester", "unknown") for s in spans)
    
    # Temporal span
    times = []
    for s in spans:
        if s.get("start_time"):
            times.append(s["start_time"])
        if s.get("end_time"):
            times.append(s["end_time"])
    
    # Status check
    failed = [s for s in spans if s.get("status") not in ("OK", None)]
    
    # Chain integrity (parent references)
    span_ids = {s["span_id"] for s in spans}
    broken_refs = [s for s in spans if s.get("parent_span_id") and s["parent_span_id"] not in span_ids]
    
    # Root spans (no parent)
    roots = [s for s in spans if not s.get("parent_span_id")]
    
    grade = "A" if coverage >= 0.9 and len(attesters) >= 3 and not failed and not broken_refs else \
            "B" if coverage >= 0.6 and len(attesters) >= 2 and not failed else \
            "C" if coverage >= 0.3 else "D" if not failed else "F"
    
    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "proof_class_coverage": round(coverage, 3),
        "proof_classes": sorted(proof_classes),
        "attester_count": len(attesters),
        "attesters": sorted(attesters),
        "root_spans": len(roots),
        "failed_spans": len(failed),
        "broken_references": len(broken_refs),
        "grade": grade,
        "diagnosis": generate_diagnosis(coverage, attesters, failed, broken_refs, proof_classes),
    }


def generate_diagnosis(coverage, attesters, failed, broken_refs, proof_classes):
    issues = []
    if coverage < 1.0:
        missing = {"payment", "generation", "transport"} - proof_classes
        issues.append(f"Missing proof classes: {', '.join(missing)}")
    if len(attesters) < 2:
        issues.append("Single attester — no independence")
    if failed:
        issues.append(f"{len(failed)} failed span(s)")
    if broken_refs:
        issues.append(f"{len(broken_refs)} broken parent reference(s) — chain integrity compromised")
    return issues if issues else ["Trace healthy — full coverage, diverse attesters, chain intact"]


def demo():
    print("=" * 60)
    print("Receipt Trace Format (OpenTelemetry for Attestation)")
    print("=" * 60)
    
    # TC3-style delivery trace
    trace_id = make_id("tc3-demo")
    
    root = create_span("contract.create", "contract", "bro_agent",
                       trace_id=trace_id,
                       attributes={"contract_id": "tc3", "amount": "0.01 SOL"})
    
    payment = create_span("payment.escrow", "payment", "paylock",
                         parent_span_id=root["span_id"], trace_id=trace_id,
                         proof_class="payment",
                         attributes={"tx_hash": "abc123", "protocol": "x402"})
    close_span(payment)
    
    generation = create_span("content.generate", "generation", "kit_fox",
                            parent_span_id=root["span_id"], trace_id=trace_id,
                            proof_class="generation",
                            attributes={"content_hash": "sha256:def456", "word_count": 7500})
    close_span(generation)
    
    transport = create_span("email.deliver", "transport", "agentmail",
                           parent_span_id=generation["span_id"], trace_id=trace_id,
                           proof_class="transport",
                           attributes={"dkim": True, "message_id": "<tc3@agentmail.to>"})
    close_span(transport)
    
    verify = create_span("quality.verify", "verification", "bro_agent",
                        parent_span_id=transport["span_id"], trace_id=trace_id,
                        attributes={"score": 0.92, "deductions": "brief unanswerable in 3 paragraphs"})
    close_span(verify)
    
    settle = create_span("payment.release", "settlement", "paylock",
                        parent_span_id=verify["span_id"], trace_id=trace_id,
                        attributes={"released": "0.01 SOL", "to": "kit_fox"})
    close_span(settle)
    close_span(root)
    
    spans = [root, payment, generation, transport, verify, settle]
    
    print("\n--- TC3 Delivery Trace ---")
    for s in spans:
        indent = "  " if s.get("parent_span_id") else ""
        status = s["status"]
        print(f"{indent}[{s['span_id'][:8]}] {s['name']} ({s['attester']}) — {status}")
    
    result = analyze_trace(spans)
    print(f"\nGrade: {result['grade']}")
    print(f"Coverage: {result['proof_class_coverage']:.0%}")
    print(f"Attesters: {result['attester_count']} ({', '.join(result['attesters'])})")
    print(f"Diagnosis: {result['diagnosis'][0]}")
    
    # Sybil trace — single attester, single class
    print("\n--- Sybil Trace (Single Attester) ---")
    sybil_trace = make_id("sybil")
    sybil_spans = [
        close_span(create_span(f"witness.{i}", "witness", "sybil_bot",
                              trace_id=sybil_trace, proof_class="witness",
                              attributes={"score": 1.0}))
        for i in range(5)
    ]
    
    result2 = analyze_trace(sybil_spans)
    print(f"Grade: {result2['grade']}")
    print(f"Coverage: {result2['proof_class_coverage']:.0%}")
    print(f"Attesters: {result2['attester_count']}")
    for d in result2['diagnosis']:
        print(f"  ⚠️ {d}")
    
    # Export format
    print("\n--- Export (JSON) ---")
    export = {
        "trace_id": trace_id,
        "spans": spans[:2],  # Just show first 2 for brevity
        "analysis": result,
    }
    print(json.dumps(export, indent=2, default=str)[:500] + "...")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_trace(data.get("spans", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
