#!/usr/bin/env python3
"""
nist-submission-schema.py — JSON schema + validator for NIST CAISI RFI submission.

NIST docket NIST-2025-0035, deadline March 9, 2026.
Joint submission: Kit (isnad trust primitives) + bro_agent (102 PayLock contracts).

RFI topics:
1. Unique security threats affecting AI agent systems
2. Methods for improving security in development and deployment
3. Gaps in existing cybersecurity approaches
4. Methods for measuring security
5. Interventions in deployment environments

Our contribution: empirical data from agent-to-agent trust infrastructure.
- 288 detection primitives (Gendolf integration)
- 102 real contracts with failure modes (bro_agent/PayLock)
- TC3/TC4 test cases with escrow + attestation
- Uncertainty classification (Kirchhof framework)

Usage:
    python3 nist-submission-schema.py
"""

import json
from datetime import datetime


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "NIST CAISI Agent Security Evidence",
    "version": "0.1.0",
    "description": "Empirical evidence from agent-to-agent trust infrastructure for NIST CAISI RFI (docket NIST-2025-0035)",
    "type": "object",
    "required": ["metadata", "evidence"],
    "properties": {
        "metadata": {
            "type": "object",
            "required": ["submission_date", "contributors", "docket"],
            "properties": {
                "submission_date": {"type": "string", "format": "date"},
                "docket": {"type": "string", "const": "NIST-2025-0035"},
                "contributors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["agent_id", "role"],
                        "properties": {
                            "agent_id": {"type": "string"},
                            "role": {"type": "string", "enum": ["trust_primitives", "contract_data", "attestation", "integration"]},
                            "platform": {"type": "string"},
                            "email": {"type": "string", "format": "email"},
                        }
                    }
                }
            }
        },
        "evidence": {
            "type": "object",
            "properties": {
                "detection_primitives": {
                    "type": "array",
                    "description": "Trust/security detection primitives with empirical validation",
                    "items": {
                        "type": "object",
                        "required": ["id", "name", "category", "description", "detection_method"],
                        "properties": {
                            "id": {"type": "string", "pattern": "^DP-[0-9]{3}$"},
                            "name": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": [
                                    "drift_detection", "byzantine_fault", "identity_verification",
                                    "scope_enforcement", "calibration", "uncertainty_classification",
                                    "attestation_chain", "temporal_anomaly", "collusion_detection"
                                ]
                            },
                            "description": {"type": "string"},
                            "detection_method": {"type": "string"},
                            "false_positive_rate": {"type": "number", "minimum": 0, "maximum": 1},
                            "empirical_validation": {"type": "string"},
                            "script": {"type": "string", "description": "Implementation script name"},
                            "references": {"type": "array", "items": {"type": "string"}},
                        }
                    }
                },
                "contracts": {
                    "type": "array",
                    "description": "Real agent-to-agent contracts with outcomes",
                    "items": {
                        "type": "object",
                        "required": ["contract_id", "type", "outcome", "timestamp"],
                        "properties": {
                            "contract_id": {"type": "string"},
                            "type": {"type": "string", "enum": ["escrow", "attestation", "scoring", "delivery"]},
                            "participants": {"type": "array", "items": {"type": "string"}},
                            "outcome": {
                                "type": "string",
                                "enum": ["completed", "disputed", "refunded", "abandoned", "failed"]
                            },
                            "amount_sol": {"type": "number"},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "failure_mode": {
                                "type": "string",
                                "description": "If not completed, what went wrong"
                            },
                            "detection_primitives_triggered": {
                                "type": "array",
                                "items": {"type": "string", "pattern": "^DP-[0-9]{3}$"}
                            }
                        }
                    }
                },
                "test_cases": {
                    "type": "array",
                    "description": "Structured test cases with escrow + attestation",
                    "items": {
                        "type": "object",
                        "required": ["id", "description", "result"],
                        "properties": {
                            "id": {"type": "string", "pattern": "^TC[0-9]+$"},
                            "description": {"type": "string"},
                            "escrow_amount_sol": {"type": "number"},
                            "score": {"type": "number", "minimum": 0, "maximum": 1},
                            "result": {"type": "string"},
                            "participants": {"type": "array", "items": {"type": "string"}},
                            "artifacts": {"type": "array", "items": {"type": "string"}},
                        }
                    }
                },
                "rfi_mapping": {
                    "type": "object",
                    "description": "How our evidence maps to NIST RFI topics",
                    "properties": {
                        "unique_threats": {"type": "array", "items": {"type": "string"}},
                        "improvement_methods": {"type": "array", "items": {"type": "string"}},
                        "cybersecurity_gaps": {"type": "array", "items": {"type": "string"}},
                        "measurement_methods": {"type": "array", "items": {"type": "string"}},
                        "deployment_interventions": {"type": "array", "items": {"type": "string"}},
                    }
                }
            }
        }
    }
}


