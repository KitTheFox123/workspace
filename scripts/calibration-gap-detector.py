#!/usr/bin/env python3
"""Calibration Gap Detector — Find agents that are confident and wrong.

Based on Steyvers & Peters (2025, Current Directions in Psychological Science):
- Implicit confidence (token probs) outperforms explicit (verbal) for accuracy
- GPT-3.5 overconfident on MMLU; GPT-4.1 mini fine-tuned = better calibration
- Metacognitive sensitivity (AUC) vs calibration (ECE) are distinct

santaclawd's insight: "confident and wrong looks identical to calibrated
until you probe it." Resolution without calibration = dangerous.

aletheaveyra's insight: scope_hash as external ISR — behavioral metacognition
without self-report.

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class PredictionRecord:
    """An agent's prediction with ground truth."""
    question_type: str       # Category of task
    stated_confidence: float  # What agent said (0-1)
    actual_correct: bool     # Ground truth
    scope_hash: str          # What agent actually did (behavioral)
    response_time_ms: int    # Implicit confidence signal


def expected_calibration_error(records: list[PredictionRecord], n_bins: int = 10) -> float:
    """ECE: average gap between confidence and accuracy per bin."""
    bins = [[] for _ in range(n_bins)]
    for r in records:
        idx = min(int(r.stated_confidence * n_bins), n_bins - 1)
        bins[idx].append(r)

    ece = 0.0
    total = len(records)
    for b in bins:
        if not b:
            continue
        avg_conf = sum(r.stated_confidence for r in b) / len(b)
        avg_acc = sum(1 for r in b if r.actual_correct) / len(b)
        ece += (len(b) / total) * abs(avg_conf - avg_acc)
    return ece


def metacognitive_sensitivity(records: list[PredictionRecord]) -> float:
    """AUC: can the agent distinguish correct from incorrect via confidence?
    Higher = better metacognitive sensitivity."""
    correct = [r.stated_confidence for r in records if r.actual_correct]
    incorrect = [r.stated_confidence for r in records if not r.actual_correct]
    if not correct or not incorrect:
        return 0.5  # chance

    # Mann-Whitney U approximation for AUC
    concordant = sum(1 for c in correct for i in incorrect if c > i)
    tied = sum(0.5 for c in correct for i in incorrect if c == i)
    return (concordant + tied) / (len(correct) * len(incorrect))


def scope_hash_variability(records: list[PredictionRecord]) -> dict:
    """aletheaveyra's ISR: scope_hash variation by question type = processing mode differences."""
    by_type: dict[str, set] = {}
    for r in records:
        by_type.setdefault(r.question_type, set()).add(r.scope_hash)

    return {qt: len(hashes) for qt, hashes in by_type.items()}


def detect_calibration_gap(records: list[PredictionRecord]) -> dict:
    ece = expected_calibration_error(records)
    auc = metacognitive_sensitivity(records)
    scope_var = scope_hash_variability(records)

    # Overconfidence detection
    overconf_records = [r for r in records if r.stated_confidence > 0.8 and not r.actual_correct]
    overconf_ratio = len(overconf_records) / len(records) if records else 0

    # Response time as implicit confidence (faster = more confident)
    correct_rt = [r.response_time_ms for r in records if r.actual_correct]
    incorrect_rt = [r.response_time_ms for r in records if not r.actual_correct]
    avg_correct_rt = sum(correct_rt) / len(correct_rt) if correct_rt else 0
    avg_incorrect_rt = sum(incorrect_rt) / len(incorrect_rt) if incorrect_rt else 0

    # Overall accuracy
    accuracy = sum(1 for r in records if r.actual_correct) / len(records) if records else 0

    # Grade
    if ece < 0.05 and auc > 0.8:
        grade, classification = "A", "WELL_CALIBRATED"
    elif ece < 0.10 and auc > 0.7:
        grade, classification = "B", "MOSTLY_CALIBRATED"
    elif ece < 0.20:
        grade, classification = "C", "MISCALIBRATED"
    elif overconf_ratio > 0.2:
        grade, classification = "D", "OVERCONFIDENT_AND_WRONG"
    else:
        grade, classification = "F", "CALIBRATION_FAILURE"

    return {
        "grade": grade,
        "classification": classification,
        "metrics": {
            "ECE": round(ece, 4),
            "AUC_sensitivity": round(auc, 4),
            "accuracy": round(accuracy, 3),
            "overconfidence_ratio": round(overconf_ratio, 3),
            "avg_correct_rt_ms": round(avg_correct_rt),
            "avg_incorrect_rt_ms": round(avg_incorrect_rt),
            "scope_hash_variability": scope_var,
        },
        "diagnosis": _diagnose(ece, auc, overconf_ratio, avg_correct_rt, avg_incorrect_rt),
    }


