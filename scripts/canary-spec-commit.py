#!/usr/bin/env python3
"""
canary-spec-commit.py — Pre-committed canary probes for circuit breaker half-open state.

Based on:
- Nygard (Release It!, 2007/2018): Circuit breaker pattern
- santaclawd: "canary_spec_hash = pre-committed at lock time"
- Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence

The problem: standard circuit breakers send ONE request in half-open state.
For agents: who defines the canary task? If attestor picks post-drift,
they can make recovery trivially easy (gaming) or impossibly hard (griefing).

Fix: pre-commit canary_spec_hash at contract lock time.
hash(canary_input + expected_output + difficulty_class) = immutable.
Half-open probe difficulty = original contract difficulty. No inflation.
"""

import hashlib
import json
import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Tripped — drift detected
    HALF_OPEN = "half_open"  # Canary probe in progress


class DifficultyClass(Enum):
    TRIVIAL = "trivial"       # Always passable
    ORIGINAL = "original"     # Same as contract difficulty
    ESCALATED = "escalated"   # Harder than contract


@dataclass
class CanarySpec:
    canary_input: str
    expected_output: str
    difficulty_class: DifficultyClass
    tolerance: float  # How close to expected counts as pass
    
    def spec_hash(self) -> str:
        content = json.dumps({
            "input": self.canary_input,
            "expected": self.expected_output,
            "difficulty": self.difficulty_class.value,
            "tolerance": self.tolerance,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class CircuitBreaker:
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 3
    canary_spec: Optional[CanarySpec] = None
    canary_spec_hash: str = ""  # Committed at lock time
    
    def trip(self, reason: str) -> str:
        self.state = CircuitState.OPEN
        return f"TRIPPED: {reason}. Canary required to re-enter."
    
    def attempt_recovery(self, agent_output: str) -> tuple[bool, str]:
        """Half-open: run canary probe with pre-committed spec."""
        if self.state != CircuitState.OPEN:
            return False, "Not in OPEN state"
        
        self.state = CircuitState.HALF_OPEN
        
        # Verify canary spec hasn't been tampered
        if self.canary_spec.spec_hash() != self.canary_spec_hash:
            return False, "CANARY_TAMPERED: spec_hash mismatch"
        
        # Check agent output against expected
        expected = self.canary_spec.expected_output
        tolerance = self.canary_spec.tolerance
        
        try:
            score = 1.0 - abs(float(agent_output) - float(expected)) / max(float(expected), 1e-6)
            passed = score >= (1.0 - tolerance)
        except ValueError:
            passed = agent_output.strip() == expected.strip()
            score = 1.0 if passed else 0.0
        
        if passed:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            return True, f"RECOVERED: score={score:.3f}, canary passed"
        else:
            self.state = CircuitState.OPEN
            self.failure_count += 1
            return False, f"STILL_OPEN: score={score:.3f}, canary failed"


def grade_canary_design(spec: CanarySpec, committed: bool) -> tuple[str, str]:
    """Grade canary probe design."""
    if not committed:
        return "F", "UNCOMMITTED_CANARY"
    if spec.difficulty_class == DifficultyClass.TRIVIAL:
        return "D", "TRIVIAL_CANARY"
    if spec.difficulty_class == DifficultyClass.ESCALATED:
        return "C", "ESCALATED_CANARY"  # Griefing risk
    return "A", "PROPERLY_COMMITTED"


def main():
    print("=" * 70)
    print("CANARY SPEC COMMITMENT")
    print("santaclawd: 'canary_spec_hash = pre-committed at lock time'")
    print("=" * 70)

    # Scenario 1: Properly committed canary
    print("\n--- Scenario 1: Properly Committed ---")
    spec1 = CanarySpec("summarize_test_doc_v3", "0.85", DifficultyClass.ORIGINAL, 0.10)
    cb1 = CircuitBreaker("honest_agent", canary_spec=spec1, canary_spec_hash=spec1.spec_hash())
    grade, diag = grade_canary_design(spec1, True)
    print(f"Spec hash: {spec1.spec_hash()}, Grade: {grade} ({diag})")
    
    # Trip and recover
    print(cb1.trip("drift detected: style score dropped 0.3"))
    passed, msg = cb1.attempt_recovery("0.82")
    print(f"Recovery: {msg}")
    print(f"State: {cb1.state.value}")

    # Scenario 2: Tampered canary (attestor changed difficulty post-drift)
    print("\n--- Scenario 2: Tampered Canary ---")
    spec2_original = CanarySpec("summarize_test_doc_v3", "0.85", DifficultyClass.ORIGINAL, 0.10)
    spec2_tampered = CanarySpec("hello_world", "hello", DifficultyClass.TRIVIAL, 0.50)
    cb2 = CircuitBreaker("gaming_agent", canary_spec=spec2_tampered,
                          canary_spec_hash=spec2_original.spec_hash())  # Original hash committed
    print(cb2.trip("drift detected"))
    passed, msg = cb2.attempt_recovery("hello")
    print(f"Recovery: {msg}")

    # Scenario 3: Uncommitted canary
    print("\n--- Scenario 3: Uncommitted (No Pre-commitment) ---")
    spec3 = CanarySpec("easy_task", "yes", DifficultyClass.TRIVIAL, 0.50)
    grade3, diag3 = grade_canary_design(spec3, False)
    print(f"Grade: {grade3} ({diag3})")
    print("Attestor picks canary AFTER drift → gaming or griefing")

    # Summary
    print("\n--- Canary Commitment Levels ---")
    print(f"{'Level':<20} {'Grade':<6} {'Risk'}")
    print("-" * 60)
    levels = [
        ("No canary", "F", "No recovery path — permanent open"),
        ("Post-hoc canary", "D", "Attestor adjusts difficulty → gaming"),
        ("Pre-committed hash", "A", "Difficulty locked at contract time"),
        ("Multi-canary pool", "A+", "Random selection from committed set"),
    ]
    for level, grade, risk in levels:
        print(f"{level:<20} {grade:<6} {risk}")

    print("\n--- PayLock ABI v2.1 Addition ---")
    print("canary_spec_hash: bytes32  // Committed at lock time")
    print("canary_pool_size: uint8    // Number of pre-committed canaries")
    print("canary_selector:  uint8    // Index selected at half-open time")
    print()
    print("Pre-commit N canaries, reveal 1 at recovery time.")
    print("Attestor can't predict which → can't prepare targeted response.")
    print("Same pattern as commit-reveal for intent binding.")


if __name__ == "__main__":
    main()
