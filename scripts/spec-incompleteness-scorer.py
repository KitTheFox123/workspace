#!/usr/bin/env python3
"""
spec-incompleteness-scorer.py — Measures spec completeness gap in agent deliverables.

Based on:
- santaclawd: "partially verifiable = hash matches but behavior drifts on edge inputs.
  Who bears spec incompleteness risk?"
- TC4: two-gate model (hash match = objective, quality score = subjective)
- Goodhart's Law: optimizing spec ≠ optimizing intent

Three categories:
1. Fully verifiable: hash(output) == hash(expected). Binary.
2. Partially verifiable: structure matches, edge cases diverge.
3. Subjective: "good enough" requires human/oracle judgment.

The gap between gates 1 and 2 = spec incompleteness surface.
Whoever WROTE the spec bears the incompleteness risk.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestCase:
    input_desc: str
    expected: str
    actual: Optional[str] = None
    is_edge: bool = False
    verifiable: bool = True  # Can be checked mechanically?


@dataclass
class DeliverableSpec:
    name: str
    spec_hash: str
    test_suite: list[TestCase] = field(default_factory=list)
    
    def coverage(self) -> float:
        """What fraction of behavior is specified?"""
        if not self.test_suite:
            return 0.0
        return len([t for t in self.test_suite if t.verifiable]) / len(self.test_suite)
    
    def edge_coverage(self) -> float:
        """What fraction of edge cases are specified?"""
        edges = [t for t in self.test_suite if t.is_edge]
        if not edges:
            return 0.0
        return len([t for t in edges if t.verifiable]) / len(edges)
    
    def pass_rate(self) -> float:
        """What fraction of tests pass?"""
        tested = [t for t in self.test_suite if t.actual is not None]
        if not tested:
            return 0.0
        return len([t for t in tested if t.actual == t.expected]) / len(tested)
    
    def incompleteness_surface(self) -> float:
        """The gap between what's specified and what's needed. 0=complete, 1=empty."""
        # Weighted: edge cases matter 2x
        base = 1 - self.coverage()
        edge = 1 - self.edge_coverage()
        return 0.4 * base + 0.6 * edge  # Edge cases weighted heavier
    
    def gate_analysis(self) -> dict:
        """TC4 two-gate analysis."""
        hash_match = self.pass_rate()  # Gate 1: objective
        spec_complete = 1 - self.incompleteness_surface()  # Gate 2: completeness
        
        # The gap between gates
        gap = max(0, hash_match - spec_complete)
        
        if hash_match >= 0.95 and spec_complete >= 0.8:
            grade = "A"
            diagnosis = "WELL_SPECIFIED"
        elif hash_match >= 0.90 and spec_complete >= 0.5:
            grade = "B"
            diagnosis = "ADEQUATELY_SPECIFIED"
        elif hash_match >= 0.80:
            grade = "C"
            diagnosis = "SPEC_INCOMPLETE"
        elif hash_match >= 0.50:
            grade = "D"
            diagnosis = "PARTIALLY_VERIFIABLE"
        else:
            grade = "F"
            diagnosis = "UNVERIFIABLE"
        
        return {
            "gate_1_hash_match": round(hash_match, 3),
            "gate_2_spec_completeness": round(spec_complete, 3),
            "incompleteness_gap": round(gap, 3),
            "grade": grade,
            "diagnosis": diagnosis,
            "risk_bearer": "spec_author" if gap > 0.1 else "deliverer",
        }


def build_scenarios() -> list[DeliverableSpec]:
    """Build example deliverable specs."""
    scenarios = []
    
    # 1. Well-specified: simple function
    well_spec = DeliverableSpec("hash_function", "abc123", [
        TestCase("empty string", "e3b0c442", "e3b0c442"),
        TestCase("hello", "2cf24dba", "2cf24dba"),
        TestCase("unicode input", "expected_hash", "expected_hash", is_edge=True),
        TestCase("null byte", "null_hash", "null_hash", is_edge=True),
        TestCase("max length", "max_hash", "max_hash", is_edge=True),
    ])
    scenarios.append(well_spec)
    
    # 2. Partially verifiable: code that compiles but edge cases fail
    partial = DeliverableSpec("api_endpoint", "def456", [
        TestCase("valid request", "200 OK", "200 OK"),
        TestCase("auth check", "401", "401"),
        TestCase("rate limit", "429", "429"),
        TestCase("malformed JSON", "400", "500", is_edge=True),  # FAILS
        TestCase("concurrent requests", "200", None, is_edge=True, verifiable=False),
        TestCase("timeout behavior", "504", None, is_edge=True, verifiable=False),
    ])
    scenarios.append(partial)
    
    # 3. Subjective: research deliverable (TC4-like)
    subjective = DeliverableSpec("research_report", "ghi789", [
        TestCase("word count > 5000", "true", "true"),
        TestCase("sources >= 10", "true", "true"),
        TestCase("thesis present", "true", "true"),
        TestCase("thesis quality", "good", None, is_edge=False, verifiable=False),
        TestCase("novel insight", "yes", None, is_edge=True, verifiable=False),
        TestCase("counter-arguments", "addressed", None, is_edge=True, verifiable=False),
    ])
    scenarios.append(subjective)
    
    # 4. Goodhart trap: optimizes spec, misses intent
    goodhart = DeliverableSpec("goodhart_trap", "jkl012", [
        TestCase("format correct", "true", "true"),
        TestCase("length >= 1000", "true", "true"),
        TestCase("keywords present", "true", "true"),
        TestCase("actually useful", "true", "false", is_edge=True, verifiable=True),
        TestCase("not plagiarized", "true", None, is_edge=True, verifiable=False),
    ])
    scenarios.append(goodhart)
    
    return scenarios


def main():
    print("=" * 70)
    print("SPEC INCOMPLETENESS SCORER")
    print("santaclawd: 'partially verifiable = hash matches, behavior drifts'")
    print("=" * 70)
    
    print(f"\n{'Spec':<20} {'Gate1':<8} {'Gate2':<8} {'Gap':<8} {'Grade':<6} {'Risk Bearer':<15} {'Diagnosis'}")
    print("-" * 85)
    
    for spec in build_scenarios():
        analysis = spec.gate_analysis()
        print(f"{spec.name:<20} {analysis['gate_1_hash_match']:<8} "
              f"{analysis['gate_2_spec_completeness']:<8} {analysis['incompleteness_gap']:<8} "
              f"{analysis['grade']:<6} {analysis['risk_bearer']:<15} {analysis['diagnosis']}")
    
    print("\n--- Key Insight ---")
    print("santaclawd's three cases:")
    print("  1. Fully verifiable: hash(output)==hash(expected). Risk=deliverer.")
    print("  2. Partially verifiable: structure ok, edges fail. Risk=spec author.")
    print("  3. Subjective: needs oracle. Risk=shared (scoring rule negotiation).")
    print()
    print("The incompleteness surface = gap between gate 1 and gate 2.")
    print("High gate 1, low gate 2 = Goodhart trap (optimizing spec not intent).")
    print("Fix: pre-committed test suite with EDGE CASES, not just happy path.")
    print("TC4 lesson: the disputed contracts were all partially verifiable.")


if __name__ == "__main__":
    main()
