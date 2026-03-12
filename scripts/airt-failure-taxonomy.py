#!/usr/bin/env python3
"""AIRT Failure Taxonomy — Microsoft's agentic AI failure modes mapped to detection.

Based on Microsoft AI Red Team (2025) "Taxonomy of Failure Mode in Agentic AI Systems."
Key insight: silent failures (scope drift, memory poisoning, cascading delegation) are
agent-specific and compound without detection. Loud failures (crash, error) are generic.

Maps each failure mode to: detection method, circuit breaker trigger, receipt evidence.

Kit 🦊 — 2026-02-28
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NoiseLevel(Enum):
    LOUD = "loud"      # Generates immediate signal (crash, error, exception)
    QUIET = "quiet"    # Generates delayed signal (log, metric drift)
    SILENT = "silent"  # No signal until chain is broken


@dataclass
class FailureMode:
    name: str
    category: str  # novel_security, novel_safety, existing_security, existing_safety
    noise: NoiseLevel
    severity: Severity
    description: str
    detection: str
    receipt_evidence: str
    circuit_breaker_trigger: Optional[str] = None


# Microsoft AIRT taxonomy mapped to detection primitives
TAXONOMY = [
    # Novel security failure modes (agent-specific)
    FailureMode(
        "memory_poisoning", "novel_security", NoiseLevel.SILENT, Severity.CRITICAL,
        "Adversary injects malicious content into agent memory/context",
        "Hash chain verification on memory writes; content integrity checks",
        "memory_write receipt with content_hash + source attestation",
        "memory_hash mismatch on read-back"
    ),
    FailureMode(
        "cascading_delegation", "novel_security", NoiseLevel.SILENT, Severity.CRITICAL,
        "Multi-agent delegation amplifies scope beyond original grant",
        "Scope monotonicity check: child scope ⊆ parent scope at each hop",
        "delegation_receipt with parent_scope_hash + child_scope_hash",
        "scope expansion detected (child > parent)"
    ),
    FailureMode(
        "identity_spoofing", "novel_security", NoiseLevel.QUIET, Severity.HIGH,
        "Agent impersonates another agent in multi-agent system",
        "DKIM/signature verification on inter-agent messages",
        "signed_message receipt with agent_id + signature",
        "signature verification failure"
    ),
    FailureMode(
        "tool_misuse", "novel_security", NoiseLevel.QUIET, Severity.HIGH,
        "Agent uses tools outside intended scope",
        "Scope enforcement: tool call vs granted capabilities",
        "tool_call receipt with scope_hash + capability_check",
        "tool call outside granted scope"
    ),
    FailureMode(
        "silent_scope_drift", "novel_security", NoiseLevel.SILENT, Severity.HIGH,
        "Agent gradually expands its operating scope without triggering alerts",
        "CUSUM on scope_hash changes over time; baseline comparison",
        "periodic scope_audit receipt with drift_metric",
        "cumulative drift exceeds threshold"
    ),

    # Novel safety failure modes
    FailureMode(
        "goal_drift", "novel_safety", NoiseLevel.SILENT, Severity.HIGH,
        "Agent's effective goal diverges from specified objective",
        "Goal alignment check: compare action patterns to objective spec",
        "goal_alignment receipt with objective_hash + action_summary",
        "action pattern diverges from objective baseline"
    ),
    FailureMode(
        "uncontrolled_autonomy", "novel_safety", NoiseLevel.QUIET, Severity.CRITICAL,
        "Agent takes consequential actions without human approval",
        "Approval gate on high-risk actions; escalation receipts",
        "approval_receipt with human_id + action_hash + timestamp",
        "high-risk action without approval receipt"
    ),
    FailureMode(
        "feedback_loop", "novel_safety", NoiseLevel.SILENT, Severity.MEDIUM,
        "Agent's outputs feed back into inputs creating amplification",
        "Cycle detection in action graph; dampening checks",
        "action_graph receipt with cycle_detected flag",
        "action references own prior output as input"
    ),

    # Existing but amplified in agentic context
    FailureMode(
        "prompt_injection", "existing_security", NoiseLevel.LOUD, Severity.HIGH,
        "Malicious input hijacks agent behavior",
        "Input sanitization + output monitoring",
        "input_receipt with sanitization_hash",
        "output diverges from expected pattern post-input"
    ),
    FailureMode(
        "data_exfiltration", "existing_security", NoiseLevel.SILENT, Severity.CRITICAL,
        "Agent leaks sensitive data through tool calls",
        "Output filtering; DLP on tool call payloads",
        "tool_output receipt with data_classification",
        "sensitive data in outbound payload"
    ),
    FailureMode(
        "hallucination_propagation", "existing_safety", NoiseLevel.SILENT, Severity.HIGH,
        "Hallucinated output fed to downstream agents as fact",
        "Source attestation on inter-agent data; confidence scoring",
        "data_transfer receipt with source_type + confidence",
        "low-confidence data passed without flagging"
    ),
]


def analyze_agent(agent_config: dict) -> dict:
    """Score an agent's exposure to AIRT failure modes."""
    has_memory = agent_config.get("has_memory", False)
    has_delegation = agent_config.get("has_delegation", False)
    has_tools = agent_config.get("has_tools", False)
    has_receipts = agent_config.get("has_receipts", False)
    has_scope_enforcement = agent_config.get("has_scope_enforcement", False)

    exposed = []
    mitigated = []
    
    for fm in TAXONOMY:
        applicable = True
        if "memory" in fm.name and not has_memory:
            applicable = False
        if "delegation" in fm.name and not has_delegation:
            applicable = False
        if "tool" in fm.name and not has_tools:
            applicable = False

        if not applicable:
            continue

        is_mitigated = False
        if has_receipts and fm.noise == NoiseLevel.SILENT:
            is_mitigated = True  # Receipts turn silent → quiet
        if has_scope_enforcement and "scope" in fm.name:
            is_mitigated = True

        if is_mitigated:
            mitigated.append(fm)
        else:
            exposed.append(fm)

    # Score
    total = len(exposed) + len(mitigated)
    if total == 0:
        return {"score": 1.0, "grade": "A", "exposed": [], "mitigated": []}

    severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    exposed_risk = sum(severity_weights[f.severity.value] for f in exposed)
    total_risk = sum(severity_weights[f.severity.value] for f in exposed + mitigated)
    
    score = 1 - (exposed_risk / total_risk) if total_risk > 0 else 1.0
    
    if score >= 0.8: grade = "A"
    elif score >= 0.6: grade = "B"
    elif score >= 0.4: grade = "C"
    elif score >= 0.2: grade = "D"
    else: grade = "F"

    # Count by noise level
    silent_exposed = [f for f in exposed if f.noise == NoiseLevel.SILENT]
    
    return {
        "score": round(score, 3),
        "grade": grade,
        "total_applicable": total,
        "exposed_count": len(exposed),
        "mitigated_count": len(mitigated),
        "silent_exposed": len(silent_exposed),
        "exposed": [{"name": f.name, "severity": f.severity.value, "noise": f.noise.value} for f in exposed],
        "mitigated": [{"name": f.name, "detection": f.detection} for f in mitigated],
        "key_insight": f"{'⚠️ ' + str(len(silent_exposed)) + ' SILENT failures undetected' if silent_exposed else '✅ All silent failures covered'}"
    }


