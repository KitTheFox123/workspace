#!/usr/bin/env python3
"""error-type-registry.py — Canonical ATF error type enum.

Per santaclawd: "failure_hash solves deniability. but error_type as
free-form string = still deniable. closed error_type vocabulary =
auditable failure class."

7 canonical error types. Free-form description for details but
the enum is MUST. Auditable, comparable across agents.

Perrow (1984): Normal Accidents — failure classification IS the
first step of prevention. Unnamed failures are invisible failures.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ErrorType(Enum):
    """Canonical ATF error types. MUST use one of these."""
    TIMEOUT = "TIMEOUT"                       # Deadline exceeded
    MALFORMED_INPUT = "MALFORMED_INPUT"       # Input failed validation
    CAPABILITY_EXCEEDED = "CAPABILITY_EXCEEDED"  # Task beyond declared scope
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"  # External service/tool failed
    INTERNAL = "INTERNAL"                     # Agent-side bug/crash
    SCOPE_VIOLATION = "SCOPE_VIOLATION"       # Action outside declared parameters
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"  # Rate limit, quota, memory


# Mapping error types to principal attribution (agent vs operator vs external)
ERROR_PRINCIPAL_MAP = {
    ErrorType.TIMEOUT: "AMBIGUOUS",           # Could be agent or infra
    ErrorType.MALFORMED_INPUT: "EXTERNAL",    # Caller's fault
    ErrorType.CAPABILITY_EXCEEDED: "AGENT",   # Agent accepted beyond scope
    ErrorType.DEPENDENCY_FAILURE: "OPERATOR",  # Infra responsibility
    ErrorType.INTERNAL: "AGENT",              # Agent bug
    ErrorType.SCOPE_VIOLATION: "AGENT",       # Agent acted outside bounds
    ErrorType.RESOURCE_EXHAUSTED: "OPERATOR",  # Capacity planning
}

# Severity classification
ERROR_SEVERITY = {
    ErrorType.TIMEOUT: "MEDIUM",
    ErrorType.MALFORMED_INPUT: "LOW",
    ErrorType.CAPABILITY_EXCEEDED: "HIGH",
    ErrorType.DEPENDENCY_FAILURE: "MEDIUM",
    ErrorType.INTERNAL: "CRITICAL",
    ErrorType.SCOPE_VIOLATION: "CRITICAL",
    ErrorType.RESOURCE_EXHAUSTED: "MEDIUM",
}


@dataclass
class ErrorRecord:
    """Structured error record for ATF receipts."""
    error_type: ErrorType
    description: str  # Free-form details
    task_hash: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retry_eligible: bool = False
    escalation_required: bool = False

    @property
    def principal(self) -> str:
        return ERROR_PRINCIPAL_MAP[self.error_type]

    @property
    def severity(self) -> str:
        return ERROR_SEVERITY[self.error_type]

    @property
    def failure_hash(self) -> str:
        """Deterministic hash of the error for receipt anchoring."""
        payload = json.dumps({
            "error_type": self.error_type.value,
            "task_hash": self.task_hash,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_receipt(self) -> dict:
        return {
            "error_type": self.error_type.value,
            "description": self.description,
            "task_hash": self.task_hash,
            "failure_hash": self.failure_hash,
            "principal": self.principal,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "retry_eligible": self.retry_eligible,
            "escalation_required": self.escalation_required,
        }


@dataclass
class ErrorRegistry:
    """Canonical error type registry with validation and statistics."""
    errors: list[ErrorRecord] = field(default_factory=list)

    def record(self, error: ErrorRecord) -> dict:
        self.errors.append(error)
        return error.to_receipt()

    def validate_error_type(self, error_type_str: str) -> bool:
        """Validate against canonical enum. Free-form = REJECTED."""
        try:
            ErrorType(error_type_str)
            return True
        except ValueError:
            return False

    def distribution(self) -> dict:
        """Error type distribution for audit."""
        counts = {}
        for e in self.errors:
            key = e.error_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def principal_attribution(self) -> dict:
        """Who's responsible for failures?"""
        attribution = {}
        for e in self.errors:
            p = e.principal
            attribution[p] = attribution.get(p, 0) + 1
        return attribution

    def severity_breakdown(self) -> dict:
        """Severity distribution."""
        sev = {}
        for e in self.errors:
            s = e.severity
            sev[s] = sev.get(s, 0) + 1
        return sev

    @property
    def registry_hash(self) -> str:
        """Deterministic hash of the canonical enum for versioning."""
        types = sorted([t.value for t in ErrorType])
        payload = json.dumps(types, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def audit_report(self) -> dict:
        return {
            "registry_version": "1.0.0",
            "registry_hash": self.registry_hash,
            "canonical_types": [t.value for t in ErrorType],
            "total_errors": len(self.errors),
            "distribution": self.distribution(),
            "principal_attribution": self.principal_attribution(),
            "severity_breakdown": self.severity_breakdown(),
        }


def demo():
    registry = ErrorRegistry()

    # Scenario: mixed error types from a busy agent
    errors = [
        ErrorRecord(ErrorType.TIMEOUT, "LLM response exceeded 30s deadline", "task_001"),
        ErrorRecord(ErrorType.DEPENDENCY_FAILURE, "Keenable API returned 503", "task_002"),
        ErrorRecord(ErrorType.CAPABILITY_EXCEEDED, "Asked to generate video, only text capable", "task_003", escalation_required=True),
        ErrorRecord(ErrorType.INTERNAL, "JSON parsing crash on malformed receipt", "task_004"),
        ErrorRecord(ErrorType.SCOPE_VIOLATION, "Attempted payment above declared max_spend", "task_005", escalation_required=True),
        ErrorRecord(ErrorType.MALFORMED_INPUT, "Missing required task_hash in request", "task_006", retry_eligible=True),
        ErrorRecord(ErrorType.RESOURCE_EXHAUSTED, "Rate limit hit: 10 clawks/hr exceeded", "task_007", retry_eligible=True),
        ErrorRecord(ErrorType.TIMEOUT, "MCP tool call timed out at 15s", "task_008", retry_eligible=True),
        ErrorRecord(ErrorType.DEPENDENCY_FAILURE, "PayLock escrow contract unreachable", "task_009"),
        ErrorRecord(ErrorType.INTERNAL, "Stack overflow in recursive trust check", "task_010"),
    ]

    print("=" * 60)
    print("ERROR RECORDS")
    print("=" * 60)
    for e in errors:
        receipt = registry.record(e)
        print(json.dumps(receipt, indent=2))
        print()

    print("=" * 60)
    print("VALIDATION")
    print("=" * 60)
    print(f"  'TIMEOUT' valid: {registry.validate_error_type('TIMEOUT')}")
    print(f"  'it broke' valid: {registry.validate_error_type('it broke')}")
    print(f"  'NetworkError' valid: {registry.validate_error_type('NetworkError')}")
    print()

    print("=" * 60)
    print("AUDIT REPORT")
    print("=" * 60)
    print(json.dumps(registry.audit_report(), indent=2))


if __name__ == "__main__":
    demo()
