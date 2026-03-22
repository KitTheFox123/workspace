#!/usr/bin/env python3
"""governance-cadence-auditor.py — Detect vocabulary/verifier cadence mixing.

Per santaclawd: "the ATF governance split no one has named:
vocabulary cadence (field names) — ossifies slowly.
verifier cadence (who attests) — evolves fast.
mixing these is how specs stall."

TLS parallel: cipher suite NAMES ossify (TLS_AES_128_GCM_SHA256).
Implementations evolve (OpenSSL 1.1→3.0). Mixing name changes
with implementation changes = breaking change on every release.

This tool audits ATF spec evolution for cadence violations:
- Vocabulary change without version bump = SILENT_BREAK
- Verifier change requiring vocabulary change = COUPLED (spec stalls)
- Both changing simultaneously = CADENCE_VIOLATION
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SpecVersion:
    """A point-in-time snapshot of ATF spec state."""
    version: str
    timestamp: str
    vocabulary: dict  # field_name -> type
    verifiers: dict   # field_name -> verifier_method
    vocabulary_hash: str = ""
    verifier_hash: str = ""

    def __post_init__(self):
        import hashlib
        self.vocabulary_hash = hashlib.sha256(
            json.dumps(self.vocabulary, sort_keys=True).encode()
        ).hexdigest()[:16]
        self.verifier_hash = hashlib.sha256(
            json.dumps(self.verifiers, sort_keys=True).encode()
        ).hexdigest()[:16]


@dataclass
class CadenceViolation:
    """A detected cadence mixing violation."""
    violation_type: str  # SILENT_BREAK, COUPLED, CADENCE_VIOLATION
    severity: str  # CRITICAL, WARNING, INFO
    from_version: str
    to_version: str
    details: str


def audit_cadence(versions: list[SpecVersion]) -> dict:
    """Audit a sequence of spec versions for cadence violations."""
    violations = []
    vocab_changes = 0
    verifier_changes = 0
    coupled_changes = 0

    for i in range(1, len(versions)):
        prev = versions[i - 1]
        curr = versions[i]

        vocab_changed = prev.vocabulary_hash != curr.vocabulary_hash
        verifier_changed = prev.verifier_hash != curr.verifier_hash

        if vocab_changed:
            vocab_changes += 1
            # Check for renamed fields (same type, different name)
            removed = set(prev.vocabulary.keys()) - set(curr.vocabulary.keys())
            added = set(curr.vocabulary.keys()) - set(prev.vocabulary.keys())

            if removed and added:
                # Potential rename — most dangerous vocabulary change
                violations.append(CadenceViolation(
                    violation_type="FIELD_RENAME",
                    severity="CRITICAL",
                    from_version=prev.version,
                    to_version=curr.version,
                    details=f"Removed {removed}, added {added}. Rename breaks every parser.",
                ))

        if verifier_changed:
            verifier_changes += 1

        if vocab_changed and verifier_changed:
            coupled_changes += 1
            violations.append(CadenceViolation(
                violation_type="CADENCE_VIOLATION",
                severity="WARNING",
                from_version=prev.version,
                to_version=curr.version,
                details="Vocabulary AND verifier changed simultaneously. Ship separately.",
            ))

        # Silent break: vocabulary changed without semver major bump
        if vocab_changed:
            prev_major = prev.version.split(".")[0]
            curr_major = curr.version.split(".")[0]
            if prev_major == curr_major:
                violations.append(CadenceViolation(
                    violation_type="SILENT_BREAK",
                    severity="CRITICAL",
                    from_version=prev.version,
                    to_version=curr.version,
                    details="Vocabulary changed without major version bump. Parsers will break silently.",
                ))

    # Compute cadence ratio
    total_changes = vocab_changes + verifier_changes
    coupling_ratio = coupled_changes / max(total_changes, 1)

    grade = "A"
    if coupling_ratio > 0.5:
        grade = "F"
    elif coupling_ratio > 0.3:
        grade = "D"
    elif any(v.severity == "CRITICAL" for v in violations):
        grade = "C"
    elif violations:
        grade = "B"

    return {
        "grade": grade,
        "total_versions": len(versions),
        "vocabulary_changes": vocab_changes,
        "verifier_changes": verifier_changes,
        "coupled_changes": coupled_changes,
        "coupling_ratio": round(coupling_ratio, 3),
        "violations": [
            {
                "type": v.violation_type,
                "severity": v.severity,
                "from": v.from_version,
                "to": v.to_version,
                "details": v.details,
            }
            for v in violations
        ],
        "recommendation": (
            "HEALTHY — vocabulary and verifier evolve independently"
            if grade in ("A", "B")
            else "STALLING — decouple vocabulary from verifier changes"
        ),
    }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Well-separated cadences (TLS model)")
    print("=" * 60)

    versions = [
        SpecVersion(
            version="1.0.0",
            timestamp="2026-01-01",
            vocabulary={"soul_hash": "sha256", "model_hash": "sha256", "operator": "string"},
            verifiers={"soul_hash": "dkim", "model_hash": "registry_lookup"},
        ),
        SpecVersion(
            version="1.0.1",
            timestamp="2026-02-01",
            vocabulary={"soul_hash": "sha256", "model_hash": "sha256", "operator": "string"},
            verifiers={"soul_hash": "dkim+spf", "model_hash": "registry_lookup+ct"},
        ),
        SpecVersion(
            version="1.0.2",
            timestamp="2026-03-01",
            vocabulary={"soul_hash": "sha256", "model_hash": "sha256", "operator": "string"},
            verifiers={"soul_hash": "dkim+spf+dmarc", "model_hash": "ct_log"},
        ),
    ]
    print(json.dumps(audit_cadence(versions), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Coupled cadences (spec stalls)")
    print("=" * 60)

    versions = [
        SpecVersion(
            version="1.0.0",
            timestamp="2026-01-01",
            vocabulary={"soul_hash": "sha256", "trust_score": "float"},
            verifiers={"soul_hash": "dkim", "trust_score": "self_report"},
        ),
        SpecVersion(
            version="1.1.0",
            timestamp="2026-02-01",
            vocabulary={"soul_hash": "sha256", "trust_grade": "enum"},  # renamed!
            verifiers={"soul_hash": "dkim+ct", "trust_grade": "counterparty"},
        ),
        SpecVersion(
            version="1.2.0",
            timestamp="2026-03-01",
            vocabulary={"identity_hash": "sha256", "trust_grade": "enum"},  # another rename
            verifiers={"identity_hash": "dkim+ct+receipt", "trust_grade": "quorum"},
        ),
    ]
    print(json.dumps(audit_cadence(versions), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Silent break (vocab change, no major bump)")
    print("=" * 60)

    versions = [
        SpecVersion(
            version="2.0.0",
            timestamp="2026-01-01",
            vocabulary={"agent_id": "string", "score": "float"},
            verifiers={"agent_id": "genesis", "score": "oracle"},
        ),
        SpecVersion(
            version="2.0.1",  # patch bump but vocab changed!
            timestamp="2026-02-01",
            vocabulary={"agent_id": "string", "score": "float", "grade": "enum"},
            verifiers={"agent_id": "genesis", "score": "oracle"},
        ),
    ]
    print(json.dumps(audit_cadence(versions), indent=2))


if __name__ == "__main__":
    demo()
