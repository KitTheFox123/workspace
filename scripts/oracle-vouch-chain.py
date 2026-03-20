#!/usr/bin/env python3
"""
oracle-vouch-chain.py — Genesis witness vouching for oracle independence.

Problem (santaclawd 2026-03-20): "who witnesses the witness?"
Self-attested independence declarations are only as honest as the declaring oracle.

Solution: Existing oracles with >90d history vouch for new oracle independence.
CT model: new log submits to root program, existing logs cross-sign.

References:
- Lamport (1982): BFT requires f < n/3
- CT root programs: Chrome, Apple, Mozilla maintain trusted log lists
- TOFU + vouching: SSH meets web of trust
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Oracle:
    """An oracle in the independence registry."""
    oracle_id: str
    model_family: str  # e.g., "gpt-4", "claude-opus", "llama-3"
    operator: str
    infrastructure: str  # e.g., "aws", "gcp", "self-hosted"
    registered_at: float
    vouched_by: list[str] = field(default_factory=list)
    age_days: float = 0.0

    @property
    def is_established(self) -> bool:
        return self.age_days >= 90

    @property
    def vouch_count(self) -> int:
        return len(self.vouched_by)


@dataclass 
class VouchRecord:
    """A vouching event: established oracle vouches for new oracle."""
    voucher_id: str
    vouchee_id: str
    dimensions_attested: list[str]  # which independence dimensions voucher attests
    timestamp: float
    voucher_age_days: float
    signature_hash: str = ""

    def __post_init__(self):
        if not self.signature_hash:
            canonical = json.dumps({
                "voucher": self.voucher_id,
                "vouchee": self.vouchee_id, 
                "dims": sorted(self.dimensions_attested),
                "ts": self.timestamp
            }, sort_keys=True)
            self.signature_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class VouchResult:
    """Result of vouch chain validation."""
    oracle_id: str
    status: str  # ESTABLISHED|VOUCHED|PROVISIONAL|UNVOUCHED
    vouch_count: int
    min_vouches_needed: int
    dimension_coverage: dict[str, int]  # dimension -> vouch count
    uncovered_dimensions: list[str]
    circular_vouches: list[str]  # detected circular vouching


INDEPENDENCE_DIMENSIONS = ["operator", "model", "infrastructure", "codebase", "data_source"]
MIN_VOUCHES = 2  # minimum vouches from established oracles
MIN_VOUCHER_AGE = 90  # days


class VouchRegistry:
    """Registry tracking oracle vouch chains."""
    
    def __init__(self):
        self.oracles: dict[str, Oracle] = {}
        self.vouches: list[VouchRecord] = []
    
    def register(self, oracle: Oracle):
        self.oracles[oracle.oracle_id] = oracle
    
    def vouch(self, voucher_id: str, vouchee_id: str, 
              dimensions: list[str]) -> tuple[bool, str]:
        """Established oracle vouches for new oracle's independence."""
        voucher = self.oracles.get(voucher_id)
        vouchee = self.oracles.get(vouchee_id)
        
        if not voucher:
            return False, f"UNKNOWN_VOUCHER: {voucher_id}"
        if not vouchee:
            return False, f"UNKNOWN_VOUCHEE: {vouchee_id}"
        if not voucher.is_established:
            return False, f"VOUCHER_TOO_YOUNG: {voucher_id} age={voucher.age_days:.0f}d < {MIN_VOUCHER_AGE}d"
        if voucher_id == vouchee_id:
            return False, "SELF_VOUCH: cannot vouch for self"
        
        # Check for circular vouching
        if vouchee_id in [v.voucher_id for v in self.vouches if v.vouchee_id == voucher_id]:
            return False, f"CIRCULAR_VOUCH: {vouchee_id} already vouched for {voucher_id}"
        
        # Check dimension overlap (voucher should be DIFFERENT on attested dimensions)
        for dim in dimensions:
            if dim == "operator" and voucher.operator == vouchee.operator:
                return False, f"SAME_OPERATOR: cannot vouch for operator independence when sharing operator"
            if dim == "model" and voucher.model_family == vouchee.model_family:
                return False, f"SAME_MODEL: cannot vouch for model independence when same family"
            if dim == "infrastructure" and voucher.infrastructure == vouchee.infrastructure:
                return False, f"SAME_INFRA: cannot vouch for infrastructure independence when same provider"
        
        record = VouchRecord(
            voucher_id=voucher_id,
            vouchee_id=vouchee_id,
            dimensions_attested=dimensions,
            timestamp=time.time(),
            voucher_age_days=voucher.age_days
        )
        self.vouches.append(record)
        vouchee.vouched_by.append(voucher_id)
        
        return True, f"VOUCHED: {voucher_id} → {vouchee_id} on {dimensions}"
    
    def validate(self, oracle_id: str) -> VouchResult:
        """Validate vouch chain for oracle."""
        oracle = self.oracles.get(oracle_id)
        if not oracle:
            return VouchResult(oracle_id, "UNKNOWN", 0, MIN_VOUCHES, {}, INDEPENDENCE_DIMENSIONS, [])
        
        if oracle.is_established:
            return VouchResult(oracle_id, "ESTABLISHED", oracle.vouch_count, 0, 
                             {d: 99 for d in INDEPENDENCE_DIMENSIONS}, [], [])
        
        # Count vouches per dimension
        dim_coverage = {d: 0 for d in INDEPENDENCE_DIMENSIONS}
        circular = []
        
        for v in self.vouches:
            if v.vouchee_id == oracle_id:
                for d in v.dimensions_attested:
                    if d in dim_coverage:
                        dim_coverage[d] += 1
                # Check circular
                reverse = [rv for rv in self.vouches 
                          if rv.voucher_id == oracle_id and rv.vouchee_id == v.voucher_id]
                if reverse:
                    circular.append(f"{v.voucher_id}↔{oracle_id}")
        
        uncovered = [d for d, c in dim_coverage.items() if c == 0]
        vouch_count = oracle.vouch_count
        
        if vouch_count >= MIN_VOUCHES and not uncovered:
            status = "VOUCHED"
        elif vouch_count > 0:
            status = "PROVISIONAL"
        else:
            status = "UNVOUCHED"
        
        return VouchResult(oracle_id, status, vouch_count, 
                          max(0, MIN_VOUCHES - vouch_count),
                          dim_coverage, uncovered, circular)


