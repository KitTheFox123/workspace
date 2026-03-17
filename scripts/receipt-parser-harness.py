#!/usr/bin/env python3
"""
receipt-parser-harness.py — Universal test harness for L3.5 receipt parsers.

Any implementation (Kit's, funwolf's, future third-party) plugs into this harness.
Runs against shared test vectors. Reports pass/fail per vector.
Two parsers producing identical results on all vectors = interop proven.

Per santaclawd (2026-03-17): "10 happy-path + 20 adversarial is the right split.
Both parsers, identical yes/no on all 30 = ship."

Usage:
    python3 receipt-parser-harness.py                    # run reference parser
    python3 receipt-parser-harness.py --export vectors   # export test vectors as JSON
    python3 receipt-parser-harness.py --compare file.json # compare against another parser's results
"""

import json
import hashlib
import sys
import argparse
from dataclasses import dataclass
from typing import Optional


# ============================================================
# TEST VECTORS — shared across all implementations
# ============================================================

VECTORS = [
    # --- HAPPY PATH (10) ---
    {
        "id": "HP-001", "name": "minimal_valid",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:alice",
            "task_hash": "sha256:aabb", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:00:00Z",
            "timeliness": 0.9, "groundedness": 0.8, "attestation": 0.7,
            "self_knowledge": 0.6, "consistency": 0.85,
            "merkle_root": "sha256:deadbeef",
            "merkle_proof": ["sha256:left1"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.9},
                {"agent_id": "w2", "operator_id": "org:b", "score": 0.8},
            ]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-002", "name": "refusal_receipt",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:bob",
            "task_hash": "sha256:ccdd", "decision_type": "refusal",
            "timestamp": "2026-03-17T04:01:00Z",
            "timeliness": 0.0, "groundedness": 0.0, "attestation": 0.95,
            "self_knowledge": 0.9, "consistency": 0.88,
            "merkle_root": "sha256:beef0001",
            "merkle_proof": ["sha256:r1"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.95},
                {"agent_id": "w3", "operator_id": "org:c", "score": 0.92},
            ]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-003", "name": "liveness_proof",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:charlie",
            "task_hash": "sha256:0000", "decision_type": "liveness",
            "timestamp": "2026-03-17T04:02:00Z",
            "timeliness": 1.0, "groundedness": 0.0, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:live0001",
            "merkle_proof": [],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 1.0},
            ]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-004", "name": "slash_receipt",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:dave",
            "task_hash": "sha256:eeff", "decision_type": "slash",
            "timestamp": "2026-03-17T04:03:00Z",
            "timeliness": 0.1, "groundedness": 0.1, "attestation": 0.99,
            "self_knowledge": 0.2, "consistency": 0.1,
            "merkle_root": "sha256:slash001",
            "merkle_proof": ["sha256:s1", "sha256:s2"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.1},
                {"agent_id": "w2", "operator_id": "org:b", "score": 0.15},
                {"agent_id": "w3", "operator_id": "org:c", "score": 0.1},
            ]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-005", "name": "scar_reference",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:eve",
            "task_hash": "sha256:1122", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:04:00Z",
            "timeliness": 0.7, "groundedness": 0.75, "attestation": 0.8,
            "self_knowledge": 0.65, "consistency": 0.7,
            "merkle_root": "sha256:scar0001",
            "merkle_proof": ["sha256:sc1"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.7},
                {"agent_id": "w2", "operator_id": "org:b", "score": 0.75},
            ],
            "scar_reference": "sha256:slash001"
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-006", "name": "three_witnesses_diverse",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:frank",
            "task_hash": "sha256:3344", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:05:00Z",
            "timeliness": 0.95, "groundedness": 0.92, "attestation": 0.98,
            "self_knowledge": 0.88, "consistency": 0.93,
            "merkle_root": "sha256:div30001",
            "merkle_proof": ["sha256:d1", "sha256:d2"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:alpha", "score": 0.95},
                {"agent_id": "w2", "operator_id": "org:beta", "score": 0.92},
                {"agent_id": "w3", "operator_id": "org:gamma", "score": 0.94},
            ]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-007", "name": "boundary_scores_zero",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:grace",
            "task_hash": "sha256:5566", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:06:00Z",
            "timeliness": 0.0, "groundedness": 0.0, "attestation": 0.0,
            "self_knowledge": 0.0, "consistency": 0.0,
            "merkle_root": "sha256:zero0001",
            "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.0}]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-008", "name": "boundary_scores_one",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:heidi",
            "task_hash": "sha256:7788", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:07:00Z",
            "timeliness": 1.0, "groundedness": 1.0, "attestation": 1.0,
            "self_knowledge": 1.0, "consistency": 1.0,
            "merkle_root": "sha256:ones0001",
            "merkle_proof": ["sha256:o1"],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 1.0}]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-009", "name": "dormant_declaration",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:ivan",
            "task_hash": "sha256:0000", "decision_type": "dormant",
            "timestamp": "2026-03-17T04:08:00Z",
            "timeliness": 0.0, "groundedness": 0.0, "attestation": 0.5,
            "self_knowledge": 1.0, "consistency": 0.5,
            "merkle_root": "sha256:dorm0001",
            "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "ACCEPT"
    },
    {
        "id": "HP-010", "name": "extra_fields_ignored",
        "category": "happy_path",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:judy",
            "task_hash": "sha256:99aa", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:09:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:xtra0001",
            "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}],
            "custom_field": "should be ignored",
            "platform_specific": {"foo": "bar"}
        },
        "expected": "ACCEPT"
    },

    # --- ADVERSARIAL (20) ---
    {
        "id": "ADV-001", "name": "missing_version",
        "category": "adversarial",
        "receipt": {
            "agent_id": "agent:x", "task_hash": "sha256:bad1",
            "decision_type": "delivery", "timestamp": "2026-03-17T04:10:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00001", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-002", "name": "missing_agent_id",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "task_hash": "sha256:bad2",
            "decision_type": "delivery", "timestamp": "2026-03-17T04:11:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00002", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-003", "name": "missing_merkle_root",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad3", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:12:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-004", "name": "score_above_one",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad4", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:13:00Z",
            "timeliness": 1.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00004", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-005", "name": "score_negative",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad5", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:14:00Z",
            "timeliness": -0.1, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00005", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-006", "name": "invalid_decision_type",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad6", "decision_type": "bribery",
            "timestamp": "2026-03-17T04:15:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00006", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-007", "name": "empty_witnesses",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad7", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:16:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00007", "merkle_proof": [],
            "witnesses": []
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-008", "name": "sybil_witnesses_same_org",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad8", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:17:00Z",
            "timeliness": 0.9, "groundedness": 0.9, "attestation": 0.9,
            "self_knowledge": 0.9, "consistency": 0.9,
            "merkle_root": "sha256:adv00008", "merkle_proof": [],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:same", "score": 0.95},
                {"agent_id": "w2", "operator_id": "org:same", "score": 0.94},
                {"agent_id": "w3", "operator_id": "org:same", "score": 0.96},
            ]
        },
        "expected": "WARN"  # valid schema, but diversity = 0.33
    },
    {
        "id": "ADV-009", "name": "self_attestation",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad9", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:18:00Z",
            "timeliness": 1.0, "groundedness": 1.0, "attestation": 1.0,
            "self_knowledge": 1.0, "consistency": 1.0,
            "merkle_root": "sha256:adv00009", "merkle_proof": [],
            "witnesses": [
                {"agent_id": "agent:x", "operator_id": "org:x", "score": 1.0},
            ]
        },
        "expected": "WARN"  # self-grading homework
    },
    {
        "id": "ADV-010", "name": "future_timestamp",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:bad10", "decision_type": "delivery",
            "timestamp": "2030-01-01T00:00:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:adv00010", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-011", "name": "empty_string_fields",
        "category": "adversarial",
        "receipt": {
            "version": "", "agent_id": "",
            "task_hash": "", "decision_type": "",
            "timestamp": "",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "", "merkle_proof": [],
            "witnesses": []
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-012", "name": "null_fields",
        "category": "adversarial",
        "receipt": {
            "version": None, "agent_id": None,
            "task_hash": None, "decision_type": None,
            "timestamp": None,
            "timeliness": None, "groundedness": None, "attestation": None,
            "self_knowledge": None, "consistency": None,
            "merkle_root": None, "merkle_proof": None,
            "witnesses": None
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-013", "name": "wrong_types",
        "category": "adversarial",
        "receipt": {
            "version": 1, "agent_id": 42,
            "task_hash": True, "decision_type": [],
            "timestamp": {},
            "timeliness": "high", "groundedness": "medium", "attestation": "low",
            "self_knowledge": "none", "consistency": "yes",
            "merkle_root": 0, "merkle_proof": "not_a_list",
            "witnesses": "not_a_list"
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-014", "name": "giant_witness_list",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:dos1", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:22:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:dos00001", "merkle_proof": [],
            "witnesses": [{"agent_id": f"w{i}", "operator_id": f"org:{i}", "score": 0.5} for i in range(10000)]
        },
        "expected": "WARN"  # valid but suspicious
    },
    {
        "id": "ADV-015", "name": "duplicate_witnesses",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:dup1", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:23:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:dup00001", "merkle_proof": [],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.8},
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.8},
            ]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-016", "name": "missing_timestamp",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:notime", "decision_type": "delivery",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:not00001", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-017", "name": "witness_missing_operator",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x",
            "task_hash": "sha256:noop", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:25:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:nop00001", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "score": 0.5}]
        },
        "expected": "WARN"  # parseable but operator_id recommended
    },
    {
        "id": "ADV-018", "name": "injection_in_agent_id",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:x\"; DROP TABLE receipts; --",
            "task_hash": "sha256:inj1", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:26:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:inj00001", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-019", "name": "unicode_smuggling",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:\u202ex\u202c",
            "task_hash": "sha256:uni1", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:27:00Z",
            "timeliness": 0.5, "groundedness": 0.5, "attestation": 0.5,
            "self_knowledge": 0.5, "consistency": 0.5,
            "merkle_root": "sha256:uni00001", "merkle_proof": [],
            "witnesses": [{"agent_id": "w1", "operator_id": "org:a", "score": 0.5}]
        },
        "expected": "REJECT"
    },
    {
        "id": "ADV-020", "name": "replay_different_task",
        "category": "adversarial",
        "receipt": {
            "version": "0.1.0", "agent_id": "agent:alice",
            "task_hash": "sha256:DIFFERENT_TASK", "decision_type": "delivery",
            "timestamp": "2026-03-17T04:00:00Z",  # same timestamp as HP-001
            "timeliness": 0.9, "groundedness": 0.8, "attestation": 0.7,
            "self_knowledge": 0.6, "consistency": 0.85,
            "merkle_root": "sha256:deadbeef",  # same merkle root as HP-001
            "merkle_proof": ["sha256:left1"],
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:a", "score": 0.9},
                {"agent_id": "w2", "operator_id": "org:b", "score": 0.8},
            ]
        },
        "expected": "WARN"  # same merkle root, different task = replay attempt
    },
]


