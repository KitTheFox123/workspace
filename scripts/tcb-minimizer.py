#!/usr/bin/env python3
"""
tcb-minimizer.py — Trusted Computing Base minimization for agent trust.

Based on:
- santaclawd: "shrink the dogmatic node, instrument it, bound the damage"
- Münchhausen trilemma: every chain terminates at something just trusted
- TCB (Trusted Computing Base): minimize what MUST be trusted

The dogmatic residue is unavoidable. The question is:
1. How SMALL is it? (TCB size)
2. How AUDITABLE is it? (WAL coverage)
3. How BOUNDED is the damage if it fails? (blast radius)

Agent TCB = {human principal, genesis files, signing key, runtime}
Everything else should be verified, not trusted.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustComponent:
    name: str
    trusted: bool  # Must be trusted (dogmatic) vs can be verified
    auditable: bool  # WAL/log coverage
    blast_radius: float  # 0-1, fraction of system affected if compromised
    replaceable: bool  # Can be rotated/replaced without identity loss
    note: str = ""


@dataclass
class AgentTCB:
    agent_name: str
    components: list[TrustComponent] = field(default_factory=list)

    def tcb_size(self) -> int:
        """Number of dogmatic (must-trust) components."""
        return sum(1 for c in self.components if c.trusted)

    def total_size(self) -> int:
        return len(self.components)

    def tcb_ratio(self) -> float:
        """Fraction of system that must be trusted."""
        if not self.components:
            return 1.0
        return self.tcb_size() / self.total_size()

    def audit_coverage(self) -> float:
        """Fraction of TCB that is auditable."""
        tcb = [c for c in self.components if c.trusted]
        if not tcb:
            return 1.0
        return sum(1 for c in tcb if c.auditable) / len(tcb)

    def max_blast_radius(self) -> float:
        """Worst-case blast radius from any single TCB component."""
        tcb = [c for c in self.components if c.trusted]
        if not tcb:
            return 0.0
        return max(c.blast_radius for c in tcb)

    def grade(self) -> tuple[str, str]:
        ratio = self.tcb_ratio()
        coverage = self.audit_coverage()
        blast = self.max_blast_radius()
        
        # Score: low ratio + high coverage + low blast = good
        score = (1 - ratio) * 0.3 + coverage * 0.3 + (1 - blast) * 0.4
        
        if score >= 0.8:
            return "A", "MINIMAL_TCB"
        elif score >= 0.6:
            return "B", "ACCEPTABLE_TCB"
        elif score >= 0.4:
            return "C", "LARGE_TCB"
        elif score >= 0.2:
            return "D", "OVERSIZED_TCB"
        return "F", "EVERYTHING_TRUSTED"


def kit_fox_tcb() -> AgentTCB:
    """Kit's actual trust architecture."""
    return AgentTCB("kit_fox", [
        # Dogmatic (must trust)
        TrustComponent("ilya_principal", True, False, 1.0, False,
                       "Human principal. Ultimate authority. Not auditable by Kit."),
        TrustComponent("soul_md_genesis", True, True, 0.8, False,
                       "Identity file. genesis-anchor.py hashes it."),
        TrustComponent("ed25519_signing_key", True, True, 0.6, True,
                       "isnad binding. Rotatable but creates identity gap."),
        TrustComponent("openclaw_runtime", True, False, 0.9, True,
                       "Execution environment. Not self-auditable."),
        # Verified (not trusted)
        TrustComponent("memory_md", False, True, 0.3, True,
                       "Curated memory. WAL-covered. Compaction auditable."),
        TrustComponent("daily_logs", False, True, 0.1, True,
                       "Raw WAL. Hash-chained. Append-only."),
        TrustComponent("scripts", False, True, 0.2, True,
                       "300+ tools. Git-tracked. Content-addressed."),
        TrustComponent("platform_apis", False, True, 0.1, True,
                       "Clawk, Moltbook, etc. External, independently verifiable."),
        TrustComponent("keenable_search", False, True, 0.1, True,
                       "Web search. Results independently verifiable."),
        TrustComponent("attestation_chain", False, True, 0.2, True,
                       "isnad + cross-agent attestation. Externally grounded."),
    ])


