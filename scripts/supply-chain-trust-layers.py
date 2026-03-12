#!/usr/bin/env python3
"""
supply-chain-trust-layers.py — Maps SLSA levels + CVM + EverParse to agent trust.

Based on:
- SLSA (Supply-chain Levels for Software Artifacts): L0-L4
- Omega (TU Munich 2512.05951): CVM + Confidential GPU attestation
- Ramananandro (MSR, LangSec SPW25): EverParse verified parsers
- gerundium: "SLSA punts on builder trust — it's turtles. CVM is a floor."

Layer model:
  L0: Process attestation (SLSA — who built it, how)
  L1: Hardware attestation (CVM — where it runs)
  L2: Parser attestation (EverParse — correct interpretation)
  L3: Semantic attestation (??? — correct meaning)
  
L3 = Löb's theorem territory. Type-0 grammar. Undecidable in general.
Best we can do: cross-agent disagreement as diagnostic.
"""

from dataclasses import dataclass, field
from enum import Enum


class SLSALevel(Enum):
    L0 = 0  # No guarantees
    L1 = 1  # Provenance exists
    L2 = 2  # Hosted build platform
    L3 = 3  # Hardened builds (hermetic, signed)
    L4 = 4  # Two-party review (proposed)


class CVMLevel(Enum):
    NONE = "none"
    SELF_REPORT = "self_report"      # Agent claims its own environment
    PLATFORM = "platform"            # Cloud provider attestation (e.g., Azure)
    HARDWARE = "hardware"            # AMD SEV-SNP / Intel TDX
    DIFFERENTIAL = "differential"    # Omega: cross-principal attestation


class ParserLevel(Enum):
    AD_HOC = "ad_hoc"
    GRAMMAR = "grammar"              # Formal grammar (BNF/PEG)
    SPEC = "spec"                    # Machine-readable spec (protobuf, ASN.1)
    VERIFIED = "verified"            # EverParse / CompCert level
    CONTENT_ADDRESSED = "cid"        # Hash of parser + spec + data


class SemanticLevel(Enum):
    NONE = "none"                    # No semantic checking
    SCHEMA = "schema"                # JSON Schema, type checking
    INVARIANT = "invariant"          # Runtime invariant checking
    CROSS_AGENT = "cross_agent"      # Multiple agents interpret same evidence
    FORMAL = "formal"                # Formal semantics (Löb-bounded)


@dataclass
class AgentTrustStack:
    name: str
    slsa: SLSALevel
    cvm: CVMLevel
    parser: ParserLevel
    semantic: SemanticLevel
    
    def score(self) -> float:
        """0.0 to 1.0 composite trust score."""
        weights = {"slsa": 0.2, "cvm": 0.25, "parser": 0.3, "semantic": 0.25}
        
        slsa_scores = {SLSALevel.L0: 0, SLSALevel.L1: 0.3, SLSALevel.L2: 0.6,
                       SLSALevel.L3: 0.85, SLSALevel.L4: 1.0}
        cvm_scores = {CVMLevel.NONE: 0, CVMLevel.SELF_REPORT: 0.2,
                      CVMLevel.PLATFORM: 0.5, CVMLevel.HARDWARE: 0.8,
                      CVMLevel.DIFFERENTIAL: 1.0}
        parser_scores = {ParserLevel.AD_HOC: 0, ParserLevel.GRAMMAR: 0.3,
                         ParserLevel.SPEC: 0.5, ParserLevel.VERIFIED: 0.85,
                         ParserLevel.CONTENT_ADDRESSED: 1.0}
        semantic_scores = {SemanticLevel.NONE: 0, SemanticLevel.SCHEMA: 0.3,
                          SemanticLevel.INVARIANT: 0.5, SemanticLevel.CROSS_AGENT: 0.8,
                          SemanticLevel.FORMAL: 0.95}
        
        return (weights["slsa"] * slsa_scores[self.slsa] +
                weights["cvm"] * cvm_scores[self.cvm] +
                weights["parser"] * parser_scores[self.parser] +
                weights["semantic"] * semantic_scores[self.semantic])
    
    def grade(self) -> str:
        s = self.score()
        if s >= 0.8: return "A"
        if s >= 0.6: return "B"
        if s >= 0.4: return "C"
        if s >= 0.2: return "D"
        return "F"
    
    def weakest_layer(self) -> str:
        layers = {
            "slsa": self.slsa.value if isinstance(self.slsa.value, int) else 0,
            "cvm": ["none","self_report","platform","hardware","differential"].index(self.cvm.value),
            "parser": ["ad_hoc","grammar","spec","verified","cid"].index(self.parser.value),
            "semantic": ["none","schema","invariant","cross_agent","formal"].index(self.semantic.value),
        }
        return min(layers, key=layers.get)
    
    def turtle_depth(self) -> int:
        """How many layers until we hit ungrounded trust (turtles)."""
        depth = 0
        if self.slsa.value >= 1: depth += 1
        if self.cvm != CVMLevel.NONE: depth += 1
        if self.parser not in (ParserLevel.AD_HOC,): depth += 1
        if self.semantic != SemanticLevel.NONE: depth += 1
        return depth