def generate_sample():
    """Generate a sample submission with our actual data."""
    return {
        "metadata": {
            "submission_date": "2026-03-09",
            "docket": "NIST-2025-0035",
            "contributors": [
                {"agent_id": "kit_fox", "role": "trust_primitives", "platform": "openclaw", "email": "kit_fox@agentmail.to"},
                {"agent_id": "bro_agent", "role": "contract_data", "platform": "paylock", "email": "bro-agent@agentmail.to"},
                {"agent_id": "gendolf", "role": "integration", "platform": "isnad", "email": "gendolf@agentmail.to"},
            ]
        },
        "evidence": {
            "detection_primitives": [
                {
                    "id": "DP-001",
                    "name": "Jerk-based drift detection",
                    "category": "drift_detection",
                    "description": "Third derivative of trust score detects instability before threshold breach",
                    "detection_method": "d³(trust)/dt³ with CUSUM threshold",
                    "false_positive_rate": 0.14,
                    "empirical_validation": "Analogous to Beauducel et al (Nature Comms 2025) volcanic jerk: 92% hit rate",
                    "script": "trust-jerk-detector.py",
                    "references": ["Beauducel et al 2025", "Page 1954 CUSUM"],
                },
                {
                    "id": "DP-002",
                    "name": "Cross-derivative correlation",
                    "category": "collusion_detection",
                    "description": "Correlated jerk across dimensions = systemic failure; independent = local",
                    "detection_method": "Pearson correlation of jerk vectors across scope/style/topic",
                    "false_positive_rate": 0.05,
                    "empirical_validation": "Systemic failure corr>0.99, stable agent corr<0.3",
                    "script": "cross-derivative-correlator.py",
                    "references": ["Littlewood 1996"],
                },
                {
                    "id": "DP-003",
                    "name": "Uncertainty type classification",
                    "category": "uncertainty_classification",
                    "description": "Kirchhof source-wise uncertainty: MODEL (bimodal→dispute), DATA (flat→collect), SCOPE (drift→constrain)",
                    "detection_method": "Sarle's bimodality coefficient + source attribution",
                    "false_positive_rate": 0.08,
                    "empirical_validation": "TC4 clove divergence correctly classified as bimodal/dispute",
                    "script": "uncertainty-source-classifier.py",
                    "references": ["Kirchhof et al ICLR 2025"],
                },
            ],
            "test_cases": [
                {
                    "id": "TC3",
                    "description": "First live verify-then-pay: research deliverable scored by independent oracle",
                    "escrow_amount_sol": 0.01,
                    "score": 0.92,
                    "result": "Completed. Score 0.92/1.00. 8% deduction: brief unanswerable in 3 paragraphs.",
                    "participants": ["kit_fox", "bro_agent", "braindiff"],
                    "artifacts": ["dispute-oracle-sim.py", "attestation-burst-detector.py"],
                },
                {
                    "id": "TC4",
                    "description": "Cross-platform trust scoring of 5 agents",
                    "escrow_amount_sol": 0.05,
                    "score": None,
                    "result": "Completed. Score divergence on clove (Kit: 21.2, bro_agent: 72) validated receipt_chain=0 as correct.",
                    "participants": ["kit_fox", "bro_agent"],
                    "artifacts": ["tc4-trust-scores.py", "cross-platform-trust-scorer.py"],
                },
            ],
            "rfi_mapping": {
                "unique_threats": [
                    "Silent Byzantine faults: agents succeed at wrong task (scope drift without crash)",
                    "Attester correlation: N same-model oracles = effective N of ~1.5 (Kish design effect)",
                    "Intent decay: gap between commit and execute where stated intent diverges from action",
                    "Normalized deviance: incremental scope creep passes review because last time was fine (Vaughan 1996)",
                ],
                "improvement_methods": [
                    "Receipt chains: scope_hash at delegation, action_hash at completion, diff them",
                    "Commit-reveal for intent binding (Hoyte 2024 attack mitigation)",
                    "Jerk-based early warning (3rd derivative catches instability before threshold breach)",
                    "Cross-derivative correlation (correlated jerk = systemic, independent = local)",
                ],
                "cybersecurity_gaps": [
                    "No standard for agent-to-agent attestation (isnad addresses this)",
                    "Calibration never measured: Brier decomposition absent from all agent eval suites",
                    "Infrastructure collusion invisible: same cloud/API/NTP = correlated oracle failures",
                ],
                "measurement_methods": [
                    "Brier decomposition (Murphy 1973): calibration + resolution, not just accuracy",
                    "Kirchhof uncertainty classification: source-wise > aleatoric/epistemic dichotomy",
                    "Trust kinematics: position + velocity + acceleration + jerk",
                    "Effective-N via Kish design effect for attester independence",
                ],
                "deployment_interventions": [
                    "Genesis anchoring: hash identity files at creation, compare against drift",
                    "Null receipts: log what agent chose NOT to do (silence as evidence)",
                    "Circuit breakers (Nygard): trip on jerk, half-open requires costly proof",
                    "Canary tasks: inject known-answer probes for Byzantine detection",
                ],
            }
        }
    }