# ============================================================
# REFERENCE PARSER (Kit's implementation)
# ============================================================

VALID_DECISION_TYPES = {"delivery", "refusal", "liveness", "slash", "dormant"}
DIMENSION_FIELDS = ["timeliness", "groundedness", "attestation", "self_knowledge", "consistency"]
REQUIRED_STRING_FIELDS = ["version", "agent_id", "task_hash", "decision_type", "timestamp", "merkle_root"]
DANGEROUS_PATTERNS = ['";', "DROP", "--", "\u202e", "\u202c", "\u200b", "\u200d"]


def reference_parse(receipt: dict) -> dict:
    """Reference parser. Returns {verdict: ACCEPT|REJECT|WARN, reasons: [...]}."""
    reasons = []
    
    # Type checks
    if not isinstance(receipt, dict):
        return {"verdict": "REJECT", "reasons": ["not_a_dict"]}
    
    # Required string fields
    for f in REQUIRED_STRING_FIELDS:
        val = receipt.get(f)
        if val is None or not isinstance(val, str) or val.strip() == "":
            reasons.append(f"missing_or_invalid: {f}")
    
    if reasons:
        return {"verdict": "REJECT", "reasons": reasons}
    
    # Decision type
    if receipt.get("decision_type") not in VALID_DECISION_TYPES:
        reasons.append(f"invalid_decision_type: {receipt.get('decision_type')}")
        return {"verdict": "REJECT", "reasons": reasons}
    
    # Dimension bounds
    for dim in DIMENSION_FIELDS:
        val = receipt.get(dim)
        if val is not None:
            if not isinstance(val, (int, float)):
                reasons.append(f"non_numeric: {dim}")
            elif val < 0.0 or val > 1.0:
                reasons.append(f"out_of_bounds: {dim}={val}")
    
    if reasons:
        return {"verdict": "REJECT", "reasons": reasons}
    
    # Timestamp validation (basic: not future)
    ts = receipt.get("timestamp", "")
    if ts > "2027":
        reasons.append(f"future_timestamp: {ts}")
        return {"verdict": "REJECT", "reasons": reasons}
    
    # Witnesses
    witnesses = receipt.get("witnesses")
    if witnesses is None or not isinstance(witnesses, list):
        return {"verdict": "REJECT", "reasons": ["witnesses_not_list"]}
    if len(witnesses) == 0:
        return {"verdict": "REJECT", "reasons": ["no_witnesses"]}
    
    # Injection / smuggling detection
    agent_id = receipt.get("agent_id", "")
    for pattern in DANGEROUS_PATTERNS:
        if pattern in agent_id:
            return {"verdict": "REJECT", "reasons": [f"dangerous_pattern: {pattern}"]}
    
    # Duplicate witnesses
    witness_ids = [w.get("agent_id") for w in witnesses if isinstance(w, dict)]
    if len(witness_ids) != len(set(witness_ids)):
        return {"verdict": "REJECT", "reasons": ["duplicate_witnesses"]}
    
    # --- WARN-level checks ---
    warn_reasons = []
    
    # Self-attestation
    if any(isinstance(w, dict) and w.get("agent_id") == agent_id for w in witnesses):
        warn_reasons.append("self_attestation")
    
    # Sybil (same org)
    orgs = [w.get("operator_id") for w in witnesses if isinstance(w, dict) and w.get("operator_id")]
    if len(orgs) > 1 and len(set(orgs)) == 1:
        warn_reasons.append(f"single_org_witnesses: {orgs[0]}")
    
    # Giant witness list
    if len(witnesses) > 100:
        warn_reasons.append(f"excessive_witnesses: {len(witnesses)}")
    
    # Missing operator_id
    if any(isinstance(w, dict) and not w.get("operator_id") for w in witnesses):
        warn_reasons.append("witness_missing_operator_id")
    
    # Replay detection (merkle_root + different task_hash — needs context)
    # Mark for consumer-side check
    
    if warn_reasons:
        return {"verdict": "WARN", "reasons": warn_reasons}
    
    return {"verdict": "ACCEPT", "reasons": []}


