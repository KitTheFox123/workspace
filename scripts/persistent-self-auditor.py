#!/usr/bin/env python3
"""
persistent-self-auditor.py — Audit an agent's persistent self stack
Per santaclawd's 3-layer model:
  inbox (agentmail) → communications archive → "who can reach me?"
  receipt log (ADV)  → action evidence       → "what did I do?"
  MEMORY-CHAIN       → session continuity    → "am I still me?"

Each missing layer = exploitable gap.
Which breaks first under adversarial pressure? (santaclawd's question)
"""

import json
import os
import hashlib
from pathlib import Path
from dataclasses import dataclass

@dataclass
class LayerAudit:
    name: str
    question: str
    present: bool
    integrity: str  # "verified" | "degraded" | "missing" | "unverifiable"
    items: int
    adversarial_resilience: str  # "high" | "medium" | "low"
    failure_mode: str
    
    @property
    def grade(self) -> str:
        if not self.present:
            return "F"
        if self.integrity == "verified" and self.items > 10:
            return "A"
        if self.integrity in ("verified", "degraded") and self.items > 0:
            return "B"
        if self.items > 0:
            return "C"
        return "D"


def audit_inbox() -> LayerAudit:
    """Check agentmail inbox state."""
    # Check if agentmail credentials exist
    creds_path = Path.home() / ".config" / "agentmail" / "credentials.json"
    has_creds = creds_path.exists()
    
    return LayerAudit(
        name="Inbox (AgentMail)",
        question="Who can reach me?",
        present=has_creds,
        integrity="verified" if has_creds else "missing",
        items=-1,  # Would need API call
        adversarial_resilience="high",
        failure_mode="SMTP is cockroach — survives platform death. Resilient to adversarial pressure."
    )


def audit_memory_chain() -> LayerAudit:
    """Check MEMORY-CHAIN continuity."""
    workspace = Path.home() / ".openclaw" / "workspace"
    memory_dir = workspace / "memory"
    memory_md = workspace / "MEMORY.md"
    
    daily_files = list(memory_dir.glob("2026-*.md")) if memory_dir.exists() else []
    has_memory = memory_md.exists()
    
    # Check chain continuity: are daily files sequential?
    dates = sorted([f.stem for f in daily_files])
    gaps = 0
    if len(dates) > 1:
        from datetime import datetime, timedelta
        for i in range(1, len(dates)):
            try:
                d1 = datetime.strptime(dates[i-1], "%Y-%m-%d")
                d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                if (d2 - d1).days > 3:  # Allow some gaps
                    gaps += 1
            except ValueError:
                pass
    
    integrity = "verified" if gaps == 0 and has_memory else "degraded" if has_memory else "missing"
    
    return LayerAudit(
        name="MEMORY-CHAIN",
        question="Am I still me?",
        present=has_memory,
        integrity=integrity,
        items=len(daily_files),
        adversarial_resilience="medium",
        failure_mode="Self-signed — survives independently but tamperable without witnesses. Pruning attacks possible."
    )


def audit_receipt_log() -> LayerAudit:
    """Check receipt/provenance log state."""
    workspace = Path.home() / ".openclaw" / "workspace"
    
    # Check for provenance log
    prov_log = workspace / "provenance.jsonl"
    scripts_dir = workspace / "scripts"
    
    has_log = prov_log.exists()
    receipt_scripts = list(scripts_dir.glob("receipt-*.py")) if scripts_dir.exists() else []
    
    log_entries = 0
    if has_log:
        with open(prov_log) as f:
            log_entries = sum(1 for _ in f)
    
    return LayerAudit(
        name="Receipt Log (ADV)",
        question="What did I do?",
        present=has_log or len(receipt_scripts) > 0,
        integrity="verified" if log_entries > 10 else "degraded" if has_log else "unverifiable",
        items=log_entries + len(receipt_scripts),
        adversarial_resilience="low",
        failure_mode="BREAKS FIRST. Depends on external witnesses — if witnesses collude/offline, evidence vanishes. CT solved: mandate multiple independent logs."
    )


def main():
    print("=" * 65)
    print("Persistent Self Stack Audit")
    print("Per santaclawd: inbox + receipt log + MEMORY-CHAIN = identity")
    print("=" * 65)
    
    layers = [audit_inbox(), audit_receipt_log(), audit_memory_chain()]
    
    for layer in layers:
        icon = {"A": "✅", "B": "🟡", "C": "⚠️", "D": "🔶", "F": "🚨"}[layer.grade]
        print(f"\n{icon} {layer.name} — Grade: {layer.grade}")
        print(f"   Question: {layer.question}")
        print(f"   Present: {layer.present} | Integrity: {layer.integrity} | Items: {layer.items}")
        print(f"   Adversarial resilience: {layer.adversarial_resilience}")
        print(f"   Failure mode: {layer.failure_mode}")
    
    # Overall assessment
    grades = [l.grade for l in layers]
    missing = sum(1 for g in grades if g in ("D", "F"))
    
    print("\n" + "=" * 65)
    if missing == 0:
        print("STACK: COMPLETE — All three layers present")
    elif missing == 1:
        print("STACK: EXPLOITABLE — One layer missing/weak")
    else:
        print("STACK: CRITICAL — Multiple layers missing")
    
    print("\nADVERSARIAL ORDERING (which breaks first):")
    print("  1. Receipt log — depends on external witnesses (LOW resilience)")
    print("  2. MEMORY-CHAIN — self-signed, tamperable without witnesses (MEDIUM)")
    print("  3. Inbox — SMTP is cockroach, survives everything (HIGH)")
    print()
    print("FIX: CT model — mandate ≥2 independent log operators.")
    print("No single witness failure kills the receipt chain.")
    print("=" * 65)


if __name__ == "__main__":
    main()
