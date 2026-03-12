#!/usr/bin/env python3
"""SOC2 Audit Checker — validate agent provenance logs against SOC2 Type II criteria.

SOC2 Type II = prove controls existed OVER TIME, not at a point.
Receipt chains = continuous SOC2 for agents.

Maps SOC2 Trust Service Criteria to agent provenance:
  CC6.1 (Logical Access) → identity/auth receipts
  CC7.1 (System Operations) → action logs with hash chains
  CC7.2 (Change Management) → null nodes (what changed and what didn't)
  CC8.1 (Monitoring) → CUSUM/drift detection logs

Usage:
  python soc2-audit-checker.py --demo
  python soc2-audit-checker.py --log <provenance.jsonl>
"""

import json
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter


# SOC2 Trust Service Criteria mapped to agent provenance
CRITERIA = {
    "CC6.1": {
        "name": "Logical Access Controls",
        "description": "Entity restricts logical access to information assets",
        "agent_mapping": "Identity receipts (DKIM, signatures, auth tokens)",
        "evidence_types": ["auth", "dkim", "signature", "login", "delegation"],
    },
    "CC7.1": {
        "name": "System Operations",
        "description": "Entity manages system operations to detect and mitigate deviations",
        "agent_mapping": "Hash-chained action logs (provenance-logger)",
        "evidence_types": ["action", "clawk_reply", "email_send", "build", "attestation"],
    },
    "CC7.2": {
        "name": "Change Management",
        "description": "Entity manages changes to infrastructure and software",
        "agent_mapping": "Null nodes (considered but declined actions)",
        "evidence_types": ["null:*", "config_change", "model_update", "memory_edit"],
    },
    "CC8.1": {
        "name": "Monitoring Activities",
        "description": "Entity monitors components for anomalies",
        "agent_mapping": "CUSUM drift detection, SPRT governance decisions",
        "evidence_types": ["heartbeat", "drift_check", "sprt_decision", "cusum_alarm"],
    },
    "CC9.1": {
        "name": "Risk Mitigation",
        "description": "Entity identifies and mitigates risks",
        "agent_mapping": "Attestation diversity scoring, sybil detection",
        "evidence_types": ["risk_assessment", "sybil_check", "proof_class_score"],
    },
}


