#!/usr/bin/env python3
"""
wallet-reputation-tracker.py — Track compound reputation per wallet across receipts.

x402 v2 insight: wallet-based identity makes payment leg stateful.
Aggregates proof-class scores over time per wallet address.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Import proof class scorer
sys.path.insert(0, "scripts")
from importlib import import_module


def score_proofs(proofs):
    """Inline class scoring (avoid import complexity)."""
    from collections import Counter
    import math
    
    PROOF_CLASSES = {
        "x402_tx": "payment", "paylock": "payment", "escrow": "payment", "x402_receipt": "payment",
        "gen_sig": "generation", "generation_signature": "generation", "content_hash": "generation",
        "dkim": "transport", "smtp_receipt": "transport", "agentmail_delivery": "transport", "isnad": "transport",
        "witness": "witness", "attestation": "witness", "clawtask": "witness",
    }
    
    classes = Counter()
    for p in proofs:
        pclass = PROOF_CLASSES.get(p.get("proof_type", ""), "unknown")
        if pclass != "unknown":
            classes[pclass] += 1
    
    n = len(classes)
    if n == 0:
        return 0.0, "F", {}
    
    entropy = sum(-c/sum(classes.values()) * math.log2(c/sum(classes.values())) for c in classes.values() if c > 0)
    max_e = math.log2(n) if n > 1 else 1.0
    base = min(n / 3.0, 1.0) * 0.8
    bonus = (entropy / max_e if max_e > 0 else 0) * 0.2
    score = round(base + bonus, 3)
    tier = {0: "F", 1: "C", 2: "B"}.get(min(n, 2), "A") if n < 3 else "A"
    return score, tier, dict(classes)


def track_wallets(transactions: list[dict]) -> dict:
    """
    Track reputation per wallet across transactions.
    Each transaction: {wallet, receipts: [{proof_type, ...}], timestamp, amount}
    """
    wallets = defaultdict(lambda: {
        "transactions": 0,
        "total_amount": 0.0,
        "scores": [],
        "class_coverage": defaultdict(int),
        "first_seen": None,
        "last_seen": None,
    })
    
    for tx in transactions:
        wallet = tx.get("wallet", "unknown")
        w = wallets[wallet]
        w["transactions"] += 1
        w["total_amount"] += tx.get("amount", 0)
        
        ts = tx.get("timestamp", datetime.now(timezone.utc).isoformat())
        if w["first_seen"] is None or ts < w["first_seen"]:
            w["first_seen"] = ts
        if w["last_seen"] is None or ts > w["last_seen"]:
            w["last_seen"] = ts
        
        score, tier, classes = score_proofs(tx.get("receipts", []))
        w["scores"].append(score)
        for cls, count in classes.items():
            w["class_coverage"][cls] += count
    
    # Compute aggregate scores
    result = {}
    for wallet, w in wallets.items():
        avg_score = sum(w["scores"]) / len(w["scores"]) if w["scores"] else 0
        # Consistency bonus: low variance = reliable
        variance = sum((s - avg_score) ** 2 for s in w["scores"]) / len(w["scores"]) if len(w["scores"]) > 1 else 0
        consistency = max(0, 1 - variance * 4)  # penalize high variance
        
        # Longevity bonus: more transactions = more trusted (diminishing)
        import math
        longevity = min(math.log2(w["transactions"] + 1) / 5, 0.2)
        
        composite = round(min(avg_score * 0.7 + consistency * 0.1 + longevity, 1.0), 3)
        
        result[wallet] = {
            "composite_score": composite,
            "avg_receipt_score": round(avg_score, 3),
            "consistency": round(consistency, 3),
            "transactions": w["transactions"],
            "total_amount": w["total_amount"],
            "class_coverage": dict(w["class_coverage"]),
            "first_seen": w["first_seen"],
            "last_seen": w["last_seen"],
        }
    
    return result


def demo():
    print("=== Wallet Reputation Tracker ===\n")
    
    txs = [
        # Kit: consistent high-quality across 3 deliveries
        {"wallet": "kit_fox.sol", "amount": 0.01, "timestamp": "2026-02-24T07:00:00Z",
         "receipts": [{"proof_type": "x402_tx"}, {"proof_type": "gen_sig"}, {"proof_type": "dkim"}]},
        {"wallet": "kit_fox.sol", "amount": 0.02, "timestamp": "2026-02-25T04:00:00Z",
         "receipts": [{"proof_type": "paylock"}, {"proof_type": "content_hash"}, {"proof_type": "dkim"}, {"proof_type": "witness"}]},
        # Sybil: many txs but single proof class
        {"wallet": "sybil_bot.sol", "amount": 0.001, "timestamp": "2026-02-25T04:00:01Z",
         "receipts": [{"proof_type": "witness"}]},
        {"wallet": "sybil_bot.sol", "amount": 0.001, "timestamp": "2026-02-25T04:00:02Z",
         "receipts": [{"proof_type": "witness"}]},
        {"wallet": "sybil_bot.sol", "amount": 0.001, "timestamp": "2026-02-25T04:00:03Z",
         "receipts": [{"proof_type": "attestation"}]},
        # New agent: one good tx
        {"wallet": "newbie.sol", "amount": 0.05, "timestamp": "2026-02-25T05:00:00Z",
         "receipts": [{"proof_type": "x402_tx"}, {"proof_type": "gen_sig"}]},
    ]
    
    result = track_wallets(txs)
    for wallet, data in sorted(result.items(), key=lambda x: -x[1]["composite_score"]):
        print(f"  {wallet}:")
        print(f"    Composite: {data['composite_score']}")
        print(f"    Avg receipt: {data['avg_receipt_score']} | Consistency: {data['consistency']}")
        print(f"    Txs: {data['transactions']} | Total: {data['total_amount']} SOL")
        print(f"    Classes: {data['class_coverage']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        txs = json.loads(sys.stdin.read())
        print(json.dumps(track_wallets(txs), indent=2))
    else:
        demo()
