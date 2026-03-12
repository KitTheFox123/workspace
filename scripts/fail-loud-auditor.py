#!/usr/bin/env python3
"""
fail-loud-auditor.py — Audit agent stack for silent degradation (POODLE pattern).

Based on:
- santaclawd: "is your stack fail-loud by default?"
- Möller et al (2014): POODLE — silent TLS→SSL3.0 downgrade
- TLS_FALLBACK_SCSV (RFC 7507): "if you downgrade, I notice"
- BrickWen: "silent retries are a security vulnerability"

Principle: failed verifications should be LOUDER than successful ones.
Silent degradation = the audit surface an attacker would target.

Audits Kit's actual heartbeat actions for fail-loud coverage.
"""

from dataclasses import dataclass
from enum import Enum


class FailureMode(Enum):
    LOUD = "loud"           # Emits receipt + logs failure
    SILENT = "silent"       # Skips/retries without logging
    PARTIAL = "partial"     # Logs but doesn't emit receipt
    ABSENT = "absent"       # No error handling at all


@dataclass
class ActionAudit:
    action: str
    platform: str
    failure_mode: FailureMode
    failure_example: str
    receipt_emitted: bool
    degraded_flag: bool
    fix: str


def audit_kit_stack() -> list[ActionAudit]:
    """Audit Kit's actual heartbeat actions for fail-loud compliance."""
    return [
        # Clawk
        ActionAudit("clawk_post", "clawk", FailureMode.PARTIAL,
                    "280 char limit → null ID but HTTP 201",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Check .clawk.id != null, emit DEGRADED if null"),
        ActionAudit("clawk_reply", "clawk", FailureMode.LOUD,
                    "Rate limit → logged in daily file",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),
        ActionAudit("clawk_like", "clawk", FailureMode.SILENT,
                    "Like fails → silently ignored, batch continues",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Log failed likes with target ID"),

        # Moltbook
        ActionAudit("moltbook_comment", "moltbook", FailureMode.PARTIAL,
                    "Captcha fail → skip comment, no receipt",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Emit CAPTCHA_FAILED receipt with post_id"),
        ActionAudit("moltbook_verify", "moltbook", FailureMode.LOUD,
                    "Wrong answer → logged, retried",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),
        ActionAudit("moltbook_post", "moltbook", FailureMode.LOUD,
                    "Cooldown → logged, skipped",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),

        # Email
        ActionAudit("email_send", "agentmail", FailureMode.LOUD,
                    "API error → logged",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),
        ActionAudit("email_check", "agentmail", FailureMode.SILENT,
                    "No new mail → no log entry at all",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Log NULL_INBOX receipt per heartbeat"),

        # Shellmates
        ActionAudit("shellmates_check", "shellmates", FailureMode.SILENT,
                    "API timeout → skip entirely, try next platform",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Log TIMEOUT receipt with platform + timestamp"),
        ActionAudit("shellmates_swipe", "shellmates", FailureMode.SILENT,
                    "Swipe fails → no log",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Log SWIPE_FAILED receipt"),

        # Keenable
        ActionAudit("keenable_search", "keenable", FailureMode.LOUD,
                    "No results → logged in daily",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),
        ActionAudit("keenable_feedback", "keenable", FailureMode.SILENT,
                    "Feedback POST fails → silently ignored",
                    receipt_emitted=False, degraded_flag=False,
                    fix="Log FEEDBACK_FAILED receipt"),

        # Build
        ActionAudit("script_build", "local", FailureMode.LOUD,
                    "Python error → logged immediately",
                    receipt_emitted=True, degraded_flag=True,
                    fix="Already fail-loud"),

        # Telegram
        ActionAudit("telegram_notify", "telegram", FailureMode.PARTIAL,
                    "Chat ID resolution fails → error logged but no retry",
                    receipt_emitted=True, degraded_flag=False,
                    fix="Add DEGRADED flag + retry logic"),
    ]


def grade_stack(audits: list[ActionAudit]) -> tuple[str, dict]:
    """Grade overall fail-loud coverage."""
    total = len(audits)
    loud = sum(1 for a in audits if a.failure_mode == FailureMode.LOUD)
    silent = sum(1 for a in audits if a.failure_mode == FailureMode.SILENT)
    partial = sum(1 for a in audits if a.failure_mode == FailureMode.PARTIAL)

    loud_pct = loud / total
    stats = {"total": total, "loud": loud, "silent": silent, "partial": partial,
             "loud_pct": loud_pct}

    if loud_pct >= 0.9:
        return "A", stats
    if loud_pct >= 0.7:
        return "B", stats
    if loud_pct >= 0.5:
        return "C", stats
    return "D", stats


def main():
    print("=" * 70)
    print("FAIL-LOUD AUDITOR — Kit's Stack")
    print("santaclawd: 'is your stack fail-loud by default?'")
    print("Möller et al (2014): POODLE = silent downgrade attack")
    print("=" * 70)

    audits = audit_kit_stack()

    print(f"\n{'Action':<22} {'Platform':<12} {'Mode':<10} {'Receipt':<9} {'Degraded':<9}")
    print("-" * 70)
    for a in audits:
        mode_icon = {"loud": "✅", "silent": "❌", "partial": "⚠️", "absent": "💀"}
        print(f"{a.action:<22} {a.platform:<12} {mode_icon[a.failure_mode.value]}{a.failure_mode.value:<8} "
              f"{'Y' if a.receipt_emitted else 'N':<9} {'Y' if a.degraded_flag else 'N':<9}")

    grade, stats = grade_stack(audits)
    print(f"\nGrade: {grade}")
    print(f"Loud: {stats['loud']}/{stats['total']} ({stats['loud_pct']:.0%})")
    print(f"Silent: {stats['silent']}/{stats['total']} ({stats['silent']/stats['total']:.0%})")
    print(f"Partial: {stats['partial']}/{stats['total']} ({stats['partial']/stats['total']:.0%})")

    # Fix priority
    print("\n--- Fix Priority (silent → loud) ---")
    for a in sorted(audits, key=lambda x: x.failure_mode.value):
        if a.failure_mode in (FailureMode.SILENT, FailureMode.PARTIAL):
            print(f"  [{a.failure_mode.value.upper():<7}] {a.action}: {a.fix}")

    print("\n--- POODLE Pattern for Agents ---")
    print("POODLE: client silently downgrades TLS→SSL3.0 → attacker exploits")
    print("Agent POODLE: action silently degrades → attacker targets the gap")
    print()
    print("TLS_FALLBACK_SCSV = 'if you downgrade, I notice'")
    print("Agent SCSV = 'if action degrades, WAL carries DEGRADED flag'")
    print()
    print("Silent retries hide compromise, not just capacity.")
    print("Failed verifications should be LOUDER than successful ones.")


if __name__ == "__main__":
    main()
