#!/usr/bin/env python3
"""
DKIM idempotency key validator for agent email DLQ.

Validates that X-Idempotency-Key is present in DKIM h= field,
ensuring the key is signed and tamper-evident through relay MTAs.

Based on: RFC 6376 §5.4, RFC 5321 (SMTP), IETF draft-httpapi-idempotency-key-header

Key findings:
- MTAs CAN strip unsigned X- headers (RFC 6376 §5.5)
- X-Idempotency-Key MUST be in h= to survive relay
- Sign at origin (agentmail), not relay MTA
- Without h= inclusion: DKIM passes but key is gone = worst case
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmailMessage:
    from_addr: str
    to_addr: str
    subject: str
    body: str
    x_idempotency_key: Optional[str] = None
    dkim_h_field: list[str] = None  # headers listed in DKIM h=
    dkim_valid: bool = True

    def __post_init__(self):
        if self.dkim_h_field is None:
            self.dkim_h_field = []


@dataclass
class ValidationResult:
    status: str  # "valid" | "unsigned_key" | "missing_key" | "stripped" | "dkim_fail"
    grade: str
    risk: str
    detail: str


class DKIMIdempotencyValidator:
    def validate(self, msg: EmailMessage, relay_stripped_headers: list[str] = None) -> ValidationResult:
        if relay_stripped_headers is None:
            relay_stripped_headers = []

        # Check DKIM signature
        if not msg.dkim_valid:
            return ValidationResult(
                status="dkim_fail",
                grade="F",
                risk="CRITICAL: DKIM signature invalid. Cannot trust any headers.",
                detail="DKIM verification failed. Message integrity compromised."
            )

        # Check if X-Idempotency-Key exists
        if not msg.x_idempotency_key:
            return ValidationResult(
                status="missing_key",
                grade="F",
                risk="CRITICAL: No idempotency key. Retry will issue duplicate cert.",
                detail="Email DLQ message missing X-Idempotency-Key header."
            )

        # Check if key was stripped by relay
        if "x-idempotency-key" in [h.lower() for h in relay_stripped_headers]:
            return ValidationResult(
                status="stripped",
                grade="F",
                risk="CRITICAL: MTA stripped X-Idempotency-Key before delivery.",
                detail="Relay MTA removed custom header. Key was present at origin but lost in transit."
            )

        # Check if key is in DKIM h= field
        h_lower = [h.lower() for h in msg.dkim_h_field]
        if "x-idempotency-key" not in h_lower:
            return ValidationResult(
                status="unsigned_key",
                grade="D",
                risk="HIGH: Key present but NOT signed by DKIM. Can be injected/modified by any relay.",
                detail="RFC 6376 §5.4: headers not in h= are not covered by signature. "
                       "An intermediary MTA could replace the key value."
            )

        # All checks pass
        return ValidationResult(
            status="valid",
            grade="A",
            risk="LOW: Key present, DKIM-signed, tamper-evident.",
            detail="X-Idempotency-Key in DKIM h= field. Origin-signed. Safe for deduplication."
        )


def run_scenarios():
    validator = DKIMIdempotencyValidator()

    scenarios = [
        (
            "Correct: origin-signed with key in h=",
            EmailMessage(
                from_addr="kit_fox@agentmail.to",
                to_addr="skillfence@paylock.ai",
                subject="Re: cert request dep_001",
                body="DLQ fallback for deposit dep_001",
                x_idempotency_key="a1b2c3d4e5f6",
                dkim_h_field=["from", "to", "subject", "x-idempotency-key", "date"],
                dkim_valid=True,
            ),
            [],
        ),
        (
            "Missing key entirely",
            EmailMessage(
                from_addr="kit_fox@agentmail.to",
                to_addr="skillfence@paylock.ai",
                subject="Re: cert request dep_002",
                body="DLQ fallback — forgot the key",
                x_idempotency_key=None,
                dkim_h_field=["from", "to", "subject", "date"],
                dkim_valid=True,
            ),
            [],
        ),
        (
            "Key present but NOT in DKIM h= (unsigned)",
            EmailMessage(
                from_addr="kit_fox@agentmail.to",
                to_addr="skillfence@paylock.ai",
                subject="Re: cert request dep_003",
                body="DLQ fallback — key not signed",
                x_idempotency_key="a1b2c3d4e5f6",
                dkim_h_field=["from", "to", "subject", "date"],  # no x-idempotency-key!
                dkim_valid=True,
            ),
            [],
        ),
        (
            "Key stripped by relay MTA",
            EmailMessage(
                from_addr="kit_fox@agentmail.to",
                to_addr="skillfence@paylock.ai",
                subject="Re: cert request dep_004",
                body="DLQ fallback — stripped in transit",
                x_idempotency_key=None,  # gone after stripping
                dkim_h_field=["from", "to", "subject", "x-idempotency-key", "date"],
                dkim_valid=False,  # DKIM fails because signed header is missing
            ),
            ["x-idempotency-key"],
        ),
        (
            "DKIM signature invalid",
            EmailMessage(
                from_addr="evil@attacker.com",
                to_addr="skillfence@paylock.ai",
                subject="Re: cert request dep_005",
                body="Forged DLQ message",
                x_idempotency_key="forged_key",
                dkim_h_field=["from", "to", "subject", "x-idempotency-key"],
                dkim_valid=False,
            ),
            [],
        ),
    ]

    print("=" * 60)
    print("DKIM IDEMPOTENCY KEY VALIDATOR")
    print("RFC 6376 §5.4 + IETF draft-httpapi-idempotency-key-header")
    print("=" * 60)

    for name, msg, stripped in scenarios:
        print(f"\n--- {name} ---")
        result = validator.validate(msg, stripped)
        print(f"  Status: {result.status}")
        print(f"  Grade:  {result.grade}")
        print(f"  Risk:   {result.risk}")
        print(f"  Detail: {result.detail}")

    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("  1. ALWAYS include X-Idempotency-Key in DKIM h= field")
    print("  2. Sign at ORIGIN (agentmail), not relay MTA")
    print("  3. Receiver MUST verify DKIM before trusting key")
    print("  4. If key missing or unsigned: reject, don't deduplicate")
    print("  5. Fallback: compute key from deposit_ref in body (weaker)")
    print("=" * 60)


if __name__ == "__main__":
    run_scenarios()
