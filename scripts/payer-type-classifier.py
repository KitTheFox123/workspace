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
    
    # Key insight
    print("--- Design Principle ---")
    print("Address IS identity. No self-reported payer_type field.")
    print("PDA = A2A = 5min timeout (programmatic, no excuse).")
    print("EOA = human = 24h timeout (attention budget).")
    print("Ambiguous = human timeout (safer default).")
    print("Zahavi handicap: the signal is credible BECAUSE it is expensive.")


if __name__ == "__main__":
    demo()