def demo():
    """Demo oracle vouch chain."""
    registry = VouchRegistry()
    
    # Established oracles (>90d)
    registry.register(Oracle("kit_fox", "claude-opus", "ilya", "hetzner", 0, age_days=120))
    registry.register(Oracle("bro_agent", "gpt-4", "paylock_team", "aws", 0, age_days=100))
    registry.register(Oracle("funwolf", "llama-3", "funwolf_op", "self-hosted", 0, age_days=95))
    
    # New oracle seeking vouches
    registry.register(Oracle("new_oracle", "claude-sonnet", "new_op", "gcp", 0, age_days=5))
    
    # Sybil attempt — same operator as kit_fox
    registry.register(Oracle("sybil_kit", "claude-haiku", "ilya", "hetzner", 0, age_days=2))
    
    print("=" * 65)
    print("ORACLE VOUCH CHAIN VALIDATION")
    print("=" * 65)
    
    # Vouch for new_oracle
    vouches = [
        ("kit_fox", "new_oracle", ["operator", "infrastructure"]),
        ("bro_agent", "new_oracle", ["operator", "model", "infrastructure"]),
        ("funwolf", "new_oracle", ["operator", "model", "infrastructure", "codebase", "data_source"]),
    ]
    
    print("\n--- Vouching for new_oracle ---")
    for voucher, vouchee, dims in vouches:
        ok, msg = registry.vouch(voucher, vouchee, dims)
        print(f"  {'✅' if ok else '❌'} {msg}")
    
    # Try sybil vouching
    print("\n--- Sybil vouching attempts ---")
    ok, msg = registry.vouch("kit_fox", "sybil_kit", ["operator", "infrastructure"])
    print(f"  {'✅' if ok else '❌'} {msg}")
    
    ok, msg = registry.vouch("bro_agent", "sybil_kit", ["operator", "model", "infrastructure"])
    print(f"  {'✅' if ok else '❌'} {msg}")
    
    # Self-vouch attempt
    ok, msg = registry.vouch("new_oracle", "new_oracle", ["operator"])
    print(f"  {'✅' if ok else '❌'} {msg}")
    
    # Validate all
    print("\n--- Validation Results ---")
    print(f"{'Oracle':<15} {'Status':<12} {'Vouches':>7} {'Needed':>7} {'Uncovered'}")
    print("-" * 65)
    
    for oid in ["kit_fox", "bro_agent", "funwolf", "new_oracle", "sybil_kit"]:
        result = registry.validate(oid)
        uncovered = ", ".join(result.uncovered_dimensions) if result.uncovered_dimensions else "none"
        print(f"{oid:<15} {result.status:<12} {result.vouch_count:>7} {result.min_vouches_needed:>7} {uncovered}")
    
    print()
    print("KEY: Established oracles (>90d) vouch for new ones.")
    print("     Same operator/model/infra = cannot vouch that dimension.")
    print("     Circular vouching detected and rejected.")
    print("     CT model: append-only log + cross-signing.")


if __name__ == "__main__":
    demo()
