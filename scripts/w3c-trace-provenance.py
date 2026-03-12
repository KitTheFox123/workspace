#!/usr/bin/env python3
"""W3C Trace Context → Agent Provenance Mapper

Maps agent attestation chains to W3C Trace Context format (traceparent + tracestate).
santaclawd's insight: extend existing W3C REC instead of inventing new spec.

traceparent: version-trace_id-parent_id-flags
tracestate: agentprov=delegation_id:scope_hash:attester_sig

Every major APM/OTEL tool already parses these headers. Zero new infrastructure.

Usage:
  python w3c-trace-provenance.py --demo
  echo '{"chain": [...]}' | python w3c-trace-provenance.py --json
"""

import json
import sys
import hashlib
import uuid
import time
from datetime import datetime


def generate_trace_id():
    """W3C trace-id: 16 bytes hex."""
    return uuid.uuid4().hex


def generate_span_id():
    """W3C parent-id/span-id: 8 bytes hex."""
    return uuid.uuid4().hex[:16]


def scope_hash(scope: str) -> str:
    """Hash scope description to 8-char hex."""
    return hashlib.sha256(scope.encode()).hexdigest()[:8]


def build_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Build W3C traceparent header."""
    version = "00"
    flags = "01" if sampled else "00"
    return f"{version}-{trace_id}-{span_id}-{flags}"


def build_tracestate(delegation_id: str, scope: str, attester_sig: str,
                     extra: dict = None) -> str:
    """Build tracestate with agentprov key.
    
    Format: agentprov=delegation_id:scope_hash:attester_sig
    Additional vendor keys preserved.
    """
    sh = scope_hash(scope)
    sig_short = attester_sig[:16] if len(attester_sig) > 16 else attester_sig
    agentprov = f"agentprov={delegation_id}:{sh}:{sig_short}"
    
    parts = [agentprov]
    if extra:
        for k, v in extra.items():
            parts.append(f"{k}={v}")
    
    return ",".join(parts)


def parse_traceparent(header: str) -> dict:
    """Parse W3C traceparent header."""
    parts = header.split("-")
    if len(parts) != 4:
        return {"error": "invalid traceparent"}
    return {
        "version": parts[0],
        "trace_id": parts[1],
        "parent_id": parts[2],
        "flags": parts[3],
        "sampled": parts[3] == "01",
    }


def parse_tracestate(header: str) -> dict:
    """Parse tracestate, extract agentprov."""
    result = {"raw": header, "vendors": {}}
    for pair in header.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k == "agentprov":
                prov_parts = v.split(":")
                result["agentprov"] = {
                    "delegation_id": prov_parts[0] if len(prov_parts) > 0 else None,
                    "scope_hash": prov_parts[1] if len(prov_parts) > 1 else None,
                    "attester_sig": prov_parts[2] if len(prov_parts) > 2 else None,
                }
            else:
                result["vendors"][k] = v
    return result


def chain_to_traces(chain: list) -> list:
    """Convert attestation chain to W3C trace headers."""
    trace_id = generate_trace_id()
    traces = []
    parent_id = None
    
    for i, link in enumerate(chain):
        span_id = generate_span_id()
        
        traceparent = build_traceparent(trace_id, span_id)
        tracestate = build_tracestate(
            delegation_id=link.get("delegation_id", f"del_{i}"),
            scope=link.get("scope", "default"),
            attester_sig=link.get("attester_sig", "unsigned"),
            extra=link.get("vendor_state", {}),
        )
        
        trace = {
            "step": i,
            "agent": link.get("agent", f"agent_{i}"),
            "action": link.get("action", "unknown"),
            "traceparent": traceparent,
            "tracestate": tracestate,
            "parent_span": parent_id,
            "timestamp": link.get("timestamp", datetime.utcnow().isoformat()),
        }
        traces.append(trace)
        parent_id = span_id
    
    return {
        "trace_id": trace_id,
        "span_count": len(traces),
        "spans": traces,
        "otel_compatible": True,
        "note": "Export to any OTEL collector via traceparent + tracestate headers",
    }


def validate_chain(traces: dict) -> dict:
    """Validate provenance chain integrity."""
    issues = []
    spans = traces.get("spans", [])
    
    for i, span in enumerate(spans):
        # Parse and validate
        tp = parse_traceparent(span["traceparent"])
        ts = parse_tracestate(span["tracestate"])
        
        if "error" in tp:
            issues.append(f"Step {i}: invalid traceparent")
        
        if "agentprov" not in ts:
            issues.append(f"Step {i}: missing agentprov in tracestate")
        elif ts["agentprov"]["attester_sig"] == "unsigned":
            issues.append(f"Step {i}: unsigned attestation (grade 3)")
        
        # Check parent chain
        if i > 0 and span["parent_span"] is None:
            issues.append(f"Step {i}: broken parent chain")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "chain_length": len(spans),
        "signed_count": sum(1 for s in spans 
                          if parse_tracestate(s["tracestate"]).get("agentprov", {}).get("attester_sig", "unsigned") != "unsigned"),
    }


def demo():
    print("=" * 60)
    print("W3C Trace Context → Agent Provenance")
    print("=" * 60)
    
    # TC3-style chain
    tc3_chain = [
        {
            "agent": "bro_agent",
            "action": "contract_create",
            "delegation_id": "tc3_brief",
            "scope": "research:trust_economy:7500chars",
            "attester_sig": "ed25519_bro_abc123",
        },
        {
            "agent": "kit_fox",
            "action": "deliverable_submit",
            "delegation_id": "tc3_delivery",
            "scope": "research:trust_economy:7500chars",
            "attester_sig": "ed25519_kit_def456",
            "vendor_state": {"paylock": "0.01SOL:confirmed"},
        },
        {
            "agent": "bro_agent",
            "action": "score_attestation",
            "delegation_id": "tc3_score",
            "scope": "quality:0.92",
            "attester_sig": "ed25519_bro_ghi789",
        },
        {
            "agent": "braindiff",
            "action": "witness_attestation",
            "delegation_id": "tc3_witness",
            "scope": "attestation:diversity_check",
            "attester_sig": "ed25519_braindiff_jkl012",
        },
    ]
    
    print("\n--- TC3 as W3C Trace Context ---")
    result = chain_to_traces(tc3_chain)
    print(f"Trace ID: {result['trace_id']}")
    print(f"Spans: {result['span_count']}")
    print(f"OTEL compatible: {result['otel_compatible']}")
    
    for span in result["spans"]:
        print(f"\n  Step {span['step']}: {span['agent']} → {span['action']}")
        print(f"    traceparent: {span['traceparent']}")
        print(f"    tracestate:  {span['tracestate']}")
    
    # Validate
    print("\n--- Validation ---")
    validation = validate_chain(result)
    print(f"Valid: {validation['valid']}")
    print(f"Signed: {validation['signed_count']}/{validation['chain_length']}")
    if validation['issues']:
        for issue in validation['issues']:
            print(f"  ⚠️ {issue}")
    
    # Parse example
    print("\n--- Parse Example ---")
    sample_tp = result["spans"][1]["traceparent"]
    sample_ts = result["spans"][1]["tracestate"]
    print(f"traceparent: {sample_tp}")
    print(f"  → {parse_traceparent(sample_tp)}")
    print(f"tracestate: {sample_ts}")
    print(f"  → {parse_tracestate(sample_ts)}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = chain_to_traces(data.get("chain", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
