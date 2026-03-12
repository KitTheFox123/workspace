#!/usr/bin/env python3
"""
execution-trace-commit.py — Execution trace commitment for scoring oracle attestation.

Based on:
- Castillo et al (TU Berlin, ICBC 2025): Trusted Compute Units — chained verifiable computation
- santaclawd: "do we need an execution trace commitment? attestation lineage on the scoring run itself"
- Wallach (LangSec SPW25): parser = fractal attack surface

The v3 problem: rule_hash proves WHAT scoring rule was committed.
It does NOT prove HOW the scoring was executed.
Two VMs, same bytecode, different results = undetected divergence.

Execution trace = hash(inputs, intermediate_states, output, environment).
Deterministic scoring → trace is reproducible → disputes resolvable.
Non-deterministic (LLM) → trace proves process, not correctness.

This tool: commit execution traces, detect replay divergence, grade auditability.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionStep:
    step_id: int
    operation: str
    input_hash: str
    output_hash: str
    duration_ms: float
    environment: str  # VM/runtime identifier


@dataclass
class ExecutionTrace:
    trace_id: str
    rule_hash: str
    input_hash: str
    output_hash: str
    steps: list[ExecutionStep] = field(default_factory=list)
    environment_hash: str = ""
    timestamp: float = 0.0
    
    def commit_hash(self) -> str:
        """Hash the entire trace for commitment."""
        content = json.dumps({
            "rule_hash": self.rule_hash,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "steps": [
                {"op": s.operation, "in": s.input_hash, "out": s.output_hash}
                for s in self.steps
            ],
            "env": self.environment_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_deterministic(self) -> bool:
        """Check if all steps have reproducible outputs."""
        # LLM steps are non-deterministic by nature
        return not any("llm" in s.operation.lower() for s in self.steps)


@dataclass
class ReplayResult:
    original_trace: str
    replay_trace: str
    match: bool
    divergence_step: Optional[int] = None
    diagnosis: str = ""


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def simulate_scoring_trace(rule: str, inputs: dict, env: str,
                            deterministic: bool = True) -> ExecutionTrace:
    """Simulate a scoring execution with trace."""
    trace = ExecutionTrace(
        trace_id=hash_content(f"{rule}{json.dumps(inputs)}{time.time()}"),
        rule_hash=hash_content(rule),
        input_hash=hash_content(json.dumps(inputs, sort_keys=True)),
        output_hash="",
        environment_hash=hash_content(env),
        timestamp=time.time(),
    )

    # Step 1: Parse input
    step1_out = hash_content(f"parsed_{json.dumps(inputs)}")
    trace.steps.append(ExecutionStep(1, "parse_input", trace.input_hash, step1_out, 2.0, env))

    # Step 2: Apply rule
    if deterministic:
        step2_out = hash_content(f"scored_{rule}_{step1_out}")
        trace.steps.append(ExecutionStep(2, "apply_rule_deterministic", step1_out, step2_out, 5.0, env))
    else:
        # LLM scoring: non-deterministic
        import random
        step2_out = hash_content(f"llm_scored_{rule}_{step1_out}_{random.random()}")
        trace.steps.append(ExecutionStep(2, "apply_rule_llm", step1_out, step2_out, 150.0, env))

    # Step 3: Format output
    step3_out = hash_content(f"output_{step2_out}")
    trace.steps.append(ExecutionStep(3, "format_output", step2_out, step3_out, 1.0, env))

    trace.output_hash = step3_out
    return trace


def replay_and_compare(original: ExecutionTrace, replay: ExecutionTrace) -> ReplayResult:
    """Compare two execution traces for divergence."""
    if original.commit_hash() == replay.commit_hash():
        return ReplayResult(original.trace_id, replay.trace_id, True, diagnosis="EXACT_MATCH")

    # Find divergence point
    for i, (orig_step, replay_step) in enumerate(zip(original.steps, replay.steps)):
        if orig_step.output_hash != replay_step.output_hash:
            if "llm" in orig_step.operation.lower():
                return ReplayResult(original.trace_id, replay.trace_id, False, i + 1,
                                     "LLM_NONDETERMINISM")
            elif orig_step.environment != replay_step.environment:
                return ReplayResult(original.trace_id, replay.trace_id, False, i + 1,
                                     "ENVIRONMENT_DIVERGENCE")
            else:
                return ReplayResult(original.trace_id, replay.trace_id, False, i + 1,
                                     "PARSER_GAP")

    return ReplayResult(original.trace_id, replay.trace_id, False, diagnosis="LENGTH_MISMATCH")


def grade_auditability(trace: ExecutionTrace) -> tuple[str, str]:
    """Grade trace auditability."""
    has_env = bool(trace.environment_hash)
    is_det = trace.is_deterministic()
    has_steps = len(trace.steps) >= 2
    has_rule = bool(trace.rule_hash)

    score = sum([has_env, is_det, has_steps, has_rule])
    if score == 4:
        return "A", "FULLY_AUDITABLE"
    elif score == 3:
        if not is_det:
            return "B", "PROCESS_AUDITABLE"  # Can verify process, not output
        return "B", "MOSTLY_AUDITABLE"
    elif score == 2:
        return "C", "PARTIALLY_AUDITABLE"
    else:
        return "F", "OPAQUE"


def main():
    print("=" * 70)
    print("EXECUTION TRACE COMMITMENT")
    print("santaclawd: 'do we need execution trace commitment?'")
    print("Castillo et al (TU Berlin, ICBC 2025): Trusted Compute Units")
    print("=" * 70)

    rule = "brier_score_v1"
    inputs = {"delivery": "test_case_4", "score": 0.92, "scope_hash": "abc123"}

    # Scenario 1: Deterministic scoring, same environment
    print("\n--- Scenario 1: Deterministic, Same Environment ---")
    t1 = simulate_scoring_trace(rule, inputs, "python3.11_linux", True)
    t2 = simulate_scoring_trace(rule, inputs, "python3.11_linux", True)
    result = replay_and_compare(t1, t2)
    grade, diag = grade_auditability(t1)
    print(f"Match: {result.match}, Diagnosis: {result.diagnosis}")
    print(f"Grade: {grade} ({diag})")

    # Scenario 2: Deterministic, different environment (parser gap)
    print("\n--- Scenario 2: Deterministic, Different Environment ---")
    t3 = simulate_scoring_trace(rule, inputs, "python3.11_linux", True)
    t4 = simulate_scoring_trace(rule, inputs, "python3.12_macos", True)
    result2 = replay_and_compare(t3, t4)
    print(f"Match: {result2.match}, Step: {result2.divergence_step}, Diagnosis: {result2.diagnosis}")

    # Scenario 3: LLM scoring (non-deterministic)
    print("\n--- Scenario 3: LLM Scoring (Non-deterministic) ---")
    t5 = simulate_scoring_trace(rule, inputs, "python3.11_linux", False)
    t6 = simulate_scoring_trace(rule, inputs, "python3.11_linux", False)
    result3 = replay_and_compare(t5, t6)
    grade3, diag3 = grade_auditability(t5)
    print(f"Match: {result3.match}, Step: {result3.divergence_step}, Diagnosis: {result3.diagnosis}")
    print(f"Grade: {grade3} ({diag3})")

    # Summary
    print("\n--- Execution Trace Commitment Levels ---")
    print(f"{'Level':<12} {'Proves':<30} {'Limitation'}")
    print("-" * 70)
    levels = [
        ("v1", "rule_hash: WHAT rule was committed", "Not how it was executed"),
        ("v2", "JCS+multihash: canonical form", "Not execution equivalence"),
        ("v3", "trace_hash: execution steps", "Not output correctness (LLM)"),
        ("v4", "TEE/zkVM: verifiable execution", "Not semantic correctness"),
    ]
    for level, proves, limit in levels:
        print(f"{level:<12} {proves:<30} {limit}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'rule_hash proves content identity, not execution equivalence'")
    print()
    print("Deterministic scoring: trace = reproducible → disputes resolvable.")
    print("LLM scoring: trace proves PROCESS, not correctness.")
    print("The gap: two honest VMs can produce different outputs from same input.")
    print()
    print("TCU (Castillo et al): TEE + zkVM chain. Each step verifiable.")
    print("For agents: execution trace commitment = v3 minimum.")
    print("Hash(inputs + steps + environment + output) per scoring run.")
    print("Replay divergence = either parser gap or environment drift.")
    print("Neither proves the SCORE is right — only that the process was followed.")


if __name__ == "__main__":
    main()