def demo():
    print("=== Microsoft AIRT Failure Taxonomy for Agents ===\n")
    
    # Taxonomy overview
    print("Failure modes by noise level:")
    for noise in NoiseLevel:
        modes = [f for f in TAXONOMY if f.noise == noise]
        emoji = {"loud": "📢", "quiet": "🔇", "silent": "🔕"}
        print(f"  {emoji[noise.value]} {noise.value.upper()}: {len(modes)} modes")
        for f in modes:
            print(f"     - {f.name} ({f.severity.value})")
    
    print("\n--- Agent Scoring ---\n")
    
    configs = {
        "Kit (full receipts)": {
            "has_memory": True, "has_delegation": True, "has_tools": True,
            "has_receipts": True, "has_scope_enforcement": True
        },
        "Generic chatbot (no protections)": {
            "has_memory": True, "has_delegation": True, "has_tools": True,
            "has_receipts": False, "has_scope_enforcement": False
        },
        "Minimal agent (tools only)": {
            "has_memory": False, "has_delegation": False, "has_tools": True,
            "has_receipts": False, "has_scope_enforcement": False
        },
    }
    
    for name, config in configs.items():
        result = analyze_agent(config)
        print(f"📊 {name}: {result['grade']} ({result['score']})")
        print(f"   Applicable: {result['total_applicable']}, Exposed: {result['exposed_count']}, Mitigated: {result['mitigated_count']}")
        print(f"   {result['key_insight']}")
        if result['exposed']:
            print(f"   Exposed: {', '.join(f['name'] for f in result['exposed'][:3])}{'...' if len(result['exposed']) > 3 else ''}")
        print()

    print("Key: Silent failures compound without detection.")
    print("     Receipts turn SILENT → QUIET (detectable with effort).")
    print("     Scope enforcement prevents drift-class failures entirely.")


if __name__ == "__main__":
    demo()
