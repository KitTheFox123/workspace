#!/usr/bin/env python3
"""Governance Readiness Scorer — assess agent systems against EU AI Act requirements.

Maps EU AI Act Articles 12 (record-keeping), 72 (proportional oversight),
and governance stack requirements to concrete agent capabilities.

School 2 framing (santaclawd): governance > alignment.
Don't fix what the AI thinks. Record what it does.

Usage:
  python governance-readiness-scorer.py --demo
  echo '{"capabilities": {...}}' | python governance-readiness-scorer.py --json
"""

import json
import sys
from dataclasses import dataclass


# EU AI Act requirements mapped to agent capabilities
REQUIREMENTS = {
    "art12_logging": {
        "name": "Art. 12: Automatic Recording",
        "description": "Automatic logging of events throughout lifecycle",
        "weight": 0.20,
        "checks": [
            ("append_only_log", "Append-only event log (tamper-evident)"),
            ("hash_chain", "Hash-chained entries (integrity verification)"),
            ("null_nodes", "Null nodes (recording declined actions)"),
            ("timestamp_source", "Trusted timestamp source"),
        ],
    },
    "art72_proportional": {
        "name": "Art. 72: Proportional Oversight",
        "description": "Oversight proportional to risk level",
        "weight": 0.15,
        "checks": [
            ("risk_classification", "Risk classification per task"),
            ("escalation_rules", "Graduated escalation rules"),
            ("human_in_loop", "Human-in-the-loop for high-risk"),
            ("automated_low_risk", "Automated handling for low-risk"),
        ],
    },
    "drift_detection": {
        "name": "Behavioral Drift Detection",
        "description": "Detecting changes in agent behavior over time",
        "weight": 0.20,
        "checks": [
            ("cusum_or_sprt", "Statistical process control (CUSUM/SPRT)"),
            ("multi_metric", "Multi-metric monitoring (quality, latency, etc.)"),
            ("alarm_threshold", "Configurable alarm thresholds"),
            ("adaptive_baseline", "Adaptive baseline estimation"),
        ],
    },
    "provenance": {
        "name": "Action Provenance",
        "description": "Full audit trail of agent actions and decisions",
        "weight": 0.20,
        "checks": [
            ("action_log", "Every action logged with reason"),
            ("decision_context", "Decision context preserved"),
            ("tool_calls_logged", "External tool calls recorded"),
            ("input_output_hash", "Input/output content hashed"),
        ],
    },
    "attestation": {
        "name": "Independent Attestation",
        "description": "Third-party verification of agent behavior",
        "weight": 0.15,
        "checks": [
            ("proof_diversity", "Multiple proof classes (payment, gen, transport)"),
            ("attester_independence", "Independent attesters (not self-attesting)"),
            ("temporal_diversity", "Temporal diversity across proof types"),
            ("sybil_resistance", "Sybil detection (burst/correlation analysis)"),
        ],
    },
    "fork_detection": {
        "name": "Fork/Identity Protection",
        "description": "Detecting unauthorized forks or impersonation",
        "weight": 0.10,
        "checks": [
            ("quorum_intersection", "Quorum-based fork detection"),
            ("key_rotation", "Secure key rotation (KERI-style)"),
            ("receipt_chain_binding", "Identity bound to receipt chain"),
            ("split_detection", "Split-brain/divergence detection"),
        ],
    },
}


def score_system(capabilities: dict) -> dict:
    """Score an agent system's governance readiness."""
    results = {}
    total_score = 0.0
    
    for req_id, req in REQUIREMENTS.items():
        checks_passed = 0
        check_results = []
        for check_id, check_desc in req["checks"]:
            present = capabilities.get(check_id, False)
            checks_passed += 1 if present else 0
            check_results.append({
                "id": check_id,
                "description": check_desc,
                "present": present,
            })
        
        coverage = checks_passed / len(req["checks"])
        weighted = coverage * req["weight"]
        total_score += weighted
        
        results[req_id] = {
            "name": req["name"],
            "coverage": round(coverage, 3),
            "weighted_score": round(weighted, 3),
            "checks": check_results,
            "grade": "A" if coverage >= 0.75 else "B" if coverage >= 0.50 else "C" if coverage >= 0.25 else "F",
        }
    
    grade = "A" if total_score >= 0.75 else "B" if total_score >= 0.50 else "C" if total_score >= 0.25 else "F"
    
    # Gap analysis
    gaps = []
    for req_id, result in results.items():
        for check in result["checks"]:
            if not check["present"]:
                gaps.append(f"{result['name']}: {check['description']}")
    
    return {
        "total_score": round(total_score, 3),
        "grade": grade,
        "requirements": results,
        "gaps": gaps[:5],
        "gap_count": len(gaps),
        "eu_ai_act_ready": total_score >= 0.60,
    }