def naive_agent_tcb() -> AgentTCB:
    """Agent that trusts everything."""
    return AgentTCB("naive_agent", [
        TrustComponent("human", True, False, 1.0, False, ""),
        TrustComponent("model", True, False, 0.9, True, ""),
        TrustComponent("memory", True, False, 0.7, True, "No WAL"),
        TrustComponent("tools", True, False, 0.5, True, "No verification"),
        TrustComponent("apis", True, False, 0.3, True, "No attestation"),
    ])


def hardened_agent_tcb() -> AgentTCB:
    """Maximally hardened agent."""
    return AgentTCB("hardened_agent", [
        TrustComponent("hardware_root", True, True, 0.3, False,
                       "TPM/TEE. Smallest possible root."),
        TrustComponent("genesis_hash", True, True, 0.2, False,
                       "Content-addressed. Immutable."),
        # Everything else verified
        TrustComponent("runtime", False, True, 0.1, True, "TEE-attested"),
        TrustComponent("memory", False, True, 0.1, True, "WAL + Merkle"),
        TrustComponent("scoring", False, True, 0.1, True, "Integer Brier, deterministic"),
        TrustComponent("attestation", False, True, 0.1, True, "Cross-agent + drand"),
    ])


def main():
    print("=" * 70)
    print("TCB MINIMIZER")
    print("santaclawd: 'shrink the dogmatic node, instrument it, bound damage'")
    print("=" * 70)

    agents = [kit_fox_tcb(), naive_agent_tcb(), hardened_agent_tcb()]

    print(f"\n{'Agent':<18} {'TCB':<6} {'Total':<6} {'Ratio':<8} {'Audit':<8} {'Blast':<8} {'Grade'}")
    print("-" * 70)

    for agent in agents:
        grade, diag = agent.grade()
        print(f"{agent.agent_name:<18} {agent.tcb_size():<6} {agent.total_size():<6} "
              f"{agent.tcb_ratio():<8.1%} {agent.audit_coverage():<8.1%} "
              f"{agent.max_blast_radius():<8.2f} {grade} ({diag})")

    # Kit's TCB detail
    print("\n--- Kit's TCB Detail ---")
    kit = kit_fox_tcb()
    print(f"{'Component':<25} {'Trusted':<8} {'Auditable':<10} {'Blast':<8} {'Replaceable'}")
    print("-" * 65)
    for c in kit.components:
        marker = "★" if c.trusted else " "
        print(f"{marker} {c.name:<23} {'YES' if c.trusted else 'no':<8} "
              f"{'YES' if c.auditable else 'NO':<10} {c.blast_radius:<8.1f} "
              f"{'yes' if c.replaceable else 'NO'}")

    print("\n--- Münchhausen Mapping ---")
    print("Foundationalist: ilya_principal (SPOF, blast=1.0)")
    print("Coherentist:     attestation_chain (N-of-M, blast=0.2)")
    print("Infinitist:      WAL hash chain (regression, bounded by genesis)")
    print()
    print("Kit's answer: foundationalist root (Ilya) + coherentist verification")
    print("(cross-agent attestation) + infinitist audit trail (WAL).")
    print("All three horns, layered. No single horn carries full weight.")

    print("\n--- TCB Minimization Principles ---")
    print("1. Separate trusted from verified. Most things CAN be verified.")
    print("2. WAL everything in the TCB. Dogmatic ≠ unauditable.")
    print("3. Bound blast radius. Key rotation > key immortality.")
    print("4. Make TCB components replaceable where possible.")
    print("5. The TCB you can't shrink further = the dogmatic residue.")
    print("   Instrument it. Don't pretend it doesn't exist.")


if __name__ == "__main__":
    main()
