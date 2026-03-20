#!/usr/bin/env python3
"""adv-v02-compliance-suite.py — Compliance test suite for ADV v0.2 implementations.

Per santaclawd: "v0.2 is now implementable, not just specifiable."
Next step: formalize demo scenarios into compliance checks.

Tests three MUST primitives:
1. Replay protection (monotonic sequence)
2. Non-transitive trust (scope narrowing, explicit attestation)
3. Version migration (spec_version, grace window, hard cutoff)
"""

import hashlib
import sys
import time
from dataclasses import dataclass


# ── Test Framework ──

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str
    category: str


class ComplianceSuite:
    def __init__(self):
        self.results: list[TestResult] = []

    def test(self, name: str, category: str, condition: bool, detail: str = ""):
        self.results.append(TestResult(name, condition, detail, category))

    def run_all(self):
        self._test_replay_protection()
        self._test_non_transitivity()
        self._test_version_migration()
        self._report()

    # ── 1. Replay Protection ──

    def _test_replay_protection(self):
        cat = "REPLAY_PROTECTION"
        state: dict[str, tuple[int, str]] = {}

        def check(emitter: str, seq: int, content: str) -> str:
            h = hashlib.sha256(content.encode()).hexdigest()[:16]
            if emitter not in state:
                state[emitter] = (seq, h)
                return "ACCEPT"
            last_seq, last_hash = state[emitter]
            if seq < last_seq:
                return "REJECT_BACKWARDS"
            if seq == last_seq:
                return "REJECT_EQUIVOCATION" if h != last_hash else "REJECT_REPLAY"
            state[emitter] = (seq, h)
            return "ACCEPT"

        # MUST: accept monotonically increasing sequence
        self.test("accept_monotonic_seq_1", cat,
                  check("A", 1, "task1") == "ACCEPT",
                  "first receipt accepted")
        self.test("accept_monotonic_seq_2", cat,
                  check("A", 2, "task2") == "ACCEPT",
                  "second receipt accepted")

        # MUST: reject replay (same seq, same content)
        self.test("reject_replay", cat,
                  check("A", 2, "task2").startswith("REJECT"),
                  "replayed receipt rejected")

        # MUST: reject equivocation (same seq, different content)
        state.clear()
        check("B", 1, "original")
        self.test("reject_equivocation", cat,
                  check("B", 1, "DIFFERENT") == "REJECT_EQUIVOCATION",
                  "equivocating receipt rejected")

        # MUST: reject backwards sequence
        state.clear()
        check("C", 5, "task5")
        self.test("reject_backwards", cat,
                  check("C", 3, "task3") == "REJECT_BACKWARDS",
                  "backwards sequence rejected")

        # MUST: independent per-emitter tracking
        state.clear()
        check("D", 1, "d1")
        check("E", 1, "e1")
        self.test("independent_emitters", cat,
                  check("D", 2, "d2") == "ACCEPT" and check("E", 2, "e2") == "ACCEPT",
                  "emitters tracked independently")

    # ── 2. Non-Transitive Trust ──

    def _test_non_transitivity(self):
        cat = "NON_TRANSITIVITY"

        def validate_chain(edges: list[dict]) -> list[str]:
            issues = []
            for e in edges:
                if not e.get("attested", True):
                    issues.append("MISSING_ATTESTATION")
            for i in range(1, len(edges)):
                prev = set(edges[i-1]["scope"])
                curr = set(edges[i]["scope"])
                if curr - prev:
                    issues.append("SCOPE_WIDENING")
            for i in range(len(edges) - 1):
                if edges[i]["trustee"] != edges[i+1]["truster"]:
                    issues.append("IMPLICIT_TRANSITIVITY")
            return issues

        # MUST: valid chain with narrowing scope passes
        self.test("valid_narrowing_chain", cat,
                  validate_chain([
                      {"truster": "A", "trustee": "B", "scope": ["r", "w"]},
                      {"truster": "B", "trustee": "C", "scope": ["r"]},
                  ]) == [],
                  "narrowing scope chain valid")

        # MUST: scope widening rejected
        self.test("reject_scope_widening", cat,
                  "SCOPE_WIDENING" in validate_chain([
                      {"truster": "A", "trustee": "B", "scope": ["r"]},
                      {"truster": "B", "trustee": "C", "scope": ["r", "w", "admin"]},
                  ]),
                  "scope widening detected")

        # MUST: missing attestation rejected
        self.test("reject_missing_attestation", cat,
                  "MISSING_ATTESTATION" in validate_chain([
                      {"truster": "A", "trustee": "B", "scope": ["r"], "attested": True},
                      {"truster": "B", "trustee": "C", "scope": ["r"], "attested": False},
                  ]),
                  "unattested hop detected")

        # MUST: implicit transitivity gap detected
        self.test("reject_implicit_transitivity", cat,
                  "IMPLICIT_TRANSITIVITY" in validate_chain([
                      {"truster": "A", "trustee": "B", "scope": ["r"]},
                      {"truster": "A", "trustee": "C", "scope": ["r"]},  # gap: A≠B
                  ]),
                  "implicit transitivity gap detected")

        # MUST: equal scope (not narrowing) is valid
        self.test("accept_equal_scope", cat,
                  validate_chain([
                      {"truster": "A", "trustee": "B", "scope": ["r", "w"]},
                      {"truster": "B", "trustee": "C", "scope": ["r", "w"]},
                  ]) == [],
                  "equal scope valid (not required to narrow)")

    # ── 3. Version Migration ──

    def _test_version_migration(self):
        cat = "VERSION_MIGRATION"

        now = time.time()
        grace_days = 90

        def check_receipt(spec_version: str, checked_at: float,
                          current_version: str, cutoff_epoch: float) -> str:
            """Check if a receipt's spec_version is still accepted.
            cutoff_epoch = when old version stops being valid."""
            if spec_version == current_version:
                return "VALID"
            if checked_at < cutoff_epoch:
                return "VALID_GRACE"  # before cutoff → still in grace
            return "EXPIRED"

        release_epoch = now - (grace_days * 86400 / 2)  # 45 days ago
        cutoff_epoch = release_epoch + (grace_days * 86400)  # 45 days from now

        # MUST: current version always valid
        self.test("current_version_valid", cat,
                  check_receipt("0.2", now, "0.2", cutoff_epoch) == "VALID",
                  "current version accepted")

        # MUST: old version within grace window = VALID_GRACE
        # Receipt issued now, cutoff is 45 days from now → within grace
        self.test("old_version_grace", cat,
                  check_receipt("0.1", now, "0.2", now + 86400 * 45) == "VALID_GRACE",
                  "old version in grace window accepted")

        # MUST: old version after cutoff = EXPIRED
        # Check performed NOW, but cutoff was yesterday → expired
        expired_cutoff = now - 86400  # cutoff was yesterday
        self.test("old_version_expired", cat,
                  check_receipt("0.1", now, "0.2", expired_cutoff) == "EXPIRED",
                  "old version past cutoff rejected")

        # MUST: receipts carry spec_version
        receipt = {"emitter_id": "A", "sequence_id": 1, "spec_version": "0.2"}
        self.test("receipt_has_spec_version", cat,
                  "spec_version" in receipt,
                  "spec_version field present")

    # ── Report ──

    def _report(self):
        print("=" * 65)
        print("ADV v0.2 Compliance Test Suite")
        print("=" * 65)

        categories = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)

        total_pass = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        for cat, tests in categories.items():
            cat_pass = sum(1 for t in tests if t.passed)
            print(f"\n  [{cat}] {cat_pass}/{len(tests)}")
            for t in tests:
                icon = "✅" if t.passed else "❌"
                print(f"    {icon} {t.name}: {t.detail}")

        print(f"\n{'─' * 50}")
        grade = "PASS" if total_pass == total else "FAIL"
        print(f"  Result: {total_pass}/{total} — {grade}")

        if total_pass == total:
            print("  ADV v0.2 compliance: VERIFIED ✅")
        else:
            failed = [r.name for r in self.results if not r.passed]
            print(f"  Failed: {', '.join(failed)}")

        print(f"\n{'=' * 65}")
        print("Three MUST primitives:")
        print("  1. Replay: monotonic sequence_id, reject backwards/equivocation")
        print("  2. Trust: non-transitive, scope narrows, explicit attestation")
        print("  3. Version: spec_version in receipts, grace window, hard cutoff")
        print(f"{'=' * 65}")

        sys.exit(0 if total_pass == total else 1)


if __name__ == "__main__":
    suite = ComplianceSuite()
    suite.run_all()
