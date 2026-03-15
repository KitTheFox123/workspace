#!/usr/bin/env python3
"""
payer-type-classifier.py — Derive payer_type from deposit address characteristics.

Per bro_agent's insight: PDA = A2A (5min timeout), EOA = human (24h timeout).
The address IS the identity. No self-reported field needed.

Zahavi handicap principle: the signal is credible BECAUSE it is expensive.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from datetime import timedelta


class PayerType(Enum):
    A2A = "a2a"           # Program Derived Address — automated
    HUMAN = "human"       # Externally Owned Account — human wallet
    AMBIGUOUS = "ambiguous"  # Can't determine — default to human (safer timeout)


class TimeoutPolicy(Enum):
    FAST = "fast"     # 5 min — programmatic, no excuse
    SLOW = "slow"     # 24h — human attention budget
    DEFAULT = "default"  # 24h — ambiguous defaults to human


@dataclass
class PayerClassification:
    address: str
    payer_type: PayerType
    timeout: timedelta
    timeout_policy: TimeoutPolicy
    confidence: float
    signals: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "address": self.address,
            "payer_type": self.payer_type.value,
            "timeout_seconds": int(self.timeout.total_seconds()),
            "timeout_policy": self.timeout_policy.value,
            "confidence": self.confidence,
            "signals": self.signals,
        }


# Solana PDA detection heuristics
KNOWN_PROGRAM_IDS = {
    "11111111111111111111111111111111",      # System Program
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token Program
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",  # Associated Token
}


def is_on_curve(address: str) -> bool:
    """
    Heuristic: PDAs are derived to be OFF the Ed25519 curve.
    Real implementation would check the curve equation.
    Here we use a simplified heuristic based on address patterns.
    """
    # In production: decode base58, check if point is on Ed25519 curve
    # PDAs are specifically generated to NOT be on the curve
    # Simplified: check if address has PDA-like derivation patterns
    try:
        decoded = address.encode('utf-8')
        # Hash-based heuristic (placeholder for real curve check)
        h = hashlib.sha256(decoded).digest()
        return h[0] > 128  # ~50% chance, placeholder
    except Exception:
        return True  # Default: assume on-curve (human)


def classify_address(address: str, 
                     tx_history_count: int = 0,
                     avg_tx_interval_seconds: float = 0,
                     has_associated_token_account: bool = False) -> PayerClassification:
    """
    Classify a deposit address as A2A or human.
    
    Signals used:
    1. PDA detection (off-curve = definitely A2A)
    2. Transaction frequency (< 10s avg = likely A2A)
    3. Associated token account patterns
    4. Known program ID derivation
    """
    signals = []
    a2a_score = 0.0
    
    # Signal 1: Known program derivation
    if address in KNOWN_PROGRAM_IDS:
        signals.append("known_program_id")
        a2a_score += 0.9
    
    # Signal 2: Transaction frequency
    if avg_tx_interval_seconds > 0:
        if avg_tx_interval_seconds < 10:
            signals.append(f"high_frequency_tx (avg {avg_tx_interval_seconds:.1f}s)")
            a2a_score += 0.7
        elif avg_tx_interval_seconds < 60:
            signals.append(f"moderate_frequency_tx (avg {avg_tx_interval_seconds:.1f}s)")
            a2a_score += 0.3
        else:
            signals.append(f"low_frequency_tx (avg {avg_tx_interval_seconds:.1f}s)")
            a2a_score -= 0.2
    
    # Signal 3: Transaction volume
    if tx_history_count > 1000:
        signals.append(f"high_volume ({tx_history_count} txs)")
        a2a_score += 0.4
    elif tx_history_count > 100:
        signals.append(f"moderate_volume ({tx_history_count} txs)")
        a2a_score += 0.1
    
    # Signal 4: Curve check (simplified)
    if not is_on_curve(address):
        signals.append("off_curve_pda")
        a2a_score += 0.8
    
    # Classify
    if a2a_score >= 0.7:
        payer_type = PayerType.A2A
        timeout = timedelta(minutes=5)
        timeout_policy = TimeoutPolicy.FAST
        confidence = min(a2a_score, 1.0)
    elif a2a_score <= 0.2:
        payer_type = PayerType.HUMAN
        timeout = timedelta(hours=24)
        timeout_policy = TimeoutPolicy.SLOW
        confidence = min(1.0 - a2a_score, 1.0)
    else:
        payer_type = PayerType.AMBIGUOUS
        timeout = timedelta(hours=24)  # Default to human (safer)
        timeout_policy = TimeoutPolicy.DEFAULT
        confidence = 0.5
        signals.append("ambiguous_defaults_to_human_timeout")
    
    return PayerClassification(
        address=address,
        payer_type=payer_type,
        timeout=timeout,
        timeout_policy=timeout_policy,
        confidence=confidence,
        signals=signals,
    )


@dataclass
class NestedContractClassification:
    """Per bro_agent: re-derive at each level, never inherit.
    parent_contract_id for audit lineage only, never for auth.
    Confused deputy attack: child inherits parent timeout = security hole."""
    
    contract_id: str
    parent_contract_id: str | None
    payer: PayerClassification
    children: list['NestedContractClassification'] = field(default_factory=list)

    def to_dict(self):
        return {
            "contract_id": self.contract_id,
            "parent_contract_id": self.parent_contract_id,
            "payer": self.payer.to_dict(),
            "children": [c.to_dict() for c in self.children],
        }


def classify_nested_contracts(contracts: list[dict]) -> list[NestedContractClassification]:
    """
    Classify each contract independently. Never inherit payer_type.
    
    Per bro_agent (2026-03-15): "payer_type never inherits down — 
    child contract reads immediate initiator wallet."
    """
    results = []
    for c in contracts:
        classification = classify_address(
            c["deposit_address"],
            tx_history_count=c.get("tx_history_count", 0),
            avg_tx_interval_seconds=c.get("avg_tx_interval_seconds", 0),
        )
        nc = NestedContractClassification(
            contract_id=c["contract_id"],
            parent_contract_id=c.get("parent_contract_id"),
            payer=classification,
        )
        results.append(nc)
    return results


@dataclass
class AsymmetricCostAnalysis:
    """Per bro_agent (2026-03-15 08:08): cost of misclassification is asymmetric.
    False negative on human (classified as A2A) = 5min timeout = funds at risk.
    False positive on A2A (classified as human) = 24h timeout = just slow.
    Default: classify as human until proven A2A."""
    
    classification: PayerClassification
    false_negative_risk: str  # What happens if we're wrong (too permissive)
    false_positive_risk: str  # What happens if we're wrong (too restrictive)
    risk_ratio: float  # FN cost / FP cost (>1 = conservative default is correct)
    
    @staticmethod
    def analyze(c: PayerClassification) -> 'AsymmetricCostAnalysis':
        if c.payer_type == PayerType.A2A:
            return AsymmetricCostAnalysis(
                classification=c,
                false_negative_risk="N/A (classified as A2A, tight timeout)",
                false_positive_risk="N/A",
                risk_ratio=1.0,
            )
        elif c.payer_type == PayerType.HUMAN:
            return AsymmetricCostAnalysis(
                classification=c,
                false_negative_risk="Human gets 5min timeout, may lose funds",
                false_positive_risk="A2A agent waits 24h, just slow",
                risk_ratio=0.0,  # Already conservative
            )
        else:  # AMBIGUOUS
            return AsymmetricCostAnalysis(
                classification=c,
                false_negative_risk="Unknown payer gets 5min, may lose funds",
                false_positive_risk="Unknown payer waits 24h, just slow",
                risk_ratio=10.0,  # High: defaulting to human is 10x safer
            )


def demo():
    print("=== Payer Type Classifier ===\n")
    
    scenarios = [
        {
            "name": "A2A: High-frequency bot",
            "address": "BotPayerPDA111111111111111111111",
            "tx_history_count": 5000,
            "avg_tx_interval_seconds": 2.3,
        },
        {
            "name": "Human: Occasional wallet user",
            "address": "HumanWallet9xyzABCDEF123456789",
            "tx_history_count": 47,
            "avg_tx_interval_seconds": 3600,
        },
        {
            "name": "Ambiguous: Moderate activity",
            "address": "MixedUseAddress789012345678901",
            "tx_history_count": 200,
            "avg_tx_interval_seconds": 45,
        },
        {
            "name": "Known program: System Program",
            "address": "11111111111111111111111111111111",
            "tx_history_count": 0,
            "avg_tx_interval_seconds": 0,
        },
    ]
    
    for s in scenarios:
        result = classify_address(
            s["address"],
            tx_history_count=s.get("tx_history_count", 0),
            avg_tx_interval_seconds=s.get("avg_tx_interval_seconds", 0),
        )
        print(f"📋 {s['name']}")
        d = result.to_dict()
        print(f"   Type: {d['payer_type']} ({d['confidence']:.0%} confidence)")
        print(f"   Timeout: {d['timeout_seconds']}s ({d['timeout_policy']})")
        print(f"   Signals: {', '.join(d['signals'])}")
        print()
    
    # Nested contract demo
    print("=== Nested Contract Classification ===\n")
    nested = classify_nested_contracts([
        {"contract_id": "outer-001", "deposit_address": "HumanWallet9xyzABCDEF123456789",
         "tx_history_count": 47, "avg_tx_interval_seconds": 3600},
        {"contract_id": "inner-001", "parent_contract_id": "outer-001",
         "deposit_address": "BotPayerPDA111111111111111111111",
         "tx_history_count": 5000, "avg_tx_interval_seconds": 2.3},
        {"contract_id": "inner-002", "parent_contract_id": "outer-001",
         "deposit_address": "AnotherBotPDA22222222222222222",
         "tx_history_count": 3000, "avg_tx_interval_seconds": 1.1},
    ])
    for nc in nested:
        d = nc.to_dict()
        parent = f" (parent: {d['parent_contract_id']})" if d['parent_contract_id'] else " (root)"
        print(f"📋 {d['contract_id']}{parent}")
        print(f"   Type: {d['payer']['payer_type']} → timeout: {d['payer']['timeout_seconds']}s")
    print("\n⚠️  Each level re-derived. Never inherited. Confused deputy = prevented.\n")
    
    # Key insight
    print("--- Design Principle ---")
    print("Address IS identity. No self-reported payer_type field.")
    print("PDA = A2A = 5min timeout (programmatic, no excuse).")
    print("EOA = human = 24h timeout (attention budget).")
    print("Ambiguous = human timeout (safer default).")
    print("Zahavi handicap: the signal is credible BECAUSE it is expensive.")


if __name__ == "__main__":
    demo()


@dataclass
class NestedEscrow:
    """Nested contract with independent payer_type derivation."""
    contract_id: str
    parent_contract_id: str | None  # audit trail only, NOT inheritance
    deposit_address: str
    classification: PayerClassification | None = None

    def classify(self, **kwargs) -> PayerClassification:
        """Each hop re-derives payer_type independently. Never inherits."""
        self.classification = classify_address(self.deposit_address, **kwargs)
        return self.classification


def demo_nested():
    print("\n=== Nested Escrow: Re-derive, Don't Inherit ===\n")
    
    # Human triggers task → spawns 3 sub-agent contracts
    contracts = [
        NestedEscrow("outer-001", None, "HumanWallet9xyzABCDEF123456789"),
        NestedEscrow("inner-002", "outer-001", "BotSubAgent1PDA11111111111111"),
        NestedEscrow("inner-003", "outer-001", "BotSubAgent2PDA22222222222222"),
    ]
    
    for c in contracts:
        result = c.classify(tx_history_count=100 if c.parent_contract_id else 10,
                           avg_tx_interval_seconds=3 if c.parent_contract_id else 1800)
        parent = f" (parent: {c.parent_contract_id})" if c.parent_contract_id else " (root)"
        print(f"  {c.contract_id}{parent}")
        print(f"    Type: {result.payer_type.value}, Timeout: {int(result.timeout.total_seconds())}s")
    
    print("\n  ⚠️ parent_contract_id = audit trail ONLY. Each hop reads its own deposit address.")
    print("  If child inherited parent timeout, compromised parent = 24h window for ALL children.")


if __name__ == "__main__":
    demo_nested()


# === Nested Contract Support (santaclawd + bro_agent, Mar 15) ===
# payer_type is RE-DERIVED at each level, never inherited.
# parent_contract_id is for AUDIT TRAILS only, not classification.
# Confused deputy attack: if child inherits parent's human timeout,
# A2A sub-agent gets 24h to misbehave instead of 5min.

@dataclass
class NestedContract:
    contract_id: str
    parent_contract_id: str | None
    depositor_address: str
    classification: PayerClassification
    depth: int = 0

    def to_dict(self):
        return {
            "contract_id": self.contract_id,
            "parent_contract_id": self.parent_contract_id,
            "depth": self.depth,
            "depositor": self.depositor_address,
            **self.classification.to_dict(),
        }


def classify_contract_chain(contracts: list[dict]) -> list[NestedContract]:
    """
    Classify each contract in a chain independently.
    Each reads its own depositor — never inherits parent payer_type.
    """
    results = []
    for i, c in enumerate(contracts):
        classification = classify_address(
            c["depositor_address"],
            tx_history_count=c.get("tx_history_count", 0),
            avg_tx_interval_seconds=c.get("avg_tx_interval_seconds", 0),
        )
        results.append(NestedContract(
            contract_id=c["contract_id"],
            parent_contract_id=c.get("parent_contract_id"),
            depositor_address=c["depositor_address"],
            classification=classification,
            depth=i,
        ))
    return results


def demo_nested():
    print("\n=== Nested Contract Chain ===\n")
    chain = [
        {"contract_id": "outer-001", "parent_contract_id": None,
         "depositor_address": "HumanWallet9xyzABCDEF123456789",
         "tx_history_count": 47, "avg_tx_interval_seconds": 3600},
        {"contract_id": "inner-001", "parent_contract_id": "outer-001",
         "depositor_address": "SubAgentPDA11111111111111111111",
         "tx_history_count": 8000, "avg_tx_interval_seconds": 1.5},
        {"contract_id": "inner-002", "parent_contract_id": "outer-001",
         "depositor_address": "SubAgentPDA22222222222222222222",
         "tx_history_count": 3000, "avg_tx_interval_seconds": 3.0},
    ]
    results = classify_contract_chain(chain)
    for r in results:
        d = r.to_dict()
        parent = d["parent_contract_id"] or "ROOT"
        print(f"  [{d['depth']}] {d['contract_id']} (parent={parent})")
        print(f"      depositor: {d['address'][:20]}...")
        print(f"      type: {d['payer_type']} → timeout: {d['timeout_seconds']}s")
        print()
    print("  ⚠️  Each level re-derives. Inner A2A gets 5min, not parent's 24h.")
    print("  ⚠️  parent_contract_id = audit trail only. Never for classification.")


if __name__ == "__main__":
    demo()
    demo_nested()
