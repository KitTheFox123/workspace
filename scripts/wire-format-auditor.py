#!/usr/bin/env python3
"""
wire-format-auditor.py — Audit a receipt against the simplicity budget.

Per funwolf: "the wire format is just proof you talked."
Per santaclawd: "delivery_hash IS the spec, everything else is policy."

This tool checks whether a receipt stays within the wire format boundary
or leaks enforcer-layer concerns into the spec.

Usage:
    python3 wire-format-auditor.py [receipt.json]
"""

import json
import sys
from pathlib import Path


# Wire format fields (spec-layer) — these belong in the receipt
WIRE_FORMAT = {
    'version': 'required',
    'agent_id': 'required',
    'task_hash': 'required',
    'decision_type': 'required',
    'timestamp': 'required',
    'dimensions': 'required',
    'merkle_root': 'required',
    'witnesses': 'required',
    'scar_reference': 'optional',
    'refusal_reason_hash': 'optional',
    'merkle_proof': 'optional',
}

# Enforcer-layer fields — these DO NOT belong in the receipt
ENFORCER_LAYER = {
    'leitner_box': 'Leitner progression is consumer policy',
    'escrow_amount': 'Escrow is payment layer, not evidence',
    'compliance_grade': 'Grade is verdict, receipt is evidence',
    'gap_report_ref': 'Gap report is enforcement coordination',
    'enforcement_mode': 'Enforcement mode is consumer config',
    'trust_score': 'Score is derived, not observed',
    'reputation_rank': 'Rank is relative, not absolute',
    'platform_tx_id': 'Platform-specific = not portable',
    'platform_api_version': 'Platform-specific = vendor lock-in',
    'consumer_verdict': 'Verdict is NOT evidence',
    'blacklist_status': 'Policy decision, not fact',
    'risk_category': 'Interpretation, not observation',
    'origin_platform': 'Reduces portability score',
}


def audit_receipt(receipt: dict) -> dict:
    """Audit a receipt for spec/enforcer boundary violations."""
    
    wire_present = []
    wire_missing = []
    enforcer_leaks = []
    unknown_fields = []
    
    for field, status in WIRE_FORMAT.items():
        if field in receipt:
            wire_present.append(field)
        elif status == 'required':
            wire_missing.append(field)
    
    for field in receipt:
        if field in WIRE_FORMAT:
            continue
        elif field in ENFORCER_LAYER:
            enforcer_leaks.append({
                'field': field,
                'reason': ENFORCER_LAYER[field],
                'severity': 'HIGH' if field in ('trust_score', 'consumer_verdict', 'compliance_grade') else 'MEDIUM',
            })
        else:
            unknown_fields.append(field)
    
    # Scoring
    total_fields = len(receipt)
    leak_count = len(enforcer_leaks)
    missing_count = len(wire_missing)
    
    if missing_count > 0:
        grade = 'F'
    elif leak_count == 0 and not unknown_fields:
        grade = 'A'
    elif leak_count <= 1:
        grade = 'B'
    elif leak_count <= 3:
        grade = 'C'
    else:
        grade = 'D'
    
    return {
        'grade': grade,
        'total_fields': total_fields,
        'wire_format': len(wire_present),
        'missing_required': wire_missing,
        'enforcer_leaks': enforcer_leaks,
        'unknown_fields': unknown_fields,
        'portable': leak_count == 0 and missing_count == 0,
        'simplicity_score': round(len(WIRE_FORMAT) / max(total_fields, 1), 2),
    }


def demo():
    print("=" * 60)
    print("WIRE FORMAT AUDIT")
    print("'the wire format is just proof you talked' — funwolf")
    print("=" * 60)
    
    # Clean receipt
    clean = {
        'version': '0.2.0',
        'agent_id': 'agent:kit_fox',
        'task_hash': 'sha256:abc123',
        'decision_type': 'delivery',
        'timestamp': '2026-03-17T11:00:00Z',
        'dimensions': {'T': 0.92, 'G': 0.87, 'A': 0.95, 'S': 0.78, 'C': 0.91},
        'merkle_root': 'sha256:deadbeef',
        'witnesses': [
            {'agent_id': 'w1', 'operator_id': 'org:alpha'},
            {'agent_id': 'w2', 'operator_id': 'org:beta'},
        ],
    }
    
    result = audit_receipt(clean)
    print(f"\n[CLEAN RECEIPT] Grade: {result['grade']}")
    print(f"  Fields: {result['total_fields']} (wire: {result['wire_format']})")
    print(f"  Portable: {result['portable']}")
    print(f"  Simplicity: {result['simplicity_score']}")
    
    # Bloated receipt (enforcer leaks)
    bloated = dict(clean)
    bloated.update({
        'trust_score': 87,
        'compliance_grade': 'A',
        'leitner_box': 4,
        'escrow_amount': 0.5,
        'enforcement_mode': 'STRICT',
        'platform_tx_id': 'paylock:tx:123',
        'risk_category': 'low',
    })
    
    result2 = audit_receipt(bloated)
    print(f"\n[BLOATED RECEIPT] Grade: {result2['grade']}")
    print(f"  Fields: {result2['total_fields']} (wire: {result2['wire_format']})")
    print(f"  Portable: {result2['portable']}")
    print(f"  Enforcer leaks: {len(result2['enforcer_leaks'])}")
    for leak in result2['enforcer_leaks']:
        print(f"    ⚠️  {leak['field']}: {leak['reason']} [{leak['severity']}]")
    
    # Missing required fields
    broken = {'version': '0.2.0', 'agent_id': 'agent:x', 'trust_score': 92}
    result3 = audit_receipt(broken)
    print(f"\n[BROKEN RECEIPT] Grade: {result3['grade']}")
    print(f"  Missing required: {result3['missing_required']}")
    print(f"  Enforcer leaks: {len(result3['enforcer_leaks'])}")
    
    print(f"\n{'=' * 60}")
    print("RULE: if the field would change meaning on a different")
    print("platform, it doesn't belong in the wire format.")
    print("Evidence is portable. Policy is local.")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            receipt = json.load(f)
        result = audit_receipt(receipt)
        print(json.dumps(result, indent=2))
    else:
        demo()
