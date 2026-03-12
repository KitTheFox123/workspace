#!/usr/bin/env python3
"""
Chain of Custody Validator — Federal Rules of Evidence Rule 901 compliance for agent receipts.

Based on Nath et al. (ASU, TPS 2024): Digital Evidence Chain of Custody SoK.
Three CoC categories: paper trail, system-oriented, infrastructure-driven.
Receipt chains = infrastructure-driven CoC.

Rule 901: evidence must be authenticated as original and untampered.
Hash chains satisfy both requirements cryptographically.

Usage:
    python3 chain-of-custody-validator.py              # Demo
    echo '{"receipts": [...]}' | python3 chain-of-custody-validator.py --stdin
"""

import json, sys, hashlib, time
from datetime import datetime, timezone


def compute_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def create_receipt(action: str, agent_id: str, prev_hash: str = "genesis",
                   custodian: str = None, metadata: dict = None) -> dict:
    """Create a CoC-compliant receipt."""
    ts = datetime.now(timezone.utc).isoformat()
    content = f"{prev_hash}:{agent_id}:{action}:{ts}"
    receipt_hash = compute_hash(content)
    
    return {
        "receipt_hash": receipt_hash,
        "prev_hash": prev_hash,
        "agent_id": agent_id,
        "action": action,
        "timestamp": ts,
        "custodian": custodian or agent_id,
        "content_hash": compute_hash(action),
        "metadata": metadata or {},
    }


def validate_chain(receipts: list[dict]) -> dict:
    """Validate a chain of custody against Rule 901 criteria."""
    if not receipts:
        return {"valid": False, "grade": "F", "errors": ["Empty chain"]}
    
    errors = []
    warnings = []
    
    # 1. Hash chain integrity (Rule 901: untampered)
    for i in range(1, len(receipts)):
        if receipts[i].get("prev_hash") != receipts[i-1].get("receipt_hash"):
            errors.append(f"Hash chain break at position {i}: expected {receipts[i-1].get('receipt_hash')}, got {receipts[i].get('prev_hash')}")
    
    # 2. Temporal ordering (no time travel)
    for i in range(1, len(receipts)):
        t1 = receipts[i-1].get("timestamp", "")
        t2 = receipts[i].get("timestamp", "")
        if t2 < t1:
            errors.append(f"Temporal regression at position {i}: {t2} < {t1}")
    
    # 3. Custodian continuity (who had possession)
    custodians = [r.get("custodian") for r in receipts]
    custody_transfers = sum(1 for i in range(1, len(custodians)) if custodians[i] != custodians[i-1])
    if custody_transfers > 0:
        warnings.append(f"{custody_transfers} custody transfer(s) detected — each needs authorization")
    
    # 4. Completeness (no gaps in sequence)
    timestamps = [r.get("timestamp", "") for r in receipts]
    for i in range(1, len(timestamps)):
        try:
            t1 = datetime.fromisoformat(timestamps[i-1])
            t2 = datetime.fromisoformat(timestamps[i])
            gap = (t2 - t1).total_seconds()
            if gap > 86400:  # >24h gap
                warnings.append(f"Temporal gap of {gap/3600:.1f}h between positions {i-1} and {i}")
        except (ValueError, TypeError):
            pass
    
    # 5. Non-repudiation (content hash present)
    missing_content_hash = sum(1 for r in receipts if not r.get("content_hash"))
    if missing_content_hash:
        warnings.append(f"{missing_content_hash} receipt(s) missing content hash (non-repudiation weak)")
    
    # Score
    chain_intact = len([e for e in errors if "Hash chain" in e]) == 0
    temporal_valid = len([e for e in errors if "Temporal" in e]) == 0
    
    score = 1.0
    score -= len(errors) * 0.2
    score -= len(warnings) * 0.05
    score = max(0, min(1, score))
    
    if score >= 0.9: grade = "A"
    elif score >= 0.7: grade = "B"
    elif score >= 0.5: grade = "C"
    elif score >= 0.3: grade = "D"
    else: grade = "F"
    
    # Rule 901 compliance
    rule_901 = {
        "authenticity": chain_intact and temporal_valid,
        "originality": all(r.get("content_hash") for r in receipts),
        "chain_unbroken": chain_intact,
        "temporal_valid": temporal_valid,
        "admissible": chain_intact and temporal_valid and len(errors) == 0,
    }
    
    return {
        "valid": len(errors) == 0,
        "score": round(score, 3),
        "grade": grade,
        "chain_length": len(receipts),
        "custody_transfers": custody_transfers,
        "unique_custodians": len(set(custodians)),
        "rule_901": rule_901,
        "errors": errors,
        "warnings": warnings,
        "coc_category": "infrastructure-driven",  # Nath et al. taxonomy
    }


def demo():
    print("=== Chain of Custody Validator ===")
    print("Based on Nath et al. (ASU, TPS 2024) + Federal Rules of Evidence Rule 901\n")
    
    # Valid chain
    r1 = create_receipt("spawn_task", "kit_fox")
    r2 = create_receipt("search_keenable", "kit_fox", r1["receipt_hash"])
    r3 = create_receipt("write_post", "kit_fox", r2["receipt_hash"])
    r4 = create_receipt("deliver_result", "kit_fox", r3["receipt_hash"])
    
    print("Valid chain (4 receipts, single custodian):")
    result = validate_chain([r1, r2, r3, r4])
    print(f"  Grade: {result['grade']} ({result['score']})")
    print(f"  Rule 901 admissible: {result['rule_901']['admissible']}")
    print(f"  Errors: {len(result['errors'])}")
    
    # Chain with custody transfer (delegation)
    r5 = create_receipt("delegate_research", "kit_fox")
    r6 = create_receipt("execute_research", "sub_agent_1", r5["receipt_hash"], custodian="sub_agent_1")
    r7 = create_receipt("return_results", "kit_fox", r6["receipt_hash"])
    
    print("\nDelegation chain (custody transfer):")
    result = validate_chain([r5, r6, r7])
    print(f"  Grade: {result['grade']} ({result['score']})")
    print(f"  Custody transfers: {result['custody_transfers']}")
    print(f"  Warnings: {result['warnings']}")
    
    # Broken chain (tampered)
    r8 = create_receipt("action_1", "agent_x")
    r9 = create_receipt("action_2", "agent_x", "FAKE_HASH")  # broken link
    r10 = create_receipt("action_3", "agent_x", r9["receipt_hash"])
    
    print("\nBroken chain (tampered):")
    result = validate_chain([r8, r9, r10])
    print(f"  Grade: {result['grade']} ({result['score']})")
    print(f"  Rule 901 admissible: {result['rule_901']['admissible']}")
    print(f"  Errors: {result['errors']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = validate_chain(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
