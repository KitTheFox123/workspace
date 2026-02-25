#!/usr/bin/env python3
"""
contract-schema-linter.py — Catch creation-time bugs in agent contracts.

Based on santaclawd's thread: the top bugs in agent contracts are all
detectable at CREATION time, not runtime. This linter checks for:

Bug #1: Schema ambiguity — fields that can be interpreted multiple ways
Bug #2: Identity mismatch — signer != deliverer 
Bug #3: Temporal assumption mismatch — no clock source binding
Bug #4: Reputation as fact — opaque scores instead of verifiable logs

Usage:
    python3 contract-schema-linter.py check CONTRACT.json
    python3 contract-schema-linter.py demo
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LintWarning:
    severity: str  # "error" | "warning" | "info"
    bug_class: str  # "schema_ambiguity" | "identity_mismatch" | "temporal" | "opacity"
    field: str
    message: str


@dataclass
class LintResult:
    valid: bool
    warnings: list[LintWarning] = field(default_factory=list)
    score: float = 1.0  # 0.0 = reject, 1.0 = clean

    def add(self, w: LintWarning):
        self.warnings.append(w)
        if w.severity == "error":
            self.valid = False
            self.score -= 0.3
        elif w.severity == "warning":
            self.score -= 0.1
        self.score = max(0.0, self.score)


# Required fields for a well-formed agent contract
REQUIRED_FIELDS = ["parties", "deliverable", "settlement", "timeline"]

# Fields that indicate verifiable vs narrative claims
VERIFIABLE_INDICATORS = ["tx_hash", "attestation_chain", "hash", "digest", "signature", "proof"]
NARRATIVE_INDICATORS = ["reputation_score", "trust_level", "quality_rating", "rank"]

# Temporal fields that need clock source
TEMPORAL_FIELDS = ["deadline", "timeout", "window", "duration", "expires", "effective_at"]
VALID_CLOCK_SOURCES = ["utc", "block_height", "unix_timestamp", "slot"]


def lint_contract(contract: dict) -> LintResult:
    result = LintResult(valid=True)

    # Check required fields
    for f in REQUIRED_FIELDS:
        if f not in contract:
            result.add(LintWarning(
                "error", "schema_ambiguity", f,
                f"Missing required field '{f}'"
            ))

    # Bug #1: Schema ambiguity
    _check_schema_ambiguity(contract, result)

    # Bug #2: Identity mismatch
    _check_identity_mismatch(contract, result)

    # Bug #3: Temporal assumptions
    _check_temporal(contract, result)

    # Bug #4: Opacity (narrative vs verifiable)
    _check_opacity(contract, result)

    return result


def _check_schema_ambiguity(contract: dict, result: LintResult):
    """Check for fields that can be interpreted multiple ways."""
    deliverable = contract.get("deliverable", {})

    # Ambiguous success criteria
    if isinstance(deliverable, dict):
        if "description" in deliverable and "acceptance_criteria" not in deliverable:
            result.add(LintWarning(
                "warning", "schema_ambiguity", "deliverable",
                "Deliverable has description but no acceptance_criteria. "
                "Subjective judgment becomes implicit."
            ))

        # Amount without denomination
        if "amount" in deliverable and "denomination" not in deliverable:
            result.add(LintWarning(
                "warning", "schema_ambiguity", "deliverable.amount",
                "Amount specified without denomination (USDC? SOL? units?)"
            ))

    # Settlement ambiguity
    settlement = contract.get("settlement", {})
    if isinstance(settlement, dict):
        if "method" not in settlement:
            result.add(LintWarning(
                "error", "schema_ambiguity", "settlement",
                "No settlement method specified (escrow? direct? auto-release?)"
            ))


def _check_identity_mismatch(contract: dict, result: LintResult):
    """Check that signer, deliverer, and payment recipient are bound."""
    parties = contract.get("parties", {})

    if isinstance(parties, dict):
        provider = parties.get("provider", {})
        if isinstance(provider, dict):
            signer = provider.get("signing_key")
            delivery_address = provider.get("delivery_address")

            if signer and delivery_address:
                # Can't verify binding without crypto, but flag if different identifiers
                if not provider.get("identity_binding"):
                    result.add(LintWarning(
                        "warning", "identity_mismatch", "parties.provider",
                        "Provider has signing_key and delivery_address but no identity_binding. "
                        "Agent A could sign, Agent B could deliver."
                    ))

        # Check buyer
        buyer = parties.get("buyer", {})
        if isinstance(buyer, dict):
            if not buyer.get("signing_key") and not buyer.get("did"):
                result.add(LintWarning(
                    "warning", "identity_mismatch", "parties.buyer",
                    "Buyer has no signing_key or DID. Identity unverifiable."
                ))


def _check_temporal(contract: dict, result: LintResult):
    """Check all temporal fields have clock source bindings."""
    timeline = contract.get("timeline", {})

    if isinstance(timeline, dict):
        has_clock_source = "clock_source" in timeline

        for key in timeline:
            if any(t in key.lower() for t in TEMPORAL_FIELDS):
                if not has_clock_source:
                    result.add(LintWarning(
                        "error", "temporal", f"timeline.{key}",
                        f"Temporal field '{key}' has no clock_source binding. "
                        f"Valid sources: {VALID_CLOCK_SOURCES}"
                    ))
                    break  # One error is enough

        if has_clock_source:
            src = timeline["clock_source"].lower()
            if src not in VALID_CLOCK_SOURCES:
                result.add(LintWarning(
                    "warning", "temporal", "timeline.clock_source",
                    f"Unknown clock source '{src}'. Valid: {VALID_CLOCK_SOURCES}"
                ))
    elif "timeline" not in contract:
        pass  # Already caught by required fields check


def _check_opacity(contract: dict, result: LintResult):
    """Check for narrative claims vs verifiable artifacts."""
    contract_str = json.dumps(contract).lower()

    # Flag narrative indicators
    for indicator in NARRATIVE_INDICATORS:
        if indicator in contract_str:
            result.add(LintWarning(
                "warning", "opacity", indicator,
                f"'{indicator}' is a narrative claim, not a checkable artifact. "
                f"Expose the raw data and let consumers compute their own score."
            ))

    # Check if any verifiable indicators present
    has_verifiable = any(v in contract_str for v in VERIFIABLE_INDICATORS)
    if not has_verifiable:
        result.add(LintWarning(
            "info", "opacity", "contract",
            "No verifiable artifacts found (tx_hash, attestation_chain, signature, proof). "
            "Consider adding checkable evidence."
        ))


def demo():
    """Run demo with sample contracts."""
    print("=" * 60)
    print("Agent Contract Schema Linter")
    print("=" * 60)

    # Contract 1: tc3-style (mostly good)
    tc3 = {
        "parties": {
            "provider": {
                "agent_id": "kit_fox",
                "signing_key": "ed25519:abc123",
                "delivery_address": "kit_fox@agentmail.to",
                "identity_binding": "isnad:agent:ed8f9aafc2964d05"
            },
            "buyer": {
                "agent_id": "gendolf",
                "signing_key": "ed25519:def456",
                "did": "agent:7fed2c1d6c682cf5"
            },
            "judge": {
                "agent_id": "bro_agent"
            }
        },
        "deliverable": {
            "description": "Research: What does the agent economy need at scale?",
            "acceptance_criteria": "Score >= 0.7 from judge",
            "format": "markdown via agentmail"
        },
        "settlement": {
            "method": "escrow",
            "platform": "PayLock",
            "amount": 0.01,
            "denomination": "SOL",
            "tx_hash": "pending"
        },
        "timeline": {
            "deadline": "48h",
            "clock_source": "utc",
            "dispute_window": "48h"
        },
        "attestation_chain": ["braindiff", "momo"]
    }

    print("\n--- Contract 1: tc3-style (well-formed) ---")
    r1 = lint_contract(tc3)
    _print_result(r1)

    # Contract 2: buggy contract (all 4 bugs)
    buggy = {
        "parties": {
            "provider": {
                "signing_key": "ed25519:xxx",
                "delivery_address": "someone@agentmail.to"
                # No identity_binding!
            },
            "buyer": {
                "name": "anonymous"
                # No signing_key or DID!
            }
        },
        "deliverable": {
            "description": "Do some research",
            "amount": 50
            # No acceptance_criteria, no denomination!
        },
        "settlement": {
            "reputation_score": 0.8
            # No method!
        },
        "timeline": {
            "deadline": "2 days"
            # No clock_source!
        }
    }

    print("\n--- Contract 2: buggy (all 4 creation-time bugs) ---")
    r2 = lint_contract(buggy)
    _print_result(r2)


def _print_result(result: LintResult):
    status = "✅ PASS" if result.valid else "❌ FAIL"
    print(f"  {status} (score: {result.score:.2f})")
    for w in result.warnings:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}[w.severity]
        print(f"  {icon} [{w.bug_class}] {w.field}: {w.message}")


def check_file(filepath: str):
    with open(filepath) as f:
        contract = json.load(f)
    result = lint_contract(contract)
    _print_result(result)
    return result.valid


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "check" and len(sys.argv) > 2:
        check_file(sys.argv[2])
    else:
        print(__doc__)
