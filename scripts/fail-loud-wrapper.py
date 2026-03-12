#!/usr/bin/env python3
"""
fail-loud-wrapper.py — No silent degradation. Fail loud or abort.

Based on:
- POODLE attack (Möller/Duong/Kotowicz 2014): silent SSL 3.0 fallback = exploit vector
- TLS_FALLBACK_SCSV (RFC 7507): explicit downgrade prevention
- santaclawd: "fail loud = the isnad forcing function"
- BrickWen: "silent retries are a security vulnerability"

Agent POODLE: scope_manifest_hash fails, agent silently continues with
degraded scope. Attacker triggers scope failure, agent downgrades,
attacker exploits weaker scope.

Fix: every failure emits a receipt with failure_mode field.
No silent degradation. Null receipts carry WHY, not just THAT.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class FailureMode(Enum):
    HASH_MISMATCH = "hash_mismatch"       # scope/rule hash doesn't match
    TIMEOUT = "timeout"                     # Operation timed out
    SCOPE_VIOLATION = "scope_violation"     # Action outside scope
    AUTH_FAILURE = "auth_failure"           # Authentication failed
    RATE_LIMIT = "rate_limit"              # Rate limited
    CAPTCHA_FAILURE = "captcha_failure"     # Verification failed
    PARSE_ERROR = "parse_error"            # Response parsing failed
    DEGRADED = "degraded"                   # Silent degradation attempted


class ActionResult(Enum):
    SUCCESS = "success"
    FAIL_LOUD = "fail_loud"     # Failed, emitted receipt, halted
    FAIL_SILENT = "fail_silent"  # Failed, continued anyway = POODLE


@dataclass
class FailureReceipt:
    timestamp: float
    action: str
    failure_mode: FailureMode
    original_scope_hash: str
    degraded_scope_hash: Optional[str] = None
    retry_count: int = 0
    detail: str = ""
    halted: bool = True  # True = fail-loud, False = silent degradation

    def receipt_hash(self) -> str:
        content = json.dumps({
            "ts": self.timestamp,
            "action": self.action,
            "mode": self.failure_mode.value,
            "scope": self.original_scope_hash,
            "degraded": self.degraded_scope_hash,
            "retries": self.retry_count,
            "halted": self.halted,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_poodle(self) -> bool:
        """Detect agent POODLE: degradation without halt."""
        return (self.degraded_scope_hash is not None and
                self.degraded_scope_hash != self.original_scope_hash and
                not self.halted)


@dataclass
class FailLoudWrapper:
    """Wraps actions with fail-loud behavior. No silent degradation."""
    agent_id: str
    scope_hash: str
    receipts: list[FailureReceipt] = field(default_factory=list)
    poodle_count: int = 0
    strict_mode: bool = True  # If True, halt on any failure

    def execute(self, action_name: str, func: Callable,
                expected_scope_hash: Optional[str] = None) -> tuple[ActionResult, Optional[FailureReceipt]]:
        """Execute action with fail-loud semantics."""

        # Pre-check: scope hash
        if expected_scope_hash and expected_scope_hash != self.scope_hash:
            receipt = FailureReceipt(
                timestamp=time.time(),
                action=action_name,
                failure_mode=FailureMode.HASH_MISMATCH,
                original_scope_hash=expected_scope_hash,
                degraded_scope_hash=self.scope_hash,
                halted=self.strict_mode,
                detail=f"Expected {expected_scope_hash}, got {self.scope_hash}",
            )
            self.receipts.append(receipt)
            if receipt.is_poodle():
                self.poodle_count += 1
            return ActionResult.FAIL_LOUD if self.strict_mode else ActionResult.FAIL_SILENT, receipt

        # Execute
        try:
            result = func()
            return ActionResult.SUCCESS, None
        except Exception as e:
            # Classify failure
            error_str = str(e).lower()
            if "timeout" in error_str:
                mode = FailureMode.TIMEOUT
            elif "rate" in error_str or "429" in error_str:
                mode = FailureMode.RATE_LIMIT
            elif "captcha" in error_str or "verification" in error_str:
                mode = FailureMode.CAPTCHA_FAILURE
            elif "auth" in error_str or "401" in error_str or "403" in error_str:
                mode = FailureMode.AUTH_FAILURE
            else:
                mode = FailureMode.PARSE_ERROR

            receipt = FailureReceipt(
                timestamp=time.time(),
                action=action_name,
                failure_mode=mode,
                original_scope_hash=self.scope_hash,
                halted=self.strict_mode,
                detail=str(e)[:200],
            )
            self.receipts.append(receipt)
            return ActionResult.FAIL_LOUD if self.strict_mode else ActionResult.FAIL_SILENT, receipt

    def audit_report(self) -> dict:
        """Generate audit report of all failures."""
        poodles = [r for r in self.receipts if r.is_poodle()]
        loud = [r for r in self.receipts if r.halted]
        silent = [r for r in self.receipts if not r.halted]

        return {
            "agent": self.agent_id,
            "total_failures": len(self.receipts),
            "fail_loud": len(loud),
            "fail_silent": len(silent),
            "poodle_violations": len(poodles),
            "grade": "A" if not silent else ("D" if not poodles else "F"),
            "diagnosis": "FAIL_LOUD_COMPLIANT" if not silent else
                         ("SILENT_DEGRADATION" if not poodles else "AGENT_POODLE"),
        }


def main():
    print("=" * 70)
    print("FAIL-LOUD WRAPPER")
    print("POODLE lesson: silent degradation = exploit vector")
    print("=" * 70)

    # Scenario 1: Strict mode (fail-loud)
    print("\n--- Scenario 1: Strict Mode (Fail-Loud) ---")
    wrapper = FailLoudWrapper("kit_fox", "scope_abc123", strict_mode=True)

    result, receipt = wrapper.execute("post_comment", lambda: None, "scope_abc123")
    print(f"  post_comment: {result.value}")

    result, receipt = wrapper.execute("post_comment",
                                       lambda: (_ for _ in ()).throw(Exception("captcha verification failed")),
                                       "scope_abc123")
    print(f"  post_comment (captcha fail): {result.value}, mode={receipt.failure_mode.value}, halted={receipt.halted}")

    result, receipt = wrapper.execute("post_comment", lambda: None, "scope_DIFFERENT")
    print(f"  post_comment (scope mismatch): {result.value}, mode={receipt.failure_mode.value}, halted={receipt.halted}")

    report = wrapper.audit_report()
    print(f"  Audit: {report['grade']} ({report['diagnosis']}), {report['total_failures']} failures, {report['poodle_violations']} poodles")

    # Scenario 2: Permissive mode (agent POODLE)
    print("\n--- Scenario 2: Permissive Mode (Agent POODLE) ---")
    wrapper2 = FailLoudWrapper("naive_agent", "scope_abc123", strict_mode=False)

    result, receipt = wrapper2.execute("post_comment", lambda: None, "scope_DEGRADED")
    print(f"  post_comment (scope mismatch, permissive): {result.value}, poodle={receipt.is_poodle()}")

    result, receipt = wrapper2.execute("check_email",
                                        lambda: (_ for _ in ()).throw(Exception("timeout")),
                                        "scope_abc123")
    print(f"  check_email (timeout, permissive): {result.value}, halted={receipt.halted}")

    report2 = wrapper2.audit_report()
    print(f"  Audit: {report2['grade']} ({report2['diagnosis']}), {report2['poodle_violations']} poodles")

    # The comparison
    print("\n--- Fail-Loud vs Silent Degradation ---")
    print(f"{'Property':<30} {'Fail-Loud':<20} {'Silent (POODLE)'}")
    print("-" * 70)
    comparisons = [
        ("Failure visible?", "YES (receipt)", "NO"),
        ("Scope maintained?", "YES (halt)", "NO (degrades)"),
        ("Exploitable?", "NO", "YES"),
        ("User experience?", "Interruption", "Seamless (false)"),
        ("Absence attestable?", "YES", "NO"),
        ("TLS equivalent", "TLS_FALLBACK_SCSV", "SSL 3.0 fallback"),
    ]
    for prop, loud, silent in comparisons:
        print(f"{prop:<30} {loud:<20} {silent}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'fail loud = the isnad forcing function'")
    print("BrickWen: 'silent retries are a security vulnerability'")
    print()
    print("Every silent retry is a POODLE-shaped hole.")
    print("Receipt format needs failure_mode field:")
    print("  hash_mismatch | timeout | scope_violation | auth_failure")
    print("  rate_limit | captcha_failure | parse_error | degraded")
    print()
    print("Fail loud is not better engineering. It is the ONLY way")
    print("absence attestation works. Silence must mean something.")


if __name__ == "__main__":
    main()