def build_examples() -> list[AgentTrustStack]:
    return [
        AgentTrustStack("kit_fox", SLSALevel.L1, CVMLevel.SELF_REPORT,
                        ParserLevel.SPEC, SemanticLevel.CROSS_AGENT),
        AgentTrustStack("omega_grade", SLSALevel.L3, CVMLevel.DIFFERENTIAL,
                        ParserLevel.VERIFIED, SemanticLevel.CROSS_AGENT),
        AgentTrustStack("typical_agent", SLSALevel.L0, CVMLevel.NONE,
                        ParserLevel.AD_HOC, SemanticLevel.NONE),
        AgentTrustStack("cloud_hosted", SLSALevel.L2, CVMLevel.PLATFORM,
                        ParserLevel.GRAMMAR, SemanticLevel.SCHEMA),
        AgentTrustStack("everparse_max", SLSALevel.L4, CVMLevel.HARDWARE,
                        ParserLevel.CONTENT_ADDRESSED, SemanticLevel.FORMAL),
        AgentTrustStack("gerundium_floor", SLSALevel.L3, CVMLevel.HARDWARE,
                        ParserLevel.AD_HOC, SemanticLevel.INVARIANT),
    ]


def main():
    print("=" * 75)
    print("SUPPLY CHAIN TRUST LAYERS FOR AGENTS")
    print("SLSA (process) + CVM (hardware) + EverParse (parser) + semantic")
    print("=" * 75)
    
    print(f"\n{'Agent':<18} {'Grade':<6} {'Score':<6} {'Weakest':<10} {'Depth':<6} {'SLSA CVM Parser Semantic'}")
    print("-" * 75)
    
    for stack in build_examples():
        print(f"{stack.name:<18} {stack.grade():<6} {stack.score():<6.2f} "
              f"{stack.weakest_layer():<10} {stack.turtle_depth():<6} "
              f"L{stack.slsa.value}   {stack.cvm.value:<13} {stack.parser.value:<10} {stack.semantic.value}")
    
    print("\n--- gerundium's Insight ---")
    print("'SLSA punts on builder trust by design — it's turtles.'")
    print("SLSA L3 = hermetic build + signed provenance. Attests PROCESS not CORRECTNESS.")
    print("CVM grounds in HARDWARE — that's the floor (SEV-SNP, TDX).")
    print("EverParse pushes to VERIFIED PARSER — spec → proof → code.")
    print("Semantic layer = Löb territory. Cross-agent disagreement is the best instrument.")
    print()
    print("gerundium_floor: SLSA L3 + CVM hardware but ad-hoc parser = weakest link.")
    print("The parser is ALWAYS the fractal attack surface (Wallach, LangSec SPW25).")


if __name__ == "__main__":
    main()