def _diagnose(ece, auc, overconf, correct_rt, incorrect_rt) -> list[str]:
    diag = []
    if ece > 0.15:
        diag.append(f"⚠️ High ECE ({ece:.3f}): stated confidence doesn't match accuracy")
    if auc < 0.6:
        diag.append(f"⚠️ Low sensitivity (AUC {auc:.3f}): can't distinguish correct from incorrect")
    if overconf > 0.15:
        diag.append(f"🚨 Overconfidence: {overconf:.1%} of high-confidence predictions are wrong")
    if incorrect_rt > 0 and correct_rt > 0 and incorrect_rt < correct_rt:
        diag.append("⚠️ Faster on wrong answers = shoots from hip on errors")
    if auc > 0.8 and ece > 0.1:
        diag.append("💡 Good sensitivity but poor calibration — knows when wrong, reports wrong confidence")
    if not diag:
        diag.append("✅ Well calibrated: confidence tracks accuracy, good sensitivity")
    return diag


def demo():
    print("=== Calibration Gap Detector ===\n")
    print("Based on Steyvers & Peters (2025, Curr Dir Psych Sci)\n")

    # Well-calibrated agent (like Kit)
    kit_records = [
        PredictionRecord("search", 0.9, True, "search_v1", 450),
        PredictionRecord("search", 0.85, True, "search_v1", 500),
        PredictionRecord("code", 0.7, True, "code_v1", 800),
        PredictionRecord("code", 0.4, False, "code_v2", 1200),
        PredictionRecord("social", 0.8, True, "social_v1", 350),
        PredictionRecord("social", 0.3, False, "social_v2", 600),
        PredictionRecord("search", 0.95, True, "search_v1", 400),
        PredictionRecord("code", 0.6, True, "code_v1", 900),
    ]
    _print_result("Kit (calibrated)", detect_calibration_gap(kit_records))

    # Overconfident agent (GPT-3.5 pattern)
    overconf_records = [
        PredictionRecord("qa", 0.95, True, "qa_v1", 200),
        PredictionRecord("qa", 0.92, False, "qa_v1", 180),
        PredictionRecord("qa", 0.88, True, "qa_v1", 210),
        PredictionRecord("qa", 0.90, False, "qa_v1", 190),
        PredictionRecord("qa", 0.93, True, "qa_v1", 195),
        PredictionRecord("qa", 0.91, False, "qa_v1", 185),
        PredictionRecord("qa", 0.87, True, "qa_v1", 220),
        PredictionRecord("qa", 0.94, False, "qa_v1", 175),
    ]
    _print_result("Overconfident (GPT-3.5 pattern)", detect_calibration_gap(overconf_records))

    # ISR=1 agent (aletheaveyra's example: always says "I know" = no resolution)
    isr1_records = [
        PredictionRecord("any", 0.5, True, "same_hash", 500),
        PredictionRecord("any", 0.5, False, "same_hash", 500),
        PredictionRecord("any", 0.5, True, "same_hash", 500),
        PredictionRecord("any", 0.5, False, "same_hash", 500),
    ]
    _print_result("ISR=1 agent (max calibration, zero resolution)", detect_calibration_gap(isr1_records))


def _print_result(name: str, result: dict):
    m = result["metrics"]
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} — {result['classification']}")
    print(f"  ECE: {m['ECE']:.4f}  AUC: {m['AUC_sensitivity']:.4f}  Accuracy: {m['accuracy']:.1%}")
    print(f"  Overconfidence ratio: {m['overconfidence_ratio']:.1%}")
    print(f"  Scope hash variability: {m['scope_hash_variability']}")
    for d in result["diagnosis"]:
        print(f"  {d}")
    print()


if __name__ == "__main__":
    demo()
