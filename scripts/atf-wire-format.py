#!/usr/bin/env python3
"""atf-wire-format.py — ATF v0.1 wire format specification generator.

Per santaclawd email (Mar 22): "Where does the spec live? Would like to
read the full wire format when you have a clean draft."

Generates the canonical ATF wire format as JSON Schema + example payloads.
The spec IS the test suite — each schema is also a validator.

Wire format: JSON over HTTPS or SMTP (X-ATF-* headers).
Discovery: DNS-SD (_atf._tcp) → /.well-known/atf.json

References:
- RFC 8259 (JSON)
- RFC 6763 (DNS-SD)
- RFC 8615 (Well-Known URIs)
- RFC 8485 (Vectors of Trust)
"""

import json
import hashlib
from datetime import datetime, timezone


ATF_VERSION = "0.1.0"


def canonical_hash(obj: dict) -> str:
    """Deterministic JSON hash for ATF objects."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


# ── Layer 0: Discovery ──────────────────────────────────────

DISCOVERY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ATF Discovery Record",
    "description": "/.well-known/atf.json — Layer 0 bootstrap",
    "type": "object",
    "required": ["atf_version", "agent_id", "genesis_hash", "endpoints"],
    "properties": {
        "atf_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "agent_id": {"type": "string", "minLength": 1},
        "genesis_hash": {"type": "string", "pattern": r"^sha256:[0-9a-f]+$"},
        "endpoints": {
            "type": "object",
            "required": ["receipts", "genesis"],
            "properties": {
                "receipts": {"type": "string", "format": "uri"},
                "genesis": {"type": "string", "format": "uri"},
                "attestations": {"type": "string", "format": "uri"},
            },
        },
        "transport": {
            "type": "array",
            "items": {"enum": ["https", "smtp", "mcp"]},
            "minItems": 1,
        },
    },
}

DISCOVERY_EXAMPLE = {
    "atf_version": ATF_VERSION,
    "agent_id": "kit_fox",
    "genesis_hash": "sha256:7f83b1657ff1fc53",
    "endpoints": {
        "receipts": "https://agent.example/atf/receipts",
        "genesis": "https://agent.example/atf/genesis",
        "attestations": "https://agent.example/atf/attestations",
    },
    "transport": ["https", "smtp"],
}


# ── Layer 1: Genesis Record ──────────────────────────────────

GENESIS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ATF Genesis Record",
    "description": "Layer 1 — founding declaration, immutable after creation",
    "type": "object",
    "required": [
        "atf_version", "agent_id", "operator_id", "model_family",
        "created_at", "genesis_hash", "scoring_criteria", "update_policy",
    ],
    "properties": {
        "atf_version": {"type": "string"},
        "agent_id": {"type": "string"},
        "operator_id": {"type": "string"},
        "model_family": {"type": "string"},
        "parameter_count": {"type": "string"},
        "quantization": {"type": "string"},
        "created_at": {"type": "string", "format": "date-time"},
        "genesis_hash": {"type": "string"},
        "scoring_criteria": {
            "type": "object",
            "required": ["weights", "criteria_hash"],
            "properties": {
                "weights": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "criteria_hash": {"type": "string"},
            },
        },
        "update_policy": {
            "type": "object",
            "required": ["model_swap", "weight_update"],
            "properties": {
                "model_swap": {"enum": ["REVOUCH", "DUAL_SIGN", "PROHIBITED"]},
                "weight_update": {"enum": ["DRIFT_CHECK", "RE_DECLARE", "PROHIBITED"]},
                "max_migration_window_hours": {"type": "integer", "minimum": 1, "maximum": 168},
            },
        },
        "declared_thresholds": {
            "type": "object",
            "properties": {
                "js_divergence": {"type": "number", "minimum": 0.25},
                "min_independent_counterparties": {"type": "integer", "minimum": 3},
                "correction_frequency_range": {
                    "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                },
            },
        },
    },
}

GENESIS_EXAMPLE = {
    "atf_version": ATF_VERSION,
    "agent_id": "kit_fox",
    "operator_id": "ilya",
    "model_family": "anthropic/claude",
    "parameter_count": "unknown",
    "quantization": "none",
    "created_at": "2026-01-30T00:00:00Z",
    "genesis_hash": "sha256:7f83b1657ff1fc53",
    "scoring_criteria": {
        "weights": {
            "continuity": 0.25,
            "independence": 0.25,
            "receipts": 0.25,
            "corrections": 0.25,
        },
        "criteria_hash": "sha256:abc123def456",
    },
    "update_policy": {
        "model_swap": "DUAL_SIGN",
        "weight_update": "DRIFT_CHECK",
        "max_migration_window_hours": 24,
    },
    "declared_thresholds": {
        "js_divergence": 0.30,
        "min_independent_counterparties": 3,
        "correction_frequency_range": [0.05, 0.40],
    },
}


# ── Layer 2: Receipt ─────────────────────────────────────────

RECEIPT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ATF Receipt",
    "description": "Layer 2 — per-interaction evidence record",
    "type": "object",
    "required": [
        "receipt_id", "task_hash", "agent_id", "counterparty_id",
        "evidence_grade", "created_at", "predecessor_hash",
    ],
    "properties": {
        "receipt_id": {"type": "string"},
        "task_hash": {"type": "string"},
        "agent_id": {"type": "string"},
        "counterparty_id": {"type": "string"},
        "evidence_grade": {"enum": ["A", "B", "C", "D", "F"]},
        "created_at": {"type": "string", "format": "date-time"},
        "predecessor_hash": {"type": "string", "description": "Hash chain link"},
        "grader_id": {"type": "string", "description": "13th MUST field"},
        "failure_hash": {"type": ["string", "null"], "description": "null if success"},
        "delivery_receipt": {"type": "boolean"},
        "acceptance_receipt": {"type": "boolean"},
        "signatures": {
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "counterparty": {"type": "string"},
                "witness": {"type": "string"},
            },
        },
    },
}

RECEIPT_EXAMPLE = {
    "receipt_id": "r_20260322_001",
    "task_hash": "sha256:task_content_hash",
    "agent_id": "kit_fox",
    "counterparty_id": "bro_agent",
    "evidence_grade": "A",
    "created_at": "2026-03-22T17:30:00Z",
    "predecessor_hash": "sha256:previous_receipt",
    "grader_id": "bro_agent",
    "failure_hash": None,
    "delivery_receipt": True,
    "acceptance_receipt": True,
    "signatures": {
        "agent": "ed25519:kit_fox_sig",
        "counterparty": "ed25519:bro_agent_sig",
    },
}


# ── Layer 3: Attestation ─────────────────────────────────────

ATTESTATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ATF Attestation",
    "description": "Layer 3 — third-party trust assessment",
    "type": "object",
    "required": [
        "attestation_id", "subject_id", "attester_id", "grade",
        "confidence_interval", "created_at", "evidence_count",
    ],
    "properties": {
        "attestation_id": {"type": "string"},
        "subject_id": {"type": "string"},
        "attester_id": {"type": "string"},
        "grade": {"enum": ["A", "B", "C", "D", "F"]},
        "confidence_interval": {
            "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
        },
        "created_at": {"type": "string", "format": "date-time"},
        "evidence_count": {"type": "integer", "minimum": 0},
        "principal_split": {
            "type": "object",
            "properties": {
                "agent_grade": {"enum": ["A", "B", "C", "D", "F"]},
                "operator_grade": {"enum": ["A", "B", "C", "D", "F"]},
            },
        },
        "attester_independence": {
            "type": "object",
            "properties": {
                "shared_operator": {"type": "boolean"},
                "shared_model_family": {"type": "boolean"},
                "shared_ca_root": {"type": "boolean"},
                "simpson_diversity": {"type": "number"},
            },
        },
    },
}


# ── SMTP Headers ─────────────────────────────────────────────

SMTP_HEADERS = {
    "X-ATF-Version": ATF_VERSION,
    "X-ATF-Agent-ID": "kit_fox",
    "X-ATF-Genesis-Hash": "sha256:7f83b1657ff1fc53",
    "X-ATF-Soul-Hash": "sha256:soul_content_hash",
    "X-ATF-Receipt-Chain": "sha256:latest_receipt_hash",
    "X-ATF-Evidence-Grade": "A",
}


def generate_spec():
    spec = {
        "atf_version": ATF_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": {
            "L0_discovery": {
                "schema": DISCOVERY_SCHEMA,
                "example": DISCOVERY_EXAMPLE,
                "transport": "DNS-SD (_atf._tcp) → /.well-known/atf.json",
            },
            "L1_genesis": {
                "schema": GENESIS_SCHEMA,
                "example": GENESIS_EXAMPLE,
                "note": "Immutable after creation. Hash-pinned scoring criteria.",
            },
            "L2_receipt": {
                "schema": RECEIPT_SCHEMA,
                "example": RECEIPT_EXAMPLE,
                "note": "Hash-chained. grader_id = 13th MUST. failure_hash for non-repudiation.",
            },
            "L3_attestation": {
                "schema": ATTESTATION_SCHEMA,
                "note": "Principal split (agent vs operator). Independence audit.",
            },
        },
        "smtp_headers": SMTP_HEADERS,
        "invariants": [
            "genesis_hash is immutable after creation",
            "receipt chain is append-only (predecessor_hash links)",
            "grader_id MUST differ from agent_id (no self-grading)",
            "failure_hash requires 2-of-3 independent signers for CONFIRMED",
            "scoring criteria weights MUST sum to 1.0",
            "max_migration_window <= 24 hours (dual-sign)",
            "js_divergence threshold >= 0.25 (ATF floor)",
            "min_independent_counterparties >= 3 (BFT bound)",
        ],
        "spec_hash": None,  # filled below
    }

    # Self-referential: spec hashes itself
    spec["spec_hash"] = canonical_hash({k: v for k, v in spec.items() if k != "spec_hash"})

    return spec


if __name__ == "__main__":
    spec = generate_spec()
    print(json.dumps(spec, indent=2, default=str))
    print(f"\nSpec hash: {spec['spec_hash']}")
    print(f"Layers: {len(spec['layers'])}")
    print(f"Invariants: {len(spec['invariants'])}")
    print(f"SMTP headers: {len(spec['smtp_headers'])}")
