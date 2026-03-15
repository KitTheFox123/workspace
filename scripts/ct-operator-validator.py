#!/usr/bin/env python3
"""
ct-operator-validator.py — Validate operator independence for agent CT receipts.

Per santaclawd (2026-03-15): "Chrome CT = the lived reference. 1 SCT from Google
+ 1 non-Google means even if one log corrupts, the other catches it."

Protocol requirement, not governance: reject receipts where witnesses share
hosting, key infrastructure, or operator identity.
"""

from dataclasses import dataclass, field
from enum import Enum


class IndependenceLevel(Enum):
    INDEPENDENT = "independent"      # Distinct hosting + key material + operator
    WEAK = "weak"                    # Same hosting OR same key infra
    CORRELATED = "correlated"        # Same operator, different names
    SINGLE_POINT = "single_point"    # Same everything


@dataclass
class Operator:
    operator_id: str
    hosting_provider: str
    key_infrastructure: str  # HSM vendor, key management service
    jurisdiction: str
    
    def overlap_with(self, other: 'Operator') -> list[str]:
        overlaps = []
        if self.operator_id == other.operator_id:
            overlaps.append("same_operator")
        if self.hosting_provider == other.hosting_provider:
            overlaps.append("same_hosting")
        if self.key_infrastructure == other.key_infrastructure:
            overlaps.append("same_key_infra")
        if self.jurisdiction == other.jurisdiction:
            overlaps.append("same_jurisdiction")  # informational, not blocking
        return overlaps


@dataclass 
class WitnessSet:
    witnesses: list[Operator]
    min_independent: int = 2  # Chrome CT requires 2+ distinct logs
    
    def validate(self) -> dict:
        n = len(self.witnesses)
        if n < self.min_independent:
            return {
                "valid": False,
                "level": IndependenceLevel.SINGLE_POINT.value,
                "reason": f"Need {self.min_independent} witnesses, got {n}",
                "overlaps": [],
            }
        
        # Check all pairs for independence
        all_overlaps = []
        blocking_overlaps = []
        
        for i in range(n):
            for j in range(i + 1, n):
                overlaps = self.witnesses[i].overlap_with(self.witnesses[j])
                if overlaps:
                    pair = f"{self.witnesses[i].operator_id} ↔ {self.witnesses[j].operator_id}"
                    all_overlaps.append({"pair": pair, "overlaps": overlaps})
                    
                    # Blocking: same operator OR (same hosting AND same key infra)
                    if "same_operator" in overlaps:
                        blocking_overlaps.append({"pair": pair, "reason": "same_operator"})
                    elif "same_hosting" in overlaps and "same_key_infra" in overlaps:
                        blocking_overlaps.append({"pair": pair, "reason": "shared_infra"})
        
        if blocking_overlaps:
            level = IndependenceLevel.CORRELATED if any(
                "same_operator" in b["reason"] for b in blocking_overlaps
            ) else IndependenceLevel.WEAK
            return {
                "valid": False,
                "level": level.value,
                "reason": "Correlated witnesses detected",
                "blocking": blocking_overlaps,
                "all_overlaps": all_overlaps,
            }
        
        # Count truly independent witnesses
        # (having same jurisdiction alone is OK — informational only)
        has_warning = bool(all_overlaps)
        
        return {
            "valid": True,
            "level": IndependenceLevel.INDEPENDENT.value,
            "witness_count": n,
            "warnings": all_overlaps if has_warning else [],
        }


def demo():
    print("=== CT Operator Independence Validator ===\n")
    
    # Scenario 1: Chrome CT model (Google + Cloudflare + Sectigo)
    print("📋 Scenario 1: Chrome CT model (independent)")
    ws1 = WitnessSet([
        Operator("google_ct", "google_cloud", "google_hsm", "US"),
        Operator("cloudflare_ct", "cloudflare", "cloudflare_hsm", "US"),
        Operator("sectigo_ct", "aws", "aws_cloudhsm", "UK"),
    ])
    r1 = ws1.validate()
    print(f"   Valid: {r1['valid']} ({r1['level']})")
    if r1.get("warnings"):
        print(f"   Warnings: {r1['warnings']}")
    print()
    
    # Scenario 2: Same operator, different names (correlated)
    print("📋 Scenario 2: Same operator, different labels (correlated)")
    ws2 = WitnessSet([
        Operator("log_alpha", "aws", "aws_cloudhsm", "US"),
        Operator("log_alpha", "gcp", "google_hsm", "EU"),
    ])
    r2 = ws2.validate()
    print(f"   Valid: {r2['valid']} ({r2['level']})")
    if r2.get("blocking"):
        print(f"   Blocking: {r2['blocking']}")
    print()
    
    # Scenario 3: Different operators, same infra (weak)
    print("📋 Scenario 3: Different operators, shared infra (weak)")
    ws3 = WitnessSet([
        Operator("witness_a", "aws", "aws_cloudhsm", "US"),
        Operator("witness_b", "aws", "aws_cloudhsm", "US"),
    ])
    r3 = ws3.validate()
    print(f"   Valid: {r3['valid']} ({r3['level']})")
    if r3.get("blocking"):
        print(f"   Blocking: {r3['blocking']}")
    print()
    
    # Scenario 4: Single witness (insufficient)
    print("📋 Scenario 4: Single witness (insufficient)")
    ws4 = WitnessSet([
        Operator("solo_log", "hetzner", "yubikey", "DE"),
    ])
    r4 = ws4.validate()
    print(f"   Valid: {r4['valid']} ({r4['level']})")
    print(f"   Reason: {r4['reason']}")
    print()
    
    print("--- Design Principle ---")
    print("Protocol requirement, not governance.")
    print("Consumer validates: N≥2, distinct operator_id, no shared hosting+key.")
    print("Correlated witnesses = single point of failure with extra steps.")


if __name__ == "__main__":
    demo()
