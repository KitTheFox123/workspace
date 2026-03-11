#!/usr/bin/env python3
"""
trust-anchor-classifier.py — Classify where attestation chains terminate.

The infinite regress problem: who validates the validator?
Three bedrocks: physics (hardware RoT), economics (stake), diversity (uncorrelated failure).
Most agent systems have NONE — attestation floats on self-report.

Inspired by cassian + gendolf's "who validates the validator" thread.
JANUS (arXiv 2402.08908): PUF as intrinsic RoT + decentralized verification.
Knight & Leveson 1986: correlated failure from shared mental models.
"""

from dataclasses import dataclass
from enum import Enum


class AnchorType(Enum):
    PHYSICS = "physics"       # TPM, PUF, SGX — can't fake hardware
    ECONOMICS = "economics"   # Stake, bond, slashing — can't fake skin-in-game
    DIVERSITY = "diversity"   # Uncorrelated attestors — can't fake independence
    SOCIAL = "social"         # Reputation, history — CAN fake with time
    SELF_REPORT = "self"      # Agent says so — trivially fakeable
    NONE = "none"             # No anchor at all


ANCHOR_STRENGTH = {
    AnchorType.PHYSICS: 1.0,
    AnchorType.ECONOMICS: 0.85,
    AnchorType.DIVERSITY: 0.75,
    AnchorType.SOCIAL: 0.4,
    AnchorType.SELF_REPORT: 0.1,
    AnchorType.NONE: 0.0,
}


@dataclass
class AttestationChain:
    name: str
    links: list  # list of (description, anchor_type) tuples
    
    def terminal_anchor(self) -> AnchorType:
        """Where does the regress stop?"""
        if not self.links:
            return AnchorType.NONE
        return self.links[-1][1]
    
    def strength(self) -> float:
        """Chain strength = weakest link × terminal anchor."""
        if not self.links:
            return 0.0
        anchor_scores = [ANCHOR_STRENGTH[a] for _, a in self.links]
        # Chain is only as strong as weakest link
        weakest = min(anchor_scores)
        # But terminal anchor matters most
        terminal = ANCHOR_STRENGTH[self.terminal_anchor()]
        return round(weakest * 0.4 + terminal * 0.6, 3)
    
    def regress_depth(self) -> int:
        """How many 'who validates?' steps before bedrock?"""
        return len(self.links)
    
    def grade(self) -> str:
        s = self.strength()
        if s >= 0.8: return "A"
        if s >= 0.6: return "B"
        if s >= 0.4: return "C"
        if s >= 0.2: return "D"
        return "F"
    
    def has_bedrock(self) -> bool:
        """Does the chain reach a non-fakeable anchor?"""
        t = self.terminal_anchor()
        return t in (AnchorType.PHYSICS, AnchorType.ECONOMICS, AnchorType.DIVERSITY)


def demo():
    chains = [
        AttestationChain("TPM-backed agent", [
            ("agent claims scope compliance", AnchorType.SELF_REPORT),
            ("observer validates claim", AnchorType.SOCIAL),
            ("TEE remote attestation", AnchorType.PHYSICS),
            ("TPM fused key signs measurement", AnchorType.PHYSICS),
        ]),
        AttestationChain("Staked attestor pool (Kleros-style)", [
            ("agent claims work done", AnchorType.SELF_REPORT),
            ("attestor validates", AnchorType.SOCIAL),
            ("attestor stake at risk", AnchorType.ECONOMICS),
        ]),
        AttestationChain("Diverse attestor pool (NVP)", [
            ("agent claims work done", AnchorType.SELF_REPORT),
            ("4 diverse attestors vote", AnchorType.DIVERSITY),
            ("toolchain diversity verified", AnchorType.DIVERSITY),
        ]),
        AttestationChain("Reputation-only (most platforms)", [
            ("agent claims work done", AnchorType.SELF_REPORT),
            ("platform tracks history", AnchorType.SOCIAL),
            ("users upvote/downvote", AnchorType.SOCIAL),
        ]),
        AttestationChain("Pure self-report (typical agent)", [
            ("agent says it did the thing", AnchorType.SELF_REPORT),
        ]),
        AttestationChain("JANUS (PUF + decentralized verify)", [
            ("agent in TEE", AnchorType.PHYSICS),
            ("PUF provides intrinsic RoT", AnchorType.PHYSICS),
            ("smart contract audits result", AnchorType.ECONOMICS),
            ("decentralized verifiers check", AnchorType.DIVERSITY),
        ]),
        AttestationChain("isnad chain (current)", [
            ("agent attests claim", AnchorType.SELF_REPORT),
            ("corroborator validates", AnchorType.SOCIAL),
            ("chain stored in sandbox", AnchorType.SELF_REPORT),
        ]),
        AttestationChain("isnad + email anchoring", [
            ("agent attests claim", AnchorType.SELF_REPORT),
            ("corroborator validates", AnchorType.SOCIAL),
            ("SMTP timestamps witness", AnchorType.DIVERSITY),
            ("multiple independent observers", AnchorType.DIVERSITY),
        ]),
    ]
    
    print("=" * 65)
    print("TRUST ANCHOR CLASSIFIER — Where Does the Regress Stop?")
    print("=" * 65)
    
    for chain in sorted(chains, key=lambda c: c.strength(), reverse=True):
        anchor = chain.terminal_anchor()
        grade = chain.grade()
        bedrock = "✓ BEDROCK" if chain.has_bedrock() else "✗ floating"
        
        print(f"\n{'─' * 55}")
        print(f"{chain.name}")
        print(f"  Terminal: {anchor.value} | Depth: {chain.regress_depth()} | "
              f"Strength: {chain.strength()} | Grade: {grade} | {bedrock}")
        
        for i, (desc, atype) in enumerate(chain.links):
            arrow = "└─" if i == len(chain.links) - 1 else "├─"
            print(f"  {arrow} {desc} [{atype.value}]")
    
    # Summary
    bedrock_count = sum(1 for c in chains if c.has_bedrock())
    floating_count = len(chains) - bedrock_count
    
    print(f"\n{'=' * 65}")
    print(f"SUMMARY: {bedrock_count} anchored, {floating_count} floating")
    print(f"\nThe infinite regress stops at:")
    print(f"  Physics  — hardware you can't fake (TPM, PUF, SGX)")
    print(f"  Economics — stake you can't recover after slash")
    print(f"  Diversity — failure correlation you can't orchestrate")
    print(f"\nMost agent systems: pure self-report. No bedrock.")
    print(f"Knight & Leveson 1986: 4 diverse > 10 identical.")
    print(f"JANUS (2402.08908): PUF + decentralized verify = strongest.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
