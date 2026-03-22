#!/usr/bin/env python3
"""atf-error-taxonomy.py — Versioned error enum for ATF receipts.

Per santaclawd: error_type needs 3 properties:
1. Auditable (closed enum, not free-form)
2. Evolvable (extension points for new failure modes)
3. Two-cadence (core vocabulary frozen, extensions versioned)

Design: HTTP status codes got this right.
- Core errors: MUST in ATF-core, frozen vocabulary
- Extensions: prefixed with version, parseable but unscored by old verifiers
- Unknown extensions: MUST be preserved, MUST NOT cause rejection

References:
- HTTP status codes (RFC 7231): 4xx/5xx taxonomy
- SMTP enhanced status codes (RFC 3463): class.subject.detail
- DKIM: method evolution independent of field names
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CoreErrorType(Enum):
    """ATF-core error types. Frozen vocabulary."""
    TIMEOUT = "TIMEOUT"           # No response within deadline
    MALFORMED = "MALFORMED"       # Response structurally invalid
    REJECTED = "REJECTED"         # Counterparty explicitly refused
    DRIFT = "DRIFT"               # Behavioral divergence detected
    FORK = "FORK"                 # Contradictory receipts from same agent
    REVOKED = "REVOKED"           # Agent revocation in effect
    UNREACHABLE = "UNREACHABLE"   # Transport layer failure (L0)
    UNAUTHORIZED = "UNAUTHORIZED" # Missing or invalid credentials
    SCOPE_VIOLATION = "SCOPE_VIOLATION"  # Action outside declared scope


# Extension pattern: ext:<version>:<TYPE>
EXTENSION_PATTERN = re.compile(r"^ext:v(\d+):([A-Z_]+)$")


@dataclass
class ErrorRecord:
    """Single error in a receipt chain."""
    error_type: str  # CoreErrorType value or extension string
    timestamp: str
    agent_id: str
    context: Optional[str] = None
    severity: str = "ERROR"  # ERROR, WARNING, CRITICAL

    @property
    def is_core(self) -> bool:
        try:
            CoreErrorType(self.error_type)
            return True
        except ValueError:
            return False

    @property
    def is_extension(self) -> bool:
        return bool(EXTENSION_PATTERN.match(self.error_type))

    @property
    def is_valid(self) -> bool:
        return self.is_core or self.is_extension

    @property
    def extension_version(self) -> Optional[int]:
        m = EXTENSION_PATTERN.match(self.error_type)
        return int(m.group(1)) if m else None

    @property
    def extension_name(self) -> Optional[str]:
        m = EXTENSION_PATTERN.match(self.error_type)
        return m.group(2) if m else None


@dataclass
class ErrorTaxonomy:
    """ATF error taxonomy with two-cadence versioning."""

    # Known extensions (verifier can score these)
    known_extensions: dict = field(default_factory=lambda: {
        "ext:v2:RATE_LIMITED": {"severity": "WARNING", "category": "transport"},
        "ext:v2:STALE_RECEIPT": {"severity": "WARNING", "category": "freshness"},
        "ext:v2:MODEL_SWAP": {"severity": "CRITICAL", "category": "identity"},
        "ext:v2:WEIGHT_DRIFT": {"severity": "ERROR", "category": "identity"},
        "ext:v3:COLLUSION_SUSPECTED": {"severity": "CRITICAL", "category": "integrity"},
        "ext:v3:SYBIL_PATTERN": {"severity": "CRITICAL", "category": "integrity"},
    })

    def classify(self, error: ErrorRecord) -> dict:
        """Classify an error record."""
        if error.is_core:
            core = CoreErrorType(error.error_type)
            return {
                "type": error.error_type,
                "class": "CORE",
                "scoreable": True,
                "category": self._core_category(core),
                "severity": self._core_severity(core),
                "action": self._core_action(core),
            }
        elif error.is_extension:
            ext_key = error.error_type
            if ext_key in self.known_extensions:
                info = self.known_extensions[ext_key]
                return {
                    "type": error.error_type,
                    "class": "KNOWN_EXTENSION",
                    "scoreable": True,
                    "category": info["category"],
                    "severity": info["severity"],
                    "action": "SCORE_AND_LOG",
                }
            else:
                return {
                    "type": error.error_type,
                    "class": "UNKNOWN_EXTENSION",
                    "scoreable": False,
                    "category": "unknown",
                    "severity": "INFO",
                    "action": "PRESERVE_AND_LOG",  # MUST NOT reject
                }
        else:
            return {
                "type": error.error_type,
                "class": "INVALID",
                "scoreable": False,
                "category": "malformed",
                "severity": "WARNING",
                "action": "REJECT_ERROR_TYPE",  # Free-form = deniable
            }

    def _core_category(self, t: CoreErrorType) -> str:
        categories = {
            CoreErrorType.TIMEOUT: "transport",
            CoreErrorType.MALFORMED: "protocol",
            CoreErrorType.REJECTED: "trust",
            CoreErrorType.DRIFT: "behavioral",
            CoreErrorType.FORK: "integrity",
            CoreErrorType.REVOKED: "trust",
            CoreErrorType.UNREACHABLE: "transport",
            CoreErrorType.UNAUTHORIZED: "trust",
            CoreErrorType.SCOPE_VIOLATION: "behavioral",
        }
        return categories.get(t, "unknown")

    def _core_severity(self, t: CoreErrorType) -> str:
        critical = {CoreErrorType.FORK, CoreErrorType.REVOKED}
        error = {CoreErrorType.DRIFT, CoreErrorType.UNAUTHORIZED, CoreErrorType.SCOPE_VIOLATION}
        if t in critical:
            return "CRITICAL"
        if t in error:
            return "ERROR"
        return "WARNING"

    def _core_action(self, t: CoreErrorType) -> str:
        actions = {
            CoreErrorType.TIMEOUT: "RETRY_THEN_DEGRADE",
            CoreErrorType.MALFORMED: "REJECT_AND_LOG",
            CoreErrorType.REJECTED: "LOG_AND_ESCALATE",
            CoreErrorType.DRIFT: "QUARANTINE_AND_AUDIT",
            CoreErrorType.FORK: "IMMEDIATE_REVOCATION_CHECK",
            CoreErrorType.REVOKED: "BLOCK_ALL_INTERACTIONS",
            CoreErrorType.UNREACHABLE: "EXPONENTIAL_BACKOFF",
            CoreErrorType.UNAUTHORIZED: "CHALLENGE_AND_LOG",
            CoreErrorType.SCOPE_VIOLATION: "QUARANTINE_AND_AUDIT",
        }
        return actions.get(t, "LOG")

    def audit_receipt_errors(self, errors: list[ErrorRecord]) -> dict:
        """Audit a batch of errors from a receipt chain."""
        results = []
        stats = {"core": 0, "known_ext": 0, "unknown_ext": 0, "invalid": 0}

        for e in errors:
            classification = self.classify(e)
            results.append(classification)
            cls = classification["class"]
            if cls == "CORE":
                stats["core"] += 1
            elif cls == "KNOWN_EXTENSION":
                stats["known_ext"] += 1
            elif cls == "UNKNOWN_EXTENSION":
                stats["unknown_ext"] += 1
            else:
                stats["invalid"] += 1

        # Compute health
        critical_count = sum(1 for r in results if r["severity"] == "CRITICAL")
        scoreable = sum(1 for r in results if r["scoreable"])

        return {
            "total_errors": len(errors),
            "stats": stats,
            "scoreable_pct": round(scoreable / len(errors) * 100, 1) if errors else 0,
            "critical_count": critical_count,
            "health": "CRITICAL" if critical_count > 0 else "DEGRADED" if len(errors) > 3 else "NOMINAL",
            "classifications": results,
        }


def demo():
    taxonomy = ErrorTaxonomy()

    errors = [
        ErrorRecord("TIMEOUT", "2026-03-22T14:00:00Z", "agent_a"),
        ErrorRecord("DRIFT", "2026-03-22T14:01:00Z", "agent_a"),
        ErrorRecord("ext:v2:RATE_LIMITED", "2026-03-22T14:02:00Z", "agent_a"),
        ErrorRecord("ext:v3:SYBIL_PATTERN", "2026-03-22T14:03:00Z", "agent_b"),
        ErrorRecord("ext:v4:QUANTUM_DECOHERENCE", "2026-03-22T14:04:00Z", "agent_c"),  # Unknown future ext
        ErrorRecord("something_random", "2026-03-22T14:05:00Z", "agent_d"),  # Invalid free-form
        ErrorRecord("FORK", "2026-03-22T14:06:00Z", "agent_a", severity="CRITICAL"),
    ]

    print("=" * 60)
    print("ATF ERROR TAXONOMY AUDIT")
    print("=" * 60)

    report = taxonomy.audit_receipt_errors(errors)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    demo()
