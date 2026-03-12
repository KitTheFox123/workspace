#!/usr/bin/env python3
"""heartbeat-risk-audit.py — Single-command risk score for each heartbeat.

Combines scope freshness (CT-inspired TTL check) with imagination inflation
detection (Garry 1996: stale scope re-reading inflates confidence).

Reads HEARTBEAT.md as scope document, compares against recent actions in
daily log, outputs risk score + recommendations.

Usage:
    python3 scripts/heartbeat-risk-audit.py [--scope HEARTBEAT.md] [--log memory/2026-03-07.md]
"""

import argparse
import hashlib
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def extract_scope_items(heartbeat_text: str) -> list[str]:
    """Extract actionable items from HEARTBEAT.md."""
    items = []
    for line in heartbeat_text.splitlines():
        line = line.strip()
        # Match checklist items, numbered items, or imperative sentences
        if re.match(r'^[-*]\s*\[.\]', line) or re.match(r'^\d+\.', line):
            items.append(line)
        elif any(line.lower().startswith(v) for v in ['check ', 'post ', 'build ', 'update ', 'reply ', 'search ']):
            items.append(line)
    return items


def extract_actions_from_log(log_text: str) -> list[str]:
    """Extract performed actions from daily log."""
    actions = []
    for line in log_text.splitlines():
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            actions.append(line[2:])
        elif re.match(r'^\d+\.', line):
            actions.append(line)
    return actions


def scope_freshness_score(heartbeat_path: str) -> dict:
    """Check how recently the scope document was modified."""
    p = Path(heartbeat_path).expanduser()
    if not p.exists():
        return {"score": 0.0, "detail": "No scope document found", "risk": "CRITICAL"}

    mtime = p.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    file_hash = hashlib.sha256(p.read_bytes()).hexdigest()[:12]

    if age_hours < 1:
        risk, score = "LOW", 1.0
    elif age_hours < 6:
        risk, score = "LOW", 0.9
    elif age_hours < 24:
        risk, score = "MODERATE", 0.7
    elif age_hours < 72:
        risk, score = "HIGH", 0.4
    else:
        risk, score = "CRITICAL", 0.1

    return {
        "score": score,
        "age_hours": round(age_hours, 1),
        "hash": file_hash,
        "risk": risk,
        "detail": f"Scope document {age_hours:.1f}h old (hash: {file_hash})"
    }


def imagination_inflation_score(scope_items: list[str], actions: list[str]) -> dict:
    """Detect if agent is acting on scope items not actually in current scope.

    Garry et al 1996: imagining events inflates belief they occurred.
    Re-reading old scope without renewal = inflated confidence in stale permissions.
    """
    if not scope_items:
        return {"score": 0.5, "risk": "UNKNOWN", "detail": "No scope items to check"}

    # Extract key terms from scope
    scope_terms = set()
    for item in scope_items:
        words = re.findall(r'\b[a-z]{4,}\b', item.lower())
        scope_terms.update(words)

    # Check actions against scope terms
    in_scope = 0
    out_of_scope = 0
    novel_terms = []

    for action in actions:
        action_words = set(re.findall(r'\b[a-z]{4,}\b', action.lower()))
        overlap = action_words & scope_terms
        novel = action_words - scope_terms - {'heartbeat', 'checked', 'updated', 'posted', 'replied'}
        if overlap:
            in_scope += 1
        if len(novel) > 3:
            out_of_scope += 1
            novel_terms.extend(list(novel)[:3])

    total = in_scope + out_of_scope
    if total == 0:
        return {"score": 1.0, "risk": "LOW", "detail": "No actions to evaluate"}

    ratio = in_scope / total
    if ratio > 0.8:
        risk = "LOW"
    elif ratio > 0.5:
        risk = "MODERATE"
    else:
        risk = "HIGH"

    return {
        "score": round(ratio, 2),
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "novel_terms": novel_terms[:10],
        "risk": risk,
        "detail": f"{in_scope}/{total} actions within scope ({ratio:.0%})"
    }


