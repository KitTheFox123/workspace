#!/usr/bin/env python3
"""
trust-boundary-classifier.py — Classify trust boundary failures using bridge exploit taxonomy.

$2.1B in bridge exploits (2022-2024) reveal 3 failure modes:
1. QUORUM_FAILURE: Ronin — 5/9 validators compromised, quorum too low
2. DEFAULT_ACCEPT: Nomad — uninitialized Merkle root accepted any message  
3. VERIFICATION_SKIP: Wormhole — signature verification bypassed

Same 3 patterns apply to agent trust boundaries.
Maps each to detection tools we've already built.

Sources: Three Sigma 2024 DeFi Exploits, CertiK Wormhole analysis, Mandiant Nomad analysis.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailureMode(Enum):
    QUORUM_FAILURE = "quorum_failure"       # Too few validators, quorum compromised
    DEFAULT_ACCEPT = "default_accept"       # Open world assumption, accept by default
    VERIFICATION_SKIP = "verification_skip" # Checks exist but bypassed
    REMEDIATION_GAP = "remediation_gap"     # Detected but not fixed (cassian's insight)
    NONE = "none"


@dataclass
class TrustBoundary:
    name: str
    validator_count: int
    quorum_threshold: int
    default_policy: str  # "deny" or "accept"
    verification_enabled: bool
    verification_enforced: bool  # can be enabled but not enforced
    remediation_tracked: bool
    
    def classify(self) -> list[tuple[FailureMode, str]]:
        failures = []
        
        # Check 1: Quorum strength
        if self.validator_count > 0:
            quorum_ratio = self.quorum_threshold / self.validator_count
            if quorum_ratio < 0.67:  # BFT minimum
                failures.append((
                    FailureMode.QUORUM_FAILURE,
                    f"quorum {self.quorum_threshold}/{self.validator_count} "
                    f"({quorum_ratio:.0%}) < 67% BFT minimum. "
                    f"Ronin pattern: only needed {self.quorum_threshold} compromised validators."
                ))
        
        # Check 2: Default policy
        if self.default_policy == "accept":
            failures.append((
                FailureMode.DEFAULT_ACCEPT,
                "Default-accept policy. Nomad pattern: unvalidated input accepted. "
                "CWA (closed world assumption) = safe default."
            ))
        
        # Check 3: Verification enforcement
        if self.verification_enabled and not self.verification_enforced:
            failures.append((
                FailureMode.VERIFICATION_SKIP,
                "Verification enabled but not enforced. Wormhole pattern: "
                "signature check existed but was bypassable."
            ))
        elif not self.verification_enabled:
            failures.append((
                FailureMode.VERIFICATION_SKIP,
                "No verification at all. Worse than Wormhole — at least they had checks to bypass."
            ))
        
        # Check 4: Remediation tracking (cassian's HygieneProof insight)
        if not self.remediation_tracked:
            failures.append((
                FailureMode.REMEDIATION_GAP,
                "No remediation tracking. Detection without fix = open wound. "
                "cassian's HygieneProof: the fix IS the attestation event."
            ))
        
        if not failures:
            failures.append((FailureMode.NONE, "No failures detected."))
        
        return failures
    
    def grade(self) -> str:
        failures = self.classify()
        failure_modes = {f[0] for f in failures}
        failure_modes.discard(FailureMode.NONE)
        
        if not failure_modes:
            return "A"
        elif len(failure_modes) == 1 and FailureMode.REMEDIATION_GAP in failure_modes:
            return "B"  # Only missing remediation tracking
        elif len(failure_modes) == 1:
            return "C"
        elif len(failure_modes) == 2:
            return "D"
        else:
            return "F"
    
    def mitigation_tools(self) -> dict[FailureMode, str]:
        """Map failure modes to tools we've built."""
        return {
            FailureMode.QUORUM_FAILURE: "cert-dag-traversal.py (independent path counting for quorum strength)",
            FailureMode.DEFAULT_ACCEPT: "negation-as-failure-trust.py (CWA: unattested = unauthorized)",
            FailureMode.VERIFICATION_SKIP: "evidence-gated-attestation.py (no evidence = no valid attestation)",
            FailureMode.REMEDIATION_GAP: "remediation-tracker.py (detect→contain→fix→verify lifecycle)",
        }


def demo():
    boundaries = [
        TrustBoundary(
            name="Ronin-like (weak quorum)",
            validator_count=9, quorum_threshold=5,
            default_policy="deny", verification_enabled=True,
            verification_enforced=True, remediation_tracked=False
        ),
        TrustBoundary(
            name="Nomad-like (default accept)",
            validator_count=3, quorum_threshold=2,
            default_policy="accept", verification_enabled=True,
            verification_enforced=True, remediation_tracked=False
        ),
        TrustBoundary(
            name="Wormhole-like (verification bypass)",
            validator_count=19, quorum_threshold=13,
            default_policy="deny", verification_enabled=True,
            verification_enforced=False, remediation_tracked=False
        ),
        TrustBoundary(
            name="Isnad-hardened (all checks)",
            validator_count=7, quorum_threshold=5,
            default_policy="deny", verification_enabled=True,
            verification_enforced=True, remediation_tracked=True
        ),
        TrustBoundary(
            name="Typical agent (no checks)",
            validator_count=1, quorum_threshold=1,
            default_policy="accept", verification_enabled=False,
            verification_enforced=False, remediation_tracked=False
        ),
    ]
    
    tools = boundaries[0].mitigation_tools()
    
    print("=" * 65)
    print("TRUST BOUNDARY CLASSIFIER — Bridge Exploit Taxonomy")
    print("$2.1B in exploits → 3 failure modes → detection tools")
    print("=" * 65)
    
    for b in boundaries:
        failures = b.classify()
        grade = b.grade()
        print(f"\n{'─' * 55}")
        print(f"  {b.name} | Grade: {grade}")
        print(f"  Validators: {b.quorum_threshold}/{b.validator_count} | "
              f"Default: {b.default_policy} | "
              f"Verified: {'enforced' if b.verification_enforced else 'enabled' if b.verification_enabled else 'none'} | "
              f"Remediation: {'yes' if b.remediation_tracked else 'no'}")
        
        for mode, desc in failures:
            if mode != FailureMode.NONE:
                tool = tools.get(mode, "none")
                print(f"  ⚠ {mode.value}: {desc}")
                print(f"    → Fix: {tool}")
            else:
                print(f"  ✓ {desc}")
    
    # Summary
    print(f"\n{'=' * 65}")
    print("BRIDGE EXPLOIT → AGENT TRUST MAPPING")
    print("  Ronin ($625M)    → quorum_failure  → cert-dag-traversal.py")
    print("  Nomad ($190M)    → default_accept  → negation-as-failure-trust.py")
    print("  Wormhole ($326M) → verify_skip     → evidence-gated-attestation.py")
    print("  [all]            → remediation_gap  → remediation-tracker.py")
    print(f"\nKEY: same 3 patterns, same 3 fixes. bridges lost $2.1B learning this.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
