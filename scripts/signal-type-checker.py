#!/usr/bin/env python3
"""
signal-type-checker.py — Prevent cross-domain signal comparison (Goodhart's Law for trust).

Problem: comparing signals across mismatched domains produces silent false positives.
- Whisper avg_logprob: transcription quality ≠ accent nativeness (rachel-caretta 2026-03-20)
- soul_hash vs manifest_hash: identity ≠ structure (axiomeye typed hash work)
- Wilson CI: trust score ≠ recommendation (cold-start-trust.py)

Solution: Typed signals with domain annotations. Cross-domain comparison = TypeError.
Same pattern as typed-hash-registry.py but generalized to any signal.

References:
- Goodhart (1975): "When a measure becomes a target, it ceases to be a good measure"
- Campbell (1979): "The more any quantitative social indicator is used for social decision-making,
  the more subject it will be to corruption pressures"
- rachel-caretta: avg_logprob confidence ≠ nativeness signal
- axiomeye: typed hashes prevent silent cross-type comparison
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SignalDomain(Enum):
    """Signal domain — what the signal actually measures."""
    IDENTITY = "identity"          # who the agent IS (soul_hash, agent_id)
    STRUCTURE = "structure"        # how the agent is BUILT (manifest, model_hash)
    BEHAVIOR = "behavior"          # what the agent DOES (receipt history, actions)
    CONFIDENCE = "confidence"      # model self-assessment (logprob, perplexity)
    TRUST = "trust"                # external assessment (Wilson CI, attestation)
    POLICY = "policy"              # rules and constraints (retention tier, scope)
    PERFORMANCE = "performance"    # task quality (accuracy, latency)


@dataclass(frozen=True)
class TypedSignal:
    """A signal with explicit domain annotation."""
    name: str
    value: float
    domain: SignalDomain
    source: str  # who produced this signal
    description: str = ""

    def __eq__(self, other):
        if not isinstance(other, TypedSignal):
            return NotImplemented
        if self.domain != other.domain:
            raise TypeError(
                f"Cannot compare {self.domain.value}:{self.name} with "
                f"{other.domain.value}:{other.name}. "
                f"Cross-domain comparison is undefined."
            )
        return self.value == other.value

    def __lt__(self, other):
        if not isinstance(other, TypedSignal):
            return NotImplemented
        if self.domain != other.domain:
            raise TypeError(
                f"Cannot compare {self.domain.value}:{self.name} with "
                f"{other.domain.value}:{other.name}. "
                f"Signal domains must match."
            )
        return self.value < other.value

    def __repr__(self):
        return f"{self.domain.value}:{self.name}={self.value:.3f}"


def check_routing_decision(signal: TypedSignal, required_domain: SignalDomain) -> dict:
    """Check if a signal is being used for its intended domain."""
    if signal.domain == required_domain:
        return {
            "valid": True,
            "signal": repr(signal),
            "required": required_domain.value,
            "warning": None
        }
    else:
        return {
            "valid": False,
            "signal": repr(signal),
            "required": required_domain.value,
            "warning": (
                f"GOODHART VIOLATION: {signal.domain.value}:{signal.name} "
                f"used as {required_domain.value} signal. "
                f"'{signal.name}' measures {signal.domain.value}, "
                f"not {required_domain.value}."
            )
        }


def demo():
    """Demo: prevent rachel-caretta's Whisper signal confusion."""
    print("=" * 65)
    print("SIGNAL TYPE CHECKER — Goodhart's Law Prevention")
    print("=" * 65)

    # rachel-caretta's Whisper example
    whisper_conf = TypedSignal(
        name="avg_logprob", value=0.882,
        domain=SignalDomain.CONFIDENCE,
        source="whisper-large-v3",
        description="Transcription confidence"
    )

    locale_flag = TypedSignal(
        name="customer_locale", value=0.95,
        domain=SignalDomain.IDENTITY,
        source="customer_profile",
        description="Self-reported locale precision"
    )

    # Check: using confidence signal for identity routing
    print("\n--- rachel-caretta's Whisper Signal ---")
    result = check_routing_decision(whisper_conf, SignalDomain.IDENTITY)
    print(f"  Signal: {result['signal']}")
    print(f"  Required: {result['required']}")
    print(f"  Valid: {'✅' if result['valid'] else '❌'}")
    if result['warning']:
        print(f"  ⚠️  {result['warning']}")

    result2 = check_routing_decision(locale_flag, SignalDomain.IDENTITY)
    print(f"\n  Fix: {result2['signal']}")
    print(f"  Valid: {'✅' if result2['valid'] else '❌'}")

    # Trust scoring examples
    print("\n--- Trust Signal Type Safety ---")
    
    wilson_ci = TypedSignal(
        name="wilson_lower", value=0.78,
        domain=SignalDomain.TRUST,
        source="cold-start-trust.py"
    )
    
    soul_hash_match = TypedSignal(
        name="soul_hash_stable", value=1.0,
        domain=SignalDomain.IDENTITY,
        source="soul-hash-drift.py"
    )
    
    receipt_density = TypedSignal(
        name="receipts_per_day", value=4.2,
        domain=SignalDomain.BEHAVIOR,
        source="attestation-density-scorer.py"
    )

    # Valid: trust signal for trust decision
    r = check_routing_decision(wilson_ci, SignalDomain.TRUST)
    print(f"  {r['signal']} for trust: {'✅' if r['valid'] else '❌'}")

    # Invalid: identity signal for trust decision
    r = check_routing_decision(soul_hash_match, SignalDomain.TRUST)
    print(f"  {r['signal']} for trust: {'❌'}")
    print(f"    ⚠️  {r['warning']}")

    # Cross-domain comparison raises TypeError
    print("\n--- Cross-Domain Comparison ---")
    try:
        _ = wilson_ci > soul_hash_match
    except TypeError as e:
        print(f"  wilson_ci > soul_hash_match → TypeError: {e}")

    # Same-domain comparison works
    wilson_ci2 = TypedSignal(
        name="wilson_lower", value=0.92,
        domain=SignalDomain.TRUST,
        source="cold-start-trust.py"
    )
    print(f"  wilson_ci(0.78) < wilson_ci2(0.92) → {wilson_ci < wilson_ci2}")

    print("\n" + "=" * 65)
    print("PRINCIPLE: Goodhart's Law is a type error.")
    print("When you route on a signal outside its domain,")
    print("you're comparing soul_hash to manifest_hash.")
    print("The type system prevents it. Boring and correct.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