def checklist_coverage(scope_items: list[str], actions: list[str]) -> dict:
    """What fraction of required scope items were actually performed?"""
    if not scope_items:
        return {"score": 0.0, "risk": "UNKNOWN", "detail": "No checklist"}

    # Simple keyword matching
    covered = 0
    uncovered = []
    for item in scope_items:
        item_lower = item.lower()
        found = any(
            any(kw in action.lower() for kw in re.findall(r'\b[a-z]{5,}\b', item_lower)[:3])
            for action in actions
        ) if actions else False
        if found:
            covered += 1
        else:
            uncovered.append(item[:60])

    ratio = covered / len(scope_items) if scope_items else 0
    if ratio > 0.8:
        risk = "LOW"
    elif ratio > 0.5:
        risk = "MODERATE"
    else:
        risk = "HIGH"

    return {
        "score": round(ratio, 2),
        "covered": covered,
        "total": len(scope_items),
        "uncovered": uncovered[:5],
        "risk": risk,
        "detail": f"{covered}/{len(scope_items)} scope items covered ({ratio:.0%})"
    }


def compute_overall(freshness: dict, inflation: dict, coverage: dict) -> dict:
    """Weighted combination: freshness 30%, inflation 30%, coverage 40%."""
    w_fresh, w_infl, w_cov = 0.3, 0.3, 0.4
    overall = (
        freshness["score"] * w_fresh +
        inflation["score"] * w_infl +
        coverage["score"] * w_cov
    )

    if overall > 0.8:
        risk = "LOW"
    elif overall > 0.6:
        risk = "MODERATE"
    elif overall > 0.4:
        risk = "HIGH"
    else:
        risk = "CRITICAL"

    return {
        "overall_score": round(overall, 3),
        "risk": risk,
        "basis_points": int(overall * 10000),
        "components": {
            "freshness": {"weight": w_fresh, "score": freshness["score"], "risk": freshness["risk"]},
            "inflation": {"weight": w_infl, "score": inflation["score"], "risk": inflation["risk"]},
            "coverage": {"weight": w_cov, "score": coverage["score"], "risk": coverage["risk"]},
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Heartbeat risk audit")
    parser.add_argument("--scope", default=os.path.expanduser("~/.openclaw/workspace/HEARTBEAT.md"))
    parser.add_argument("--log", default=None, help="Daily log file (auto-detects today's)")
    args = parser.parse_args()

    if args.log is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        args.log = os.path.expanduser(f"~/.openclaw/workspace/memory/{today}.md")

    print(f"Scope: {args.scope}")
    print(f"Log:   {args.log}")
    print()

    scope_text = load_file(args.scope)
    log_text = load_file(args.log)

    scope_items = extract_scope_items(scope_text)
    actions = extract_actions_from_log(log_text)

    print(f"Scope items: {len(scope_items)}")
    print(f"Actions logged: {len(actions)}")
    print()

    freshness = scope_freshness_score(args.scope)
    inflation = imagination_inflation_score(scope_items, actions)
    coverage = checklist_coverage(scope_items, actions)
    overall = compute_overall(freshness, inflation, coverage)

    print("=" * 50)
    print(f"HEARTBEAT RISK AUDIT")
    print("=" * 50)
    print(f"\n1. Scope Freshness:      {freshness['risk']:>10}  ({freshness['score']:.2f})")
    print(f"   {freshness['detail']}")
    print(f"\n2. Imagination Inflation: {inflation['risk']:>9}  ({inflation['score']:.2f})")
    print(f"   {inflation['detail']}")
    print(f"\n3. Checklist Coverage:   {coverage['risk']:>10}  ({coverage['score']:.2f})")
    print(f"   {coverage['detail']}")

    if coverage.get("uncovered"):
        print(f"   Uncovered:")
        for item in coverage["uncovered"]:
            print(f"     - {item}")

    print(f"\n{'=' * 50}")
    print(f"OVERALL: {overall['risk']}  ({overall['overall_score']:.3f} = {overall['basis_points']} bps)")
    print(f"{'=' * 50}")

    return 0 if overall["risk"] in ("LOW", "MODERATE") else 1


if __name__ == "__main__":
    sys.exit(main())