def load_provenance(path: str) -> list:
    """Load JSONL provenance log."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def verify_chain_integrity(entries: list) -> dict:
    """Verify hash chain integrity."""
    total = len(entries)
    breaks = 0
    prev_hash = None
    
    for i, e in enumerate(entries):
        if prev_hash and e.get("prev_hash") != prev_hash:
            breaks += 1
        prev_hash = e.get("hash")
    
    return {
        "total_entries": total,
        "chain_breaks": breaks,
        "integrity": round((total - breaks) / max(1, total), 3),
        "status": "PASS" if breaks == 0 else "FAIL",
    }


def check_criteria(entries: list, audit_window_days: int = 30) -> dict:
    """Check provenance log against SOC2 criteria."""
    results = {}
    
    for cc_id, criteria in CRITERIA.items():
        # Find matching entries
        matching = []
        for e in entries:
            action = e.get("action", "")
            for ev_type in criteria["evidence_types"]:
                if ev_type.endswith("*"):
                    if action.startswith(ev_type[:-1]):
                        matching.append(e)
                        break
                elif action == ev_type:
                    matching.append(e)
                    break
        
        # Assess coverage
        coverage = len(matching) / max(1, len(entries))
        
        # Check temporal distribution (SOC2 Type II = over time)
        if matching:
            timestamps = []
            for m in matching:
                ts = m.get("timestamp", "")
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except (ValueError, AttributeError):
                    pass
            
            if len(timestamps) >= 2:
                span = (max(timestamps) - min(timestamps)).total_seconds() / 3600
                regularity = min(1.0, span / (audit_window_days * 24))
            else:
                regularity = 0.1
        else:
            regularity = 0.0
        
        # Grade
        score = coverage * 0.4 + regularity * 0.6
        grade = "PASS" if score > 0.3 else "PARTIAL" if score > 0.1 else "FAIL"
        
        results[cc_id] = {
            "name": criteria["name"],
            "evidence_count": len(matching),
            "coverage": round(coverage, 3),
            "temporal_regularity": round(regularity, 3),
            "score": round(score, 3),
            "grade": grade,
        }
    
    return results


def generate_report(entries: list) -> dict:
    """Generate full SOC2 audit report."""
    chain = verify_chain_integrity(entries)
    criteria = check_criteria(entries)
    
    # Null node analysis
    null_count = sum(1 for e in entries if e.get("null_node") or e.get("action", "").startswith("null:"))
    null_ratio = null_count / max(1, len(entries))
    
    # Overall score
    criteria_scores = [c["score"] for c in criteria.values()]
    avg_score = sum(criteria_scores) / len(criteria_scores) if criteria_scores else 0
    
    passed = sum(1 for c in criteria.values() if c["grade"] == "PASS")
    total_criteria = len(criteria)
    
    overall = "COMPLIANT" if passed == total_criteria and chain["status"] == "PASS" else \
              "PARTIAL" if passed >= total_criteria * 0.6 else "NON-COMPLIANT"
    
    return {
        "audit_date": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(entries),
        "chain_integrity": chain,
        "null_node_ratio": round(null_ratio, 3),
        "criteria": criteria,
        "summary": {
            "overall_status": overall,
            "criteria_passed": f"{passed}/{total_criteria}",
            "average_score": round(avg_score, 3),
            "chain_valid": chain["status"] == "PASS",
        },
        "recommendations": generate_recs(criteria, chain, null_ratio),
    }


def generate_recs(criteria, chain, null_ratio):
    recs = []
    if chain["status"] == "FAIL":
        recs.append(f"CRITICAL: {chain['chain_breaks']} hash chain breaks. Investigate tampering.")
    for cc_id, c in criteria.items():
        if c["grade"] == "FAIL":
            recs.append(f"{cc_id} ({c['name']}): No evidence. Add {CRITERIA[cc_id]['agent_mapping']}.")
    if null_ratio < 0.05:
        recs.append("LOW NULL NODES: Record declined actions for complete audit trail.")
    if not recs:
        recs.append("Audit trail healthy. Continue logging.")
    return recs


def demo():
    """Demo with provenance log if available, else synthetic."""
    print("=" * 60)
    print("SOC2 Type II Audit Checker for Agent Provenance")
    print("=" * 60)
    
    log_path = Path(__file__).parent.parent / "memory" / "provenance.jsonl"
    
    if log_path.exists():
        print(f"\nUsing real provenance log: {log_path}")
        entries = load_provenance(str(log_path))
    else:
        print("\nUsing synthetic demo data")
        now = datetime.now(timezone.utc)
        entries = []
        prev_hash = None
        for i in range(20):
            e = {
                "timestamp": (now - timedelta(hours=i*3)).isoformat(),
                "action": ["clawk_reply", "heartbeat", "null:moltbook_post", "build", "attestation"][i % 5],
            }
            if prev_hash:
                e["prev_hash"] = prev_hash
            if e["action"].startswith("null:"):
                e["null_node"] = True
            raw = json.dumps(e, sort_keys=True).encode()
            e["hash"] = hashlib.sha256(raw).hexdigest()[:16]
            prev_hash = e["hash"]
            entries.append(e)
    
    report = generate_report(entries)
    
    print(f"\nEntries: {report['total_entries']}")
    print(f"Chain integrity: {report['chain_integrity']['status']} ({report['chain_integrity']['integrity']})")
    print(f"Null node ratio: {report['null_node_ratio']}")
    print(f"\nCriteria:")
    for cc_id, c in report['criteria'].items():
        print(f"  {cc_id} {c['name']:30s} {c['grade']:7s} ({c['evidence_count']} evidence, score={c['score']})")
    print(f"\nOverall: {report['summary']['overall_status']} ({report['summary']['criteria_passed']} criteria passed)")
    for rec in report['recommendations']:
        print(f"  → {rec}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        log_path = sys.argv[sys.argv.index("--json") + 1] if len(sys.argv) > sys.argv.index("--json") + 1 else None
        if log_path:
            entries = load_provenance(log_path)
        else:
            entries = [json.loads(line) for line in sys.stdin if line.strip()]
        print(json.dumps(generate_report(entries), indent=2))
    elif "--log" in sys.argv:
        log_path = sys.argv[sys.argv.index("--log") + 1]
        entries = load_provenance(log_path)
        report = generate_report(entries)
        print(json.dumps(report, indent=2))
    else:
        demo()
