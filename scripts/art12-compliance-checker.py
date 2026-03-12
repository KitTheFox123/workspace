#!/usr/bin/env python3
"""EU AI Act Article 12 Compliance Checker for agent governance stacks.

Art. 12 requires high-risk AI systems to have "automatic recording of events"
(logging) enabling traceability throughout the system's lifetime.

This tool audits a provenance log against Art. 12 requirements and scores
compliance. Null nodes (actions considered but not taken) go BEYOND Art. 12.

Based on:
- EU AI Act Art. 12 (Record-keeping), Art. 72 (Post-market monitoring)
- santaclawd: "null logs = what Art. 12 didn't know to ask for"
- provenance-logger.py JSONL format

Usage:
  python art12-compliance-checker.py --demo
  python art12-compliance-checker.py --audit memory/provenance.jsonl
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


# Art. 12 requirements mapped to provenance log features
ART12_REQUIREMENTS = {
    "12.1_automatic_recording": {
        "description": "Automatic recording of events throughout lifetime",
        "check": "entries_exist",
        "weight": 1.0,
    },
    "12.2a_period_of_use": {
        "description": "Recording covers the period of each use",
        "check": "temporal_coverage",
        "weight": 0.8,
    },
    "12.2b_input_data": {
        "description": "Input data reference or description",
        "check": "has_targets_or_context",
        "weight": 0.6,
    },
    "12.2c_identification": {
        "description": "Identification of natural persons involved in verification",
        "check": "has_attesters",
        "weight": 0.5,
    },
    "12.3_traceability": {
        "description": "Logging enables traceability of AI functioning",
        "check": "chain_integrity",
        "weight": 1.0,
    },
    "beyond_null_nodes": {
        "description": "BEYOND Art. 12: Records of actions considered but not taken",
        "check": "has_null_nodes",
        "weight": 0.3,  # Bonus, not required
    },
}


def audit_log(log_path: str) -> dict:
    """Audit a provenance JSONL log against Art. 12."""
    path = Path(log_path)
    if not path.exists():
        return {"error": f"Log file not found: {log_path}"}
    
    entries = []
    parse_errors = 0
    for line in path.open():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            parse_errors += 1
    
    if not entries:
        return {"error": "Empty log", "parse_errors": parse_errors}
    
    results = {}
    
    # 12.1: Entries exist
    results["12.1_automatic_recording"] = {
        "status": "PASS" if len(entries) > 0 else "FAIL",
        "detail": f"{len(entries)} entries logged",
        "score": 1.0 if entries else 0.0,
    }
    
    # 12.2a: Temporal coverage
    timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    if len(timestamps) >= 2:
        try:
            first = timestamps[0][:19]
            last = timestamps[-1][:19]
            results["12.2a_period_of_use"] = {
                "status": "PASS",
                "detail": f"Covers {first} to {last}",
                "score": 1.0,
            }
        except Exception:
            results["12.2a_period_of_use"] = {"status": "PARTIAL", "detail": "Timestamps present but unparseable", "score": 0.5}
    else:
        results["12.2a_period_of_use"] = {"status": "FAIL", "detail": "Insufficient timestamps", "score": 0.0}
    
    # 12.2b: Input data references
    with_targets = sum(1 for e in entries if e.get("target") or e.get("reason"))
    target_pct = with_targets / len(entries) if entries else 0
    results["12.2b_input_data"] = {
        "status": "PASS" if target_pct > 0.7 else "PARTIAL" if target_pct > 0.3 else "FAIL",
        "detail": f"{with_targets}/{len(entries)} entries have target/reason ({target_pct:.0%})",
        "score": min(1.0, target_pct / 0.7),
    }
    
    # 12.2c: Identification of verifiers
    with_attesters = sum(1 for e in entries if e.get("attester") or e.get("platform"))
    attester_pct = with_attesters / len(entries) if entries else 0
    results["12.2c_identification"] = {
        "status": "PASS" if attester_pct > 0.5 else "PARTIAL" if attester_pct > 0.1 else "FAIL",
        "detail": f"{with_attesters}/{len(entries)} entries have attester/platform info",
        "score": min(1.0, attester_pct / 0.5),
    }
    
    # 12.3: Chain integrity (hash chain)
    chain_ok = 0
    chain_break = 0
    prev_hash = None
    for e in entries:
        if prev_hash is None:
            chain_ok += 1
        elif e.get("prev_hash") == prev_hash:
            chain_ok += 1
        else:
            chain_break += 1
        prev_hash = e.get("hash")
    
    integrity = chain_ok / len(entries) if entries else 0
    results["12.3_traceability"] = {
        "status": "PASS" if integrity > 0.95 else "PARTIAL" if integrity > 0.5 else "FAIL",
        "detail": f"Chain integrity: {chain_ok}/{len(entries)} ({integrity:.0%}), {chain_break} breaks",
        "score": integrity,
    }
    
    # Beyond Art. 12: Null nodes
    null_nodes = sum(1 for e in entries if e.get("null_node") or (e.get("action", "").startswith("null:")))
    null_pct = null_nodes / len(entries) if entries else 0
    results["beyond_null_nodes"] = {
        "status": "PRESENT" if null_nodes > 0 else "ABSENT",
        "detail": f"{null_nodes} null nodes ({null_pct:.0%} of entries) — BEYOND Art. 12 requirements",
        "score": 1.0 if null_nodes > 0 else 0.0,
    }
    
    # Composite score
    weighted_sum = 0
    weight_total = 0
    for req_id, req in ART12_REQUIREMENTS.items():
        if req_id in results:
            weighted_sum += results[req_id]["score"] * req["weight"]
            weight_total += req["weight"]
    
    composite = weighted_sum / weight_total if weight_total > 0 else 0
    grade = "A" if composite > 0.85 else "B" if composite > 0.7 else "C" if composite > 0.5 else "D" if composite > 0.3 else "F"
    
    return {
        "log_file": str(log_path),
        "total_entries": len(entries),
        "parse_errors": parse_errors,
        "null_nodes": null_nodes,
        "composite_score": round(composite, 3),
        "grade": grade,
        "requirements": results,
        "summary": f"Art. 12 compliance: {grade} ({composite:.0%}). {null_nodes} null nodes exceed regulatory requirements.",
    }


def demo():
    """Demo with synthetic provenance data."""
    print("=" * 60)
    print("EU AI Act Article 12 Compliance Checker")
    print("=" * 60)
    
    # Check real provenance log if it exists
    real_log = Path(__file__).parent.parent / "memory" / "provenance.jsonl"
    if real_log.exists():
        print(f"\n--- Real Provenance Log: {real_log} ---")
        result = audit_log(str(real_log))
        print(f"Grade: {result['grade']} ({result['composite_score']})")
        print(f"Entries: {result['total_entries']}, Null nodes: {result['null_nodes']}")
        for req_id, r in result['requirements'].items():
            emoji = "✅" if r['status'] == 'PASS' else "⚠️" if r['status'] in ('PARTIAL', 'PRESENT') else "❌"
            print(f"  {emoji} {req_id}: {r['status']} — {r['detail']}")
        print(f"\n{result['summary']}")
    
    # Synthetic: compliant log
    print("\n--- Synthetic: Compliant Governance Stack ---")
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        prev_hash = None
        for i in range(20):
            entry = {
                "timestamp": f"2026-02-27T{i:02d}:00:00Z",
                "action": "null:skip_spam" if i % 5 == 0 else "clawk_reply",
                "target": f"agent_{i % 4}",
                "reason": "thread engagement" if i % 5 != 0 else "low quality, skipped",
                "platform": "clawk",
            }
            if i % 5 == 0:
                entry["null_node"] = True
            if prev_hash:
                entry["prev_hash"] = prev_hash
            canon = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
            entry["hash"] = hashlib.sha256(canon).hexdigest()[:16]
            prev_hash = entry["hash"]
            f.write(json.dumps(entry) + "\n")
        tmp_path = f.name
    
    result = audit_log(tmp_path)
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Entries: {result['total_entries']}, Null nodes: {result['null_nodes']}")
    for req_id, r in result['requirements'].items():
        emoji = "✅" if r['status'] == 'PASS' else "⚠️" if r['status'] in ('PARTIAL', 'PRESENT') else "❌"
        print(f"  {emoji} {req_id}: {r['status']} — {r['detail']}")
    print(f"\n{result['summary']}")
    
    Path(tmp_path).unlink()


if __name__ == "__main__":
    if "--audit" in sys.argv:
        idx = sys.argv.index("--audit")
        if idx + 1 < len(sys.argv):
            result = audit_log(sys.argv[idx + 1])
            print(json.dumps(result, indent=2))
    elif "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = audit_log(data.get("log_path", ""))
        print(json.dumps(result, indent=2))
    else:
        demo()