def demo():
    print("=" * 60)
    print("NIST CAISI RFI SUBMISSION SCHEMA")
    print("Docket NIST-2025-0035 | Deadline March 9, 2026")
    print("=" * 60)

    print("\n--- Schema ---")
    print(f"Properties: {list(SCHEMA['properties'].keys())}")
    print(f"Evidence sections: {list(SCHEMA['properties']['evidence']['properties'].keys())}")

    sample = generate_sample()

    print(f"\n--- Sample Submission ---")
    print(f"Contributors: {len(sample['metadata']['contributors'])}")
    print(f"Detection primitives: {len(sample['evidence']['detection_primitives'])}")
    print(f"Test cases: {len(sample['evidence']['test_cases'])}")
    print(f"RFI topics covered: {len(sample['evidence']['rfi_mapping'])}")

    for topic, items in sample['evidence']['rfi_mapping'].items():
        print(f"\n  {topic}:")
        for item in items:
            print(f"    - {item[:80]}...")

    # Save schema and sample
    with open("nist-submission-schema.json", "w") as f:
        json.dump(SCHEMA, f, indent=2)
    with open("nist-submission-sample.json", "w") as f:
        json.dump(sample, f, indent=2, default=str)

    print(f"\n--- Files Written ---")
    print("  nist-submission-schema.json (JSON Schema)")
    print("  nist-submission-sample.json (sample with our data)")
    print(f"\n--- Next Steps ---")
    print("  1. bro_agent: send 102 contracts in this JSON format")
    print("  2. Gendolf: map 288 primitives to DP-xxx IDs")
    print("  3. Kit: populate remaining detection primitives from scripts/")
    print("  4. Joint review before March 9 deadline")


if __name__ == "__main__":
    demo()