def demo():
    print("=" * 60)
    print("Governance Readiness Scorer (EU AI Act + Agent Provenance)")
    print("School 2: Record what it did. Don't fix what it thinks.")
    print("=" * 60)
    
    # Our actual governance stack
    kit_stack = {
        # Art. 12 logging
        "append_only_log": True,       # provenance-logger.py
        "hash_chain": True,            # SHA-256 chain linking
        "null_nodes": True,            # Just added!
        "timestamp_source": True,      # UTC timestamps
        # Art. 72 proportional
        "risk_classification": True,   # governance-classifier.py
        "escalation_rules": False,     # TODO: graduated sanctions
        "human_in_loop": True,         # Ilya reviews
        "automated_low_risk": True,    # Heartbeat automation
        # Drift detection
        "cusum_or_sprt": True,         # cusum-drift-detector.py + wald-sprt-governance.py
        "multi_metric": True,          # quality, latency, diversity, heartbeat
        "alarm_threshold": True,       # Configurable h parameter
        "adaptive_baseline": True,     # IACUSUM adaptive
        # Provenance
        "action_log": True,            # provenance-logger.py
        "decision_context": True,      # reason field
        "tool_calls_logged": True,     # platform field
        "input_output_hash": True,     # hash chain
        # Attestation
        "proof_diversity": True,       # proof-class-scorer.py
        "attester_independence": True,  # witness-independence-scorer.py
        "temporal_diversity": True,    # temporal_class in scorer
        "sybil_resistance": True,      # attestation-burst-detector.py
        # Fork detection
        "quorum_intersection": True,   # fork-fingerprint.py
        "key_rotation": True,          # key-rotation-verifier.py
        "receipt_chain_binding": True,  # hash chain = identity
        "split_detection": True,       # fork-fingerprint.py
    }
    
    print("\n--- Kit's Governance Stack ---")
    result = score_system(kit_stack)
    print(f"Score: {result['total_score']} ({result['grade']})")
    print(f"EU AI Act Ready: {'✅' if result['eu_ai_act_ready'] else '❌'}")
    for req_id, req_result in result["requirements"].items():
        print(f"  {req_result['name']}: {req_result['grade']} ({req_result['coverage']:.0%})")
    if result["gaps"]:
        print(f"Gaps ({result['gap_count']}):")
        for gap in result["gaps"]:
            print(f"  ❌ {gap}")
    
    # Typical agent (no governance)
    print("\n--- Typical Agent (No Governance) ---")
    typical = {
        "human_in_loop": True,  # Most have this
    }
    result = score_system(typical)
    print(f"Score: {result['total_score']} ({result['grade']})")
    print(f"EU AI Act Ready: {'✅' if result['eu_ai_act_ready'] else '❌'}")
    print(f"Gaps: {result['gap_count']}")
    
    # Partial implementation
    print("\n--- Partial Implementation (logging only) ---")
    partial = {
        "append_only_log": True,
        "timestamp_source": True,
        "action_log": True,
        "tool_calls_logged": True,
        "human_in_loop": True,
    }
    result = score_system(partial)
    print(f"Score: {result['total_score']} ({result['grade']})")
    print(f"EU AI Act Ready: {'✅' if result['eu_ai_act_ready'] else '❌'}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_system(data.get("capabilities", {}))
        print(json.dumps(result, indent=2))
    else:
        demo()
