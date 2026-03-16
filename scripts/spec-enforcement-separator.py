#!/usr/bin/env python3
"""
spec-enforcement-separator.py — Formal separation of spec and enforcement layers.

Per santaclawd: "Make the SPEC product-neutral so enforcement can move between runtimes."
Chrome CT model: IETF owns RFC 6962 (spec), Chrome enforces (policy), any browser can enforce independently.

Key principle: spec defines WIRE FORMAT, enforcement defines POLICY.
- Spec: what a valid receipt looks like (schema, fields, proof structure)
- Enforcement: what to DO with invalid receipts (reject, warn, log, ignore)

This is the IETF/browser split applied to agent trust:
- L3.5 wire format = RFC (open, product-neutral, versioned)
- Runtime enforcement = Chrome CT policy (per-product, graduated, rollback-capable)

Anti-patterns:
1. Spec includes scoring algorithm → every impl disagrees on weights → forks
2. Spec is too loose → "be liberal in acceptance" → ossification (RFC 9413)
3. Enforcement is spec-coupled → can't change policy without spec revision
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


# ============================================================
# SPEC LAYER: Wire format only. No policy. No scoring.
# ============================================================

class ReceiptVersion(Enum):
    V1 = "1.0"
    V1_1 = "1.1"


@dataclass
class WireReceipt:
    """L3.5 wire format. Spec-defined. Product-neutral."""
    version: ReceiptVersion
    receipt_id: str
    agent_id: str
    action_type: str
    timestamp: float
    
    # Merkle proof (spec-mandated structure)
    leaf_hash: str
    inclusion_proof: list[str]
    merkle_root: str
    
    # Witness signatures (spec-mandated: ≥1, enforcement decides minimum)
    witnesses: list[dict]  # [{operator_id, org, sig, timestamp}]
    
    # Diversity hash (spec-mandated field, enforcement decides threshold)
    diversity_hash: Optional[str] = None
    
    # Extension fields (spec allows, enforcement interprets)
    extensions: dict[str, Any] = field(default_factory=dict)
    
    def to_wire(self) -> bytes:
        """Serialize to canonical wire format."""
        canonical = {
            "version": self.version.value,
            "receipt_id": self.receipt_id,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "timestamp": self.timestamp,
            "leaf_hash": self.leaf_hash,
            "inclusion_proof": self.inclusion_proof,
            "merkle_root": self.merkle_root,
            "witnesses": sorted(self.witnesses, key=lambda w: w.get("operator_id", "")),
            "diversity_hash": self.diversity_hash,
        }
        return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    
    def content_hash(self) -> str:
        """Content-addressable hash of wire format."""
        return hashlib.sha256(self.to_wire()).hexdigest()


class SpecValidator:
    """
    Validates wire format compliance. Spec-only, no policy.
    
    Returns: which spec requirements are met/violated.
    Does NOT decide what to do about violations — that's enforcement.
    """
    
    REQUIRED_FIELDS = ["version", "receipt_id", "agent_id", "action_type",
                       "timestamp", "leaf_hash", "merkle_root"]
    
    @staticmethod
    def validate(receipt: WireReceipt) -> dict:
        """Check spec compliance. Returns findings, not decisions."""
        findings = {
            "spec_version": receipt.version.value,
            "has_required_fields": True,
            "has_merkle_proof": len(receipt.inclusion_proof) > 0,
            "has_witnesses": len(receipt.witnesses) > 0,
            "witness_count": len(receipt.witnesses),
            "has_diversity_hash": receipt.diversity_hash is not None,
            "merkle_proof_valid": False,
            "unique_witness_orgs": 0,
            "violations": [],
        }
        
        # Check required fields
        for f in SpecValidator.REQUIRED_FIELDS:
            if not getattr(receipt, f, None):
                findings["has_required_fields"] = False
                findings["violations"].append(f"missing_field:{f}")
        
        # Verify Merkle proof
        if findings["has_merkle_proof"]:
            findings["merkle_proof_valid"] = SpecValidator._verify_merkle(receipt)
            if not findings["merkle_proof_valid"]:
                findings["violations"].append("invalid_merkle_proof")
        else:
            findings["violations"].append("no_merkle_proof")
        
        # Count unique witness orgs (fact, not policy)
        orgs = set()
        for w in receipt.witnesses:
            org = w.get("org", "unknown")
            orgs.add(org)
        findings["unique_witness_orgs"] = len(orgs)
        
        # Timestamp sanity (spec: must be positive, not in future)
        if receipt.timestamp <= 0:
            findings["violations"].append("invalid_timestamp")
        elif receipt.timestamp > time.time() + 300:  # 5min clock skew tolerance
            findings["violations"].append("future_timestamp")
        
        return findings
    
    @staticmethod
    def _verify_merkle(receipt: WireReceipt) -> bool:
        """Verify Merkle inclusion proof."""
        current = receipt.leaf_hash
        for sibling in receipt.inclusion_proof:
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == receipt.merkle_root


# ============================================================
# ENFORCEMENT LAYER: Policy decisions. Product-specific.
# ============================================================

class EnforcementAction(Enum):
    ACCEPT = "accept"
    WARN = "warn"
    REJECT = "reject"
    QUARANTINE = "quarantine"


@dataclass
class EnforcementPolicy:
    """
    Runtime-specific enforcement policy. NOT part of the spec.
    
    Different runtimes can have different policies:
    - OpenClaw: STRICT (reject without 2+ witnesses)
    - LangChain: PERMISSIVE (accept all, log violations)
    - Custom: WARN (accept but surface to user)
    """
    name: str
    min_witnesses: int = 2
    require_diversity_hash: bool = True
    max_receipt_age_s: float = 86400  # 24h
    require_merkle_proof: bool = True
    min_unique_orgs: int = 2
    
    # Graduation state
    phase: str = "report"  # permissive, report, warn, strict
    
    def decide(self, findings: dict) -> tuple[EnforcementAction, list[str]]:
        """Apply policy to spec findings. Returns action + reasons."""
        reasons = []
        
        if not findings["has_required_fields"]:
            reasons.append("missing_required_fields")
        
        if self.require_merkle_proof and not findings["merkle_proof_valid"]:
            reasons.append("invalid_merkle_proof")
        
        if findings["witness_count"] < self.min_witnesses:
            reasons.append(f"insufficient_witnesses:{findings['witness_count']}/{self.min_witnesses}")
        
        if self.require_diversity_hash and not findings["has_diversity_hash"]:
            reasons.append("missing_diversity_hash")
        
        if findings["unique_witness_orgs"] < self.min_unique_orgs:
            reasons.append(f"insufficient_org_diversity:{findings['unique_witness_orgs']}/{self.min_unique_orgs}")
        
        # Determine action based on phase
        if not reasons:
            return EnforcementAction.ACCEPT, []
        
        if self.phase == "strict":
            return EnforcementAction.REJECT, reasons
        elif self.phase == "warn":
            return EnforcementAction.WARN, reasons
        elif self.phase == "report":
            return EnforcementAction.ACCEPT, reasons  # Accept but log
        else:  # permissive
            return EnforcementAction.ACCEPT, []


# ============================================================
# RUNTIME: Combines spec validation + policy enforcement
# ============================================================

class AgentRuntime:
    """
    An agent runtime that enforces receipts.
    Spec validation is shared. Enforcement policy is runtime-specific.
    """
    
    def __init__(self, name: str, policy: EnforcementPolicy):
        self.name = name
        self.policy = policy
        self.spec_validator = SpecValidator()
        self.log: list[dict] = []
    
    def process_receipt(self, receipt: WireReceipt) -> dict:
        """Validate spec compliance, then apply enforcement policy."""
        # Step 1: Spec validation (same for all runtimes)
        findings = self.spec_validator.validate(receipt)
        
        # Step 2: Enforcement policy (runtime-specific)
        action, reasons = self.policy.decide(findings)
        
        result = {
            "runtime": self.name,
            "receipt_id": receipt.receipt_id,
            "spec_violations": findings["violations"],
            "policy_phase": self.policy.phase,
            "action": action.value,
            "reasons": reasons,
        }
        
        self.log.append(result)
        return result


def _make_receipt(valid=True, witnesses=2, diversity=True) -> WireReceipt:
    """Helper to create test receipts."""
    now = time.time()
    leaf = hashlib.sha256(b"test_action").hexdigest()
    sibling = hashlib.sha256(b"sibling").hexdigest()
    if leaf < sibling:
        root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
    
    witness_list = []
    for i in range(witnesses):
        witness_list.append({
            "operator_id": f"op_{i}",
            "org": f"Org{'ABCDE'[i]}" if valid else "SameOrg",
            "sig": f"sig_{i}",
            "timestamp": now,
        })
    
    return WireReceipt(
        version=ReceiptVersion.V1,
        receipt_id=f"r_{int(now)}",
        agent_id="agent:test",
        action_type="delivery",
        timestamp=now,
        leaf_hash=leaf,
        inclusion_proof=[sibling] if valid else [],
        merkle_root=root if valid else "bad_root",
        witnesses=witness_list,
        diversity_hash="div_hash" if diversity else None,
    )


def demo():
    """Show spec/enforcement separation across multiple runtimes."""
    print("=" * 70)
    print("SPEC/ENFORCEMENT SEPARATION")
    print("Same receipt, same spec validation, different runtime policies")
    print("=" * 70)
    
    # Define runtime policies (like Chrome, Firefox, Safari each enforcing CT differently)
    runtimes = [
        AgentRuntime("OpenClaw-Strict", EnforcementPolicy(
            name="strict", min_witnesses=2, require_diversity_hash=True,
            min_unique_orgs=2, phase="strict"
        )),
        AgentRuntime("LangChain-Report", EnforcementPolicy(
            name="report", min_witnesses=2, require_diversity_hash=True,
            min_unique_orgs=2, phase="report"
        )),
        AgentRuntime("Custom-Permissive", EnforcementPolicy(
            name="permissive", min_witnesses=1, require_diversity_hash=False,
            min_unique_orgs=1, phase="permissive"
        )),
    ]
    
    receipts = [
        ("Valid receipt (2 orgs, Merkle, diversity)", _make_receipt(True, 2, True)),
        ("Single witness, no diversity hash", _make_receipt(True, 1, False)),
        ("Same org witnesses, bad Merkle proof", _make_receipt(False, 2, True)),
    ]
    
    for receipt_name, receipt in receipts:
        print(f"\n📄 {receipt_name}")
        print("-" * 50)
        
        # Spec validation (same for all)
        findings = SpecValidator.validate(receipt)
        print(f"  Spec violations: {findings['violations'] or 'none'}")
        
        # Each runtime decides independently
        for runtime in runtimes:
            result = runtime.process_receipt(receipt)
            icon = {"accept": "✅", "warn": "⚠️", "reject": "❌", "quarantine": "🔒"}
            print(f"  {icon.get(result['action'], '?')} {runtime.name}: "
                  f"{result['action'].upper()}"
                  f"{' — ' + ', '.join(result['reasons']) if result['reasons'] else ''}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: Same wire format, same spec validation,")
    print("different enforcement decisions. The spec outlives any single enforcer.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
