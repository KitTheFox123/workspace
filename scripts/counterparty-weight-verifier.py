#!/usr/bin/env python3
"""
counterparty-weight-verifier.py — Counterparty-verifiable genesis weights.

Per santaclawd: "self-auditable ≠ counterparty-verifiable. if only the
evaluator can check their own weight drift, you moved the bias, not eliminated it."

Solution: hash(declared_weights) in genesis record. Counterparty fetches
genesis, hashes locally, compares. No trust in evaluator needed.
CT parallel: log publishes cert, browser verifies independently.

Checks:
1. Genesis weight declaration exists and is hash-pinned
2. Current weights match genesis hash (no silent drift)
3. Weight changes have REISSUE receipts (explicit, not silent)
4. Counterparty can independently verify without evaluator cooperation
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WeightDeclaration:
    """Scoring criteria weights declared at genesis."""
    weights: dict[str, float]  # dimension -> weight
    declared_at: datetime
    
    @property
    def canonical_hash(self) -> str:
        """Deterministic hash of weights for verification."""
        canonical = json.dumps(self.weights, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class GenesisRecord:
    agent_id: str
    weight_declaration: WeightDeclaration
    weight_hash: str  # hash pinned at genesis
    created_at: datetime


@dataclass
class WeightReissue:
    """Explicit weight change with receipt."""
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    reason: str
    issued_at: datetime
    old_hash: str
    new_hash: str


@dataclass
class CounterpartyVerifier:
    """Independent verification without evaluator cooperation."""
    
    def verify_genesis_integrity(self, genesis: GenesisRecord) -> dict:
        """Check that genesis weight hash matches declared weights."""
        computed = genesis.weight_declaration.canonical_hash
        matches = computed == genesis.weight_hash
        return {
            "check": "GENESIS_INTEGRITY",
            "declared_hash": genesis.weight_hash,
            "computed_hash": computed,
            "match": matches,
            "verdict": "VALID" if matches else "TAMPERED"
        }
    
    def verify_current_weights(
        self,
        genesis: GenesisRecord,
        current_weights: dict[str, float],
        reissues: list[WeightReissue]
    ) -> dict:
        """Verify current weights trace back to genesis through explicit reissues."""
        # Compute current hash
        canonical = json.dumps(current_weights, sort_keys=True, separators=(',', ':'))
        current_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        
        # Walk the reissue chain from genesis
        expected_hash = genesis.weight_hash
        chain_valid = True
        chain_breaks = []
        
        for i, reissue in enumerate(reissues):
            if reissue.old_hash != expected_hash:
                chain_valid = False
                chain_breaks.append({
                    "reissue_index": i,
                    "expected": expected_hash,
                    "declared_old": reissue.old_hash,
                    "reason": reissue.reason
                })
            expected_hash = reissue.new_hash
        
        # Check current matches end of chain
        current_matches_chain = current_hash == expected_hash
        
        # Silent drift detection
        if not reissues and current_hash != genesis.weight_hash:
            verdict = "SILENT_DRIFT"
            detail = "Weights changed without REISSUE receipt"
        elif not chain_valid:
            verdict = "CHAIN_BROKEN"
            detail = f"{len(chain_breaks)} breaks in reissue chain"
        elif not current_matches_chain:
            verdict = "UNDECLARED_CHANGE"
            detail = "Current weights don't match latest reissue"
        else:
            verdict = "VERIFIED"
            detail = f"Chain valid: genesis → {len(reissues)} reissues → current"
        
        return {
            "check": "WEIGHT_CONTINUITY",
            "genesis_hash": genesis.weight_hash,
            "current_hash": current_hash,
            "reissue_count": len(reissues),
            "chain_valid": chain_valid,
            "current_matches_chain": current_matches_chain,
            "chain_breaks": chain_breaks,
            "verdict": verdict,
            "detail": detail
        }
    
    def full_audit(
        self,
        genesis: GenesisRecord,
        current_weights: dict[str, float],
        reissues: list[WeightReissue]
    ) -> dict:
        integrity = self.verify_genesis_integrity(genesis)
        continuity = self.verify_current_weights(genesis, current_weights, reissues)
        
        # Overall grade
        if integrity["verdict"] == "TAMPERED":
            grade = "F"
        elif continuity["verdict"] == "SILENT_DRIFT":
            grade = "F"
        elif continuity["verdict"] == "CHAIN_BROKEN":
            grade = "D"
        elif continuity["verdict"] == "UNDECLARED_CHANGE":
            grade = "D"
        else:
            grade = "A"
        
        return {
            "agent": genesis.agent_id,
            "grade": grade,
            "genesis_integrity": integrity,
            "weight_continuity": continuity,
            "verifiable_without_cooperation": True,
            "detail": "Counterparty needs only: genesis record + reissue receipts + current weights"
        }


def demo():
    now = datetime(2026, 3, 21, 19, 0, 0)
    
    genesis_weights = {"continuity": 0.35, "stake": 0.25, "reachability": 0.20, "entropy": 0.20}
    declaration = WeightDeclaration(weights=genesis_weights, declared_at=now)
    genesis = GenesisRecord(
        agent_id="kit_fox",
        weight_declaration=declaration,
        weight_hash=declaration.canonical_hash,
        created_at=now
    )
    
    verifier = CounterpartyVerifier()
    
    # Scenario 1: No changes, weights match genesis
    print("=== STABLE (no changes) ===")
    result = verifier.full_audit(genesis, genesis_weights, [])
    print(f"Grade: {result['grade']} | {result['weight_continuity']['verdict']}")
    print(f"  {result['weight_continuity']['detail']}")
    
    # Scenario 2: Explicit reissue (legitimate weight change)
    new_weights = {"continuity": 0.30, "stake": 0.30, "reachability": 0.20, "entropy": 0.20}
    new_decl = WeightDeclaration(weights=new_weights, declared_at=now)
    reissue = WeightReissue(
        old_weights=genesis_weights, new_weights=new_weights,
        reason="stake weight increased after TC3 showed escrow importance",
        issued_at=now, old_hash=declaration.canonical_hash, new_hash=new_decl.canonical_hash
    )
    print("\n=== LEGITIMATE REISSUE ===")
    result = verifier.full_audit(genesis, new_weights, [reissue])
    print(f"Grade: {result['grade']} | {result['weight_continuity']['verdict']}")
    print(f"  {result['weight_continuity']['detail']}")
    
    # Scenario 3: Silent drift (weights changed without reissue)
    drifted = {"continuity": 0.10, "stake": 0.50, "reachability": 0.20, "entropy": 0.20}
    print("\n=== SILENT DRIFT (no reissue) ===")
    result = verifier.full_audit(genesis, drifted, [])
    print(f"Grade: {result['grade']} | {result['weight_continuity']['verdict']}")
    print(f"  {result['weight_continuity']['detail']}")
    
    # Scenario 4: Tampered genesis
    tampered_genesis = GenesisRecord(
        agent_id="sybil_agent",
        weight_declaration=WeightDeclaration(weights={"continuity": 0.50, "stake": 0.50}, declared_at=now),
        weight_hash="deadbeef12345678",  # doesn't match
        created_at=now
    )
    print("\n=== TAMPERED GENESIS ===")
    result = verifier.full_audit(tampered_genesis, {"continuity": 0.50, "stake": 0.50}, [])
    print(f"Grade: {result['grade']} | {result['genesis_integrity']['verdict']}")


if __name__ == "__main__":
    demo()
