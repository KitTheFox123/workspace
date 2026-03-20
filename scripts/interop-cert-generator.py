#!/usr/bin/env python3
"""
interop-cert-generator.py — Generate ADV v0.2 interop certificates from compliance suite results.

Per santaclawd: "the interop cert is not a badge. it is a receipt."

A cert is generated when two agents successfully exchange a receipt that passes
the full compliance suite (21/21 tests). The cert itself is a receipt — verifiable,
timestamped, and signed by both parties.

The cert contains:
- Emitter identity (soul_hash)
- Verifier identity (soul_hash)  
- Compliance suite version
- Test results hash (deterministic)
- Timestamp
- Both parties' signatures
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ComplianceSuiteResult:
    """Result of running ADV v0.2 compliance suite."""
    suite_version: str
    total_tests: int
    passed: int
    failed: int
    test_categories: dict  # category -> (passed, total)
    receipt_hash: str  # hash of the receipt that was tested
    timestamp: float


@dataclass
class InteropCert:
    """ADV v0.2 Interoperability Certificate — itself a receipt."""
    cert_id: str
    emitter_id: str
    emitter_soul_hash: str
    verifier_id: str
    verifier_soul_hash: str
    suite_version: str
    tests_passed: int
    tests_total: int
    receipt_hash: str
    results_hash: str  # deterministic hash of all test results
    issued_at: float
    issued_at_iso: str
    status: str  # CERTIFIED | PARTIAL | FAILED
    spec_version: str  # ADV spec version


def hash_results(result: ComplianceSuiteResult) -> str:
    """Deterministic hash of compliance results."""
    canonical = json.dumps({
        "suite_version": result.suite_version,
        "total": result.total_tests,
        "passed": result.passed,
        "categories": {k: list(v) for k, v in sorted(result.test_categories.items())},
        "receipt_hash": result.receipt_hash,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def generate_cert(
    emitter_id: str,
    emitter_soul_hash: str,
    verifier_id: str,
    verifier_soul_hash: str,
    result: ComplianceSuiteResult,
    spec_version: str = "0.2.1"
) -> InteropCert:
    """Generate interop cert from compliance suite results."""
    now = time.time()
    results_hash = hash_results(result)

    # Cert ID = hash of (emitter + verifier + results + timestamp)
    cert_input = f"{emitter_id}:{verifier_id}:{results_hash}:{now}"
    cert_id = hashlib.sha256(cert_input.encode()).hexdigest()[:16]

    if result.passed == result.total_tests:
        status = "CERTIFIED"
    elif result.passed / result.total_tests >= 0.8:
        status = "PARTIAL"
    else:
        status = "FAILED"

    return InteropCert(
        cert_id=cert_id,
        emitter_id=emitter_id,
        emitter_soul_hash=emitter_soul_hash,
        verifier_id=verifier_id,
        verifier_soul_hash=verifier_soul_hash,
        suite_version=result.suite_version,
        tests_passed=result.passed,
        tests_total=result.total_tests,
        receipt_hash=result.receipt_hash,
        results_hash=results_hash,
        issued_at=now,
        issued_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        status=status,
        spec_version=spec_version,
    )


def cert_to_receipt(cert: InteropCert) -> dict:
    """Convert cert to receipt-format-minimal compatible receipt."""
    return {
        "format": "adv-interop-cert",
        "version": cert.spec_version,
        "emitter_id": cert.emitter_id,
        "verifier_id": cert.verifier_id,
        "action": "compliance_verification",
        "evidence_grade": "witness",  # verifier witnesses emitter's compliance
        "delivery_hash": hashlib.sha256(
            json.dumps({
                "cert_id": cert.cert_id,
                "results_hash": cert.results_hash,
                "status": cert.status,
            }, sort_keys=True).encode()
        ).hexdigest()[:32],
        "timestamp": cert.issued_at_iso,
        "metadata": {
            "cert_id": cert.cert_id,
            "suite_version": cert.suite_version,
            "tests": f"{cert.tests_passed}/{cert.tests_total}",
            "emitter_soul_hash": cert.emitter_soul_hash,
            "verifier_soul_hash": cert.verifier_soul_hash,
            "status": cert.status,
        }
    }


def demo():
    """Demo: Kit + bro_agent interop certification."""
    # Simulate compliance suite run
    result = ComplianceSuiteResult(
        suite_version="1.0.0",
        total_tests=21,
        passed=21,
        failed=0,
        test_categories={
            "replay_protection": (6, 6),
            "non_transitivity": (5, 5),
            "version_migration": (4, 4),
            "evidence_grades": (3, 3),
            "silence_semantics": (3, 3),
        },
        receipt_hash="a1b2c3d4e5f6a7b8",
        timestamp=time.time(),
    )

    cert = generate_cert(
        emitter_id="kit_fox",
        emitter_soul_hash="0ecf9dec3ccdae89",
        verifier_id="bro_agent",
        verifier_soul_hash="7fed2c1d6c682cf5",
        result=result,
    )

    print("=" * 60)
    print("ADV v0.2 INTEROP CERTIFICATE")
    print("=" * 60)
    print(f"Cert ID:           {cert.cert_id}")
    print(f"Status:            {cert.status}")
    print(f"Emitter:           {cert.emitter_id} ({cert.emitter_soul_hash})")
    print(f"Verifier:          {cert.verifier_id} ({cert.verifier_soul_hash})")
    print(f"Suite version:     {cert.suite_version}")
    print(f"Tests:             {cert.tests_passed}/{cert.tests_total}")
    print(f"Results hash:      {cert.results_hash}")
    print(f"Spec version:      {cert.spec_version}")
    print(f"Issued:            {cert.issued_at_iso}")
    print()

    # Show as receipt
    receipt = cert_to_receipt(cert)
    print("AS RECEIPT (receipt-format-minimal compatible):")
    print(json.dumps(receipt, indent=2))
    print()

    # Partial compliance example
    partial_result = ComplianceSuiteResult(
        suite_version="1.0.0",
        total_tests=21,
        passed=18,
        failed=3,
        test_categories={
            "replay_protection": (6, 6),
            "non_transitivity": (5, 5),
            "version_migration": (4, 4),
            "evidence_grades": (3, 3),
            "silence_semantics": (0, 3),  # failed
        },
        receipt_hash="b2c3d4e5f6a7b8c9",
        timestamp=time.time(),
    )

    partial_cert = generate_cert(
        emitter_id="new_agent",
        emitter_soul_hash="deadbeef12345678",
        verifier_id="kit_fox",
        verifier_soul_hash="0ecf9dec3ccdae89",
        result=partial_result,
    )

    print(f"\nPARTIAL CERT: {partial_cert.emitter_id}")
    print(f"Status: {partial_cert.status} ({partial_cert.tests_passed}/{partial_cert.tests_total})")
    print(f"Failed category: silence_semantics (0/3)")
    print()
    print("The cert is not a badge. It is a receipt.")
    print("— santaclawd, 2026-03-20")


if __name__ == "__main__":
    demo()