def run_harness(parser_fn=None):
    """Run all vectors through a parser. Returns results dict."""
    if parser_fn is None:
        parser_fn = reference_parse
    
    results = []
    pass_count = 0
    
    for v in VECTORS:
        result = parser_fn(v["receipt"])
        expected = v["expected"]
        actual = result["verdict"]
        match = actual == expected
        if match:
            pass_count += 1
        
        results.append({
            "id": v["id"],
            "name": v["name"],
            "category": v["category"],
            "expected": expected,
            "actual": actual,
            "match": match,
            "reasons": result["reasons"],
        })
    
    return {
        "total": len(VECTORS),
        "passed": pass_count,
        "failed": len(VECTORS) - pass_count,
        "pass_rate": round(pass_count / len(VECTORS) * 100, 1),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="L3.5 receipt parser test harness")
    parser.add_argument("--export", choices=["vectors", "results"], help="Export as JSON")
    parser.add_argument("--compare", help="Compare against another parser's results JSON")
    args = parser.parse_args()
    
    if args.export == "vectors":
        export = [{"id": v["id"], "name": v["name"], "category": v["category"],
                    "receipt": v["receipt"], "expected": v["expected"]} for v in VECTORS]
        print(json.dumps(export, indent=2))
        return
    
    report = run_harness()
    
    if args.export == "results":
        print(json.dumps(report, indent=2))
        return
    
    if args.compare:
        with open(args.compare) as f:
            other = json.load(f)
        other_map = {r["id"]: r["actual"] for r in other.get("results", other)}
        print(f"INTEROP COMPARISON: Reference vs {args.compare}")
        print("=" * 60)
        agree = disagree = 0
        for r in report["results"]:
            other_verdict = other_map.get(r["id"], "MISSING")
            match = r["actual"] == other_verdict
            if match:
                agree += 1
            else:
                disagree += 1
                print(f"  DISAGREE {r['id']}: ref={r['actual']} other={other_verdict}")
        print(f"\nAgreed: {agree}/{len(report['results'])}")
        print(f"Disagreed: {disagree}")
        print(f"Interop: {'PASS' if disagree == 0 else 'FAIL'}")
        return
    
    # Default: run and report
    print(f"L3.5 RECEIPT PARSER TEST HARNESS")
    print(f"{'=' * 60}")
    print(f"Vectors: {report['total']} (10 happy-path + 20 adversarial)")
    print(f"Pass rate: {report['pass_rate']}% ({report['passed']}/{report['total']})")
    print()
    
    for r in report["results"]:
        icon = "✓" if r["match"] else "✗"
        print(f"  {icon} {r['id']:8} {r['name']:30} expected={r['expected']:6} got={r['actual']:6}", end="")
        if not r["match"]:
            print(f"  ← MISMATCH", end="")
        print()
    
    if report["failed"] > 0:
        print(f"\n⚠️  {report['failed']} mismatches — these are spec ambiguities to resolve.")
    else:
        print(f"\n✓ All vectors pass. Ready for second parser.")
    
    print(f"\nExport vectors: python3 {sys.argv[0]} --export vectors > vectors.json")
    print(f"Export results: python3 {sys.argv[0]} --export results > kit-results.json")
    print(f"Compare:        python3 {sys.argv[0]} --compare funwolf-results.json")


if __name__ == "__main__":
    main()
