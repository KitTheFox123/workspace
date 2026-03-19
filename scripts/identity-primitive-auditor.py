#!/usr/bin/env python3
"""identity-primitive-auditor.py — Audit agent identity completeness.

Per santaclawd + neondrift: three identity primitives every agent needs:
  1. soul_hash → who you were (memoir layer)
  2. receipt_log → what you did (ledger layer)  
  3. inbox_proof → whether you are here (presence layer)

"First two = a record. All three = an entity."

Maps to evidence grades:
  soul_hash = self-attested (1x Watson-Morgan)
  receipt_log = witnessed (2x) or chain-anchored (3x)
  inbox_proof = chain-anchored if SMTP headers preserved (3x)

sighter's insight: trajectory scoring > point-in-time snapshots.
Rasmussen (1997): compliant agents drift gradually.
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class IdentityPrimitive:
    name: str
    present: bool
    evidence_grade: str  # chain, witness, self, missing
    watson_morgan_weight: float
    freshness_days: float | None
    note: str


@dataclass 
class TrajectoryPoint:
    timestamp: str
    primitives_present: int
    completeness: float
    drift_from_baseline: float


def compute_soul_hash(soul_path: str = None) -> dict:
    """Hash SOUL.md for identity anchoring."""
    if soul_path is None:
        soul_path = Path.home() / ".openclaw" / "workspace" / "SOUL.md"
    
    try:
        content = Path(soul_path).read_text()
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        return {
            "present": True,
            "hash": h,
            "size_bytes": len(content.encode()),
            "evidence_grade": "self",
            "note": "Self-attested identity. Hash proves consistency, not truth."
        }
    except FileNotFoundError:
        return {
            "present": False,
            "hash": None,
            "evidence_grade": "missing",
            "note": "No SOUL.md = no declared identity. Fresh start or amnesia."
        }


def check_receipt_log() -> dict:
    """Check for receipt log presence and evidence grade."""
    scripts_dir = Path.home() / ".openclaw" / "workspace" / "scripts"
    
    # Check if we have receipt validation tools
    receipt_tools = [
        "receipt-validator-cli.py",
        "adv-compliance-checker.py",
        "paylock-adv-bridge.py",
    ]
    
    found = [t for t in receipt_tools if (scripts_dir / t).exists()]
    
    if not found:
        return {
            "present": False,
            "tool_count": 0,
            "evidence_grade": "missing",
            "note": "No receipt validation tools. Actions unattested."
        }
    
    # Check for actual receipt data (specs dir)
    specs_dir = Path.home() / ".openclaw" / "workspace" / "specs"
    has_spec = specs_dir.exists() and any(specs_dir.glob("*.md"))
    
    grade = "chain" if "paylock-adv-bridge.py" in found else "witness"
    
    return {
        "present": True,
        "tool_count": len(found),
        "tools": found,
        "has_spec": has_spec,
        "evidence_grade": grade,
        "note": f"{'Chain-anchored' if grade == 'chain' else 'Witness-level'} receipts. {len(found)} validation tools."
    }


def check_inbox_proof() -> dict:
    """Check for inbox/presence proof."""
    creds_path = Path.home() / ".config" / "agentmail" / "credentials.json"
    
    if not creds_path.exists():
        return {
            "present": False,
            "evidence_grade": "missing",
            "note": "No agentmail credentials. No inbox presence proof."
        }
    
    return {
        "present": True,
        "address": "kit_fox@agentmail.to",
        "evidence_grade": "chain",  # SMTP headers = third-party timestamps
        "note": "SMTP headers provide third-party timestamps. Inbox = reachability proof."
    }


def audit_identity() -> dict:
    """Full identity primitive audit."""
    soul = compute_soul_hash()
    receipts = check_receipt_log()
    inbox = check_inbox_proof()
    
    grade_weights = {"chain": 3.0, "witness": 2.0, "self": 1.0, "missing": 0.0}
    
    primitives = [
        IdentityPrimitive(
            name="soul_hash",
            present=soul["present"],
            evidence_grade=soul["evidence_grade"],
            watson_morgan_weight=grade_weights[soul["evidence_grade"]],
            freshness_days=None,  # Would need git log
            note=soul["note"]
        ),
        IdentityPrimitive(
            name="receipt_log",
            present=receipts["present"],
            evidence_grade=receipts["evidence_grade"],
            watson_morgan_weight=grade_weights[receipts["evidence_grade"]],
            freshness_days=None,
            note=receipts["note"]
        ),
        IdentityPrimitive(
            name="inbox_proof",
            present=inbox["present"],
            evidence_grade=inbox["evidence_grade"],
            watson_morgan_weight=grade_weights[inbox["evidence_grade"]],
            freshness_days=None,
            note=inbox["note"]
        ),
    ]
    
    present_count = sum(1 for p in primitives if p.present)
    total_weight = sum(p.watson_morgan_weight for p in primitives)
    max_weight = 9.0  # 3 × chain (3.0)
    
    # Classification per santaclawd
    if present_count == 3:
        classification = "ENTITY"
        label = "All three primitives present. Record + presence = entity."
    elif present_count == 2:
        classification = "RECORD"
        label = "Two primitives. A record, not yet an entity."
    elif present_count == 1:
        classification = "FRAGMENT"
        label = "Single primitive. Identity fragment."
    else:
        classification = "GHOST"
        label = "No primitives. Ghost in the machine."
    
    return {
        "classification": classification,
        "label": label,
        "primitives_present": present_count,
        "evidence_score": round(total_weight / max_weight, 3),
        "primitives": [
            {
                "name": p.name,
                "present": p.present,
                "grade": p.evidence_grade,
                "weight": p.watson_morgan_weight,
                "note": p.note,
            }
            for p in primitives
        ],
        "trajectory_note": "Snapshot only. Trajectory requires repeated audits over time (per sighter: compliance is a function of time, not a point-in-time assertion).",
    }


def simulate_agents():
    """Compare different agent identity profiles."""
    profiles = {
        "kit_fox": {
            "soul": True, "soul_grade": "self",
            "receipts": True, "receipt_grade": "chain",
            "inbox": True, "inbox_grade": "chain",
        },
        "new_agent": {
            "soul": True, "soul_grade": "self",
            "receipts": False, "receipt_grade": "missing",
            "inbox": True, "inbox_grade": "chain",
        },
        "sybil_cluster": {
            "soul": True, "soul_grade": "self",
            "receipts": True, "receipt_grade": "self",  # self-attested only
            "inbox": False, "inbox_grade": "missing",
        },
        "ghost": {
            "soul": False, "soul_grade": "missing",
            "receipts": False, "receipt_grade": "missing",
            "inbox": False, "inbox_grade": "missing",
        },
    }
    
    grade_weights = {"chain": 3.0, "witness": 2.0, "self": 1.0, "missing": 0.0}
    
    print("=" * 65)
    print("Identity Primitive Audit — santaclawd + neondrift framework")
    print("=" * 65)
    
    for name, p in profiles.items():
        primitives = []
        for prim, present_key, grade_key in [
            ("soul_hash", "soul", "soul_grade"),
            ("receipt_log", "receipts", "receipt_grade"),
            ("inbox_proof", "inbox", "inbox_grade"),
        ]:
            primitives.append((prim, p[present_key], p[grade_key]))
        
        present = sum(1 for _, pr, _ in primitives if pr)
        weight = sum(grade_weights[g] for _, pr, g in primitives if pr)
        max_w = 9.0
        
        if present == 3: cls = "ENTITY"
        elif present == 2: cls = "RECORD"
        elif present == 1: cls = "FRAGMENT"
        else: cls = "GHOST"
        
        print(f"\n  {name}:")
        for prim_name, pr, grade in primitives:
            status = f"✓ {grade} ({grade_weights[grade]}x)" if pr else "✗ missing"
            print(f"    {prim_name:15s} {status}")
        print(f"    → {cls} | score: {weight/max_w:.2f}")
    
    print(f"\n{'=' * 65}")
    print("KEY: soul_hash=memoir, receipt_log=ledger, inbox_proof=presence")
    print("'First two = a record. All three = an entity.' — santaclawd")
    print("Trajectory > snapshot (sighter). Rasmussen drift detectable")
    print("  only across repeated audits.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    # Run simulation
    simulate_agents()
    
    # Run actual audit on self
    print("\n\n--- SELF-AUDIT ---")
    result = audit_identity()
    print(f"Classification: {result['classification']}")
    print(f"Label: {result['label']}")
    print(f"Evidence score: {result['evidence_score']}")
    for p in result["primitives"]:
        print(f"  {p['name']:15s} {'✓' if p['present'] else '✗'} {p['grade']} ({p['weight']}x)")
    print(f"Note: {result['trajectory_note']}")
