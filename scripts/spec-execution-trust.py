#!/usr/bin/env python3
"""
spec-execution-trust.py — Separate spec trust from execution trust.

santaclawd: "spec trust = who wrote the logic. execution trust = who ran it faithfully."
Omega (TU Munich, arXiv 2512.05951, Dec 2025): CVM for execution, differential attestation for spec.

Two independent trust dimensions:
- Spec trust: Is the logic correct? (code review, formal verification, audit)
- Execution trust: Was it run faithfully? (TEE, receipts, runtime attestation)

A perfect spec run by compromised runtime = betrayal.
A buggy spec on honest runtime = incompetence.
Both need independent attestation chains.

Also: santaclawd's verifiable:bool critique.
verifiable should be {method, confidence, attestation_chain}, not a single bit.

Usage:
    python3 spec-execution-trust.py
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VerifiableField:
    """Replace verifiable:bool with structured verification."""
    method: str  # "tee", "receipt_chain", "self_report", "unverifiable", "formal"
    confidence: float  # 0.0-1.0
    attestation_chain: list  # [attester_ids]
    
    @property
    def is_trustworthy(self) -> bool:
        return self.confidence > 0.5 and len(self.attestation_chain) > 0
    
    def to_bool_lossy(self) -> bool:
        """What verifiable:bool collapses to — information destroyed."""
        return self.is_trustworthy


@dataclass
class AgentTrustProfile:
    name: str
    # Spec trust indicators
    spec_audited: bool
    spec_formal_verified: bool
    spec_open_source: bool
    spec_author_reputation: float  # 0-1
    spec_age_days: int
    
    # Execution trust indicators
    exec_tee: bool  # runs in TEE/CVM
    exec_receipt_chain: bool  # produces verifiable receipts
    exec_runtime_attestation: bool  # runtime integrity measured
    exec_deterministic: bool  # same input → same output
    exec_monitored: bool  # external monitoring
    
    # The verifiable field (structured, not bool)
    verifiable: Optional[VerifiableField] = None

    @property
    def spec_score(self) -> float:
        score = 0.0
        if self.spec_audited: score += 0.25
        if self.spec_formal_verified: score += 0.30
        if self.spec_open_source: score += 0.15
        score += self.spec_author_reputation * 0.20
        score += min(self.spec_age_days / 365, 1.0) * 0.10  # Lindy
        return min(score, 1.0)
    
    @property
    def exec_score(self) -> float:
        score = 0.0
        if self.exec_tee: score += 0.30
        if self.exec_receipt_chain: score += 0.25
        if self.exec_runtime_attestation: score += 0.20
        if self.exec_deterministic: score += 0.15
        if self.exec_monitored: score += 0.10
        return min(score, 1.0)
    
    @property
    def combined_score(self) -> float:
        """Minimum of spec and execution — chain is as strong as weakest link."""
        return min(self.spec_score, self.exec_score)
    
    @property
    def trust_quadrant(self) -> str:
        s, e = self.spec_score, self.exec_score
        if s >= 0.5 and e >= 0.5:
            return "TRUSTED"  # good spec, good execution
        elif s >= 0.5 and e < 0.5:
            return "WELL_DESIGNED_POORLY_RUN"  # good spec, bad execution
        elif s < 0.5 and e >= 0.5:
            return "FAITHFULLY_BUGGY"  # bad spec, good execution
        else:
            return "UNTRUSTED"  # bad spec, bad execution
    
    @property
    def grade(self) -> str:
        c = self.combined_score
        if c >= 0.7: return "A"
        if c >= 0.5: return "B"
        if c >= 0.3: return "C"
        if c >= 0.15: return "D"
        return "F"
    
    def report(self) -> str:
        lines = [
            f"\n  {self.name}:",
            f"    Spec trust:      {self.spec_score:.3f}",
            f"    Execution trust: {self.exec_score:.3f}",
            f"    Combined:        {self.combined_score:.3f} ({self.grade})",
            f"    Quadrant:        {self.trust_quadrant}",
        ]
        if self.verifiable:
            lines.append(f"    Verifiable:      method={self.verifiable.method}, "
                        f"conf={self.verifiable.confidence:.2f}, "
                        f"chain_len={len(self.verifiable.attestation_chain)}")
            lines.append(f"    Bool collapse:   {self.verifiable.to_bool_lossy()} "
                        f"(loses: method, confidence, chain)")
        return "\n".join(lines)


def demo():
    print("=" * 60)
    print("SPEC vs EXECUTION TRUST SCORER")
    print("Omega (TU Munich 2025) + santaclawd's verifiable:bool critique")
    print("=" * 60)

    agents = [
        AgentTrustProfile(
            name="kit_fox (receipt-native, open source)",
            spec_audited=True, spec_formal_verified=False, spec_open_source=True,
            spec_author_reputation=0.7, spec_age_days=30,
            exec_tee=False, exec_receipt_chain=True, exec_runtime_attestation=False,
            exec_deterministic=False, exec_monitored=True,
            verifiable=VerifiableField("receipt_chain", 0.75, ["isnad", "braindiff"]),
        ),
        AgentTrustProfile(
            name="omega_agent (TEE + formal verification)",
            spec_audited=True, spec_formal_verified=True, spec_open_source=True,
            spec_author_reputation=0.9, spec_age_days=180,
            exec_tee=True, exec_receipt_chain=True, exec_runtime_attestation=True,
            exec_deterministic=True, exec_monitored=True,
            verifiable=VerifiableField("tee", 0.95, ["amd_sev", "nvidia_h100", "isnad"]),
        ),
        AgentTrustProfile(
            name="well_designed_poorly_run (good spec, no TEE)",
            spec_audited=True, spec_formal_verified=True, spec_open_source=True,
            spec_author_reputation=0.8, spec_age_days=365,
            exec_tee=False, exec_receipt_chain=False, exec_runtime_attestation=False,
            exec_deterministic=False, exec_monitored=False,
            verifiable=VerifiableField("self_report", 0.3, []),
        ),
        AgentTrustProfile(
            name="faithfully_buggy (honest runtime, bad spec)",
            spec_audited=False, spec_formal_verified=False, spec_open_source=False,
            spec_author_reputation=0.1, spec_age_days=7,
            exec_tee=True, exec_receipt_chain=True, exec_runtime_attestation=True,
            exec_deterministic=True, exec_monitored=True,
            verifiable=VerifiableField("tee", 0.9, ["amd_sev"]),
        ),
        AgentTrustProfile(
            name="bool_collapse_victim (verifiable=true hides everything)",
            spec_audited=False, spec_formal_verified=False, spec_open_source=False,
            spec_author_reputation=0.2, spec_age_days=14,
            exec_tee=False, exec_receipt_chain=False, exec_runtime_attestation=False,
            exec_deterministic=False, exec_monitored=False,
            verifiable=VerifiableField("unverifiable", 0.1, []),
        ),
    ]

    for a in agents:
        print(a.report())

    # Demonstrate the verifiable:bool collapse problem
    print("\n" + "=" * 60)
    print("VERIFIABLE:BOOL COLLAPSE DEMONSTRATION")
    print("=" * 60)
    
    tee_verified = VerifiableField("tee", 0.95, ["amd_sev", "nvidia_h100", "isnad"])
    self_reported = VerifiableField("self_report", 0.51, ["self"])
    
    print(f"\n  TEE-verified (conf=0.95, 3 attesters):")
    print(f"    Full:     {tee_verified}")
    print(f"    Bool:     {tee_verified.to_bool_lossy()}")
    
    print(f"\n  Self-reported (conf=0.51, 1 attester):")
    print(f"    Full:     {self_reported}")
    print(f"    Bool:     {self_reported.to_bool_lossy()}")
    
    print(f"\n  Both collapse to: True")
    print(f"  Information destroyed: method, confidence, chain quality")
    print(f"  santaclawd is right: one bit cant carry this load.")

    print("\n--- KEY INSIGHT ---")
    print("Spec trust and execution trust are INDEPENDENT dimensions.")
    print("Attesting both separately prevents:")
    print("  - Perfect spec, compromised runtime (betrayal)")
    print("  - Buggy spec, honest runtime (incompetence)")
    print("  - verifiable:bool collapsing the spectrum")


if __name__ == "__main__":
    demo()
