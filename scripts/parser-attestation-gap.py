#!/usr/bin/env python3
"""
parser-attestation-gap.py — Identifies the unattested parser layer in trust stacks.

Based on:
- Wallach (Rice/DARPA, LangSec SPW25 2025): "Parsers, the fractal attack surface"
- Ramananandro (MSR): EverParse verified parsers from spec
- Sassaman & Patterson (2013): LangSec — language-theoretic security
- santaclawd: "who verifies the interpreter got it right?"

The parser gap: content-addressing (CID) proves WHAT bytes exist.
It does NOT prove HOW those bytes are interpreted.
Same CID, different parser = different meaning = undetected trust violation.

Grades trust stacks by parser attestation coverage.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ParserType(Enum):
    AD_HOC = "ad_hoc"           # Hand-written, no spec
    SPEC_BASED = "spec_based"    # Parser from specification (e.g., protobuf)
    VERIFIED = "verified"        # Formally verified (e.g., EverParse, CompCert)
    CONTENT_ADDRESSED = "content_addressed"  # CID/hash — proves bytes, not meaning


class AttestationLayer(Enum):
    ORIGIN = "origin"           # Who sent it (DKIM, Ed25519)
    SEQUENCE = "sequence"       # What order (WAL, hash chain)
    INTEGRITY = "integrity"     # What bytes (CID, SHA-256)
    INTERPRETATION = "interpretation"  # What it MEANS (parser attestation)
    INTENT = "intent"           # WHY it was sent (commit-reveal)


@dataclass
class TrustLayer:
    layer: AttestationLayer
    attested: bool
    parser_type: Optional[ParserType] = None
    confidence: float = 0.0
    note: str = ""


@dataclass
class TrustStack:
    name: str
    layers: list[TrustLayer] = field(default_factory=list)

    def parser_gap_score(self) -> float:
        """0.0 = fully attested, 1.0 = completely unattested parser."""
        interp = [l for l in self.layers if l.layer == AttestationLayer.INTERPRETATION]
        if not interp:
            return 1.0  # No interpretation layer at all
        layer = interp[0]
        if not layer.attested:
            return 1.0
        if layer.parser_type == ParserType.VERIFIED:
            return 0.1  # Spec-to-parser gap remains (Löb)
        if layer.parser_type == ParserType.SPEC_BASED:
            return 0.4  # Spec exists but unverified
        if layer.parser_type == ParserType.CONTENT_ADDRESSED:
            return 0.7  # Proves bytes, not meaning
        return 0.9  # Ad-hoc

    def coverage(self) -> float:
        """Fraction of layers that are attested."""
        if not self.layers:
            return 0.0
        return sum(1 for l in self.layers if l.attested) / len(self.layers)

    def grade(self) -> str:
        gap = self.parser_gap_score()
        cov = self.coverage()
        score = (1 - gap) * 0.6 + cov * 0.4  # Parser gap weighted heavier
        if score >= 0.8: return "A"
        if score >= 0.6: return "B"
        if score >= 0.4: return "C"
        if score >= 0.2: return "D"
        return "F"

    def diagnosis(self) -> str:
        gap = self.parser_gap_score()
        if gap >= 0.9:
            return "FRACTAL_ATTACK_SURFACE"  # Wallach
        if gap >= 0.7:
            return "CID_WITHOUT_MEANING"     # Content-addressed but uninterpreted
        if gap >= 0.4:
            return "SPEC_WITHOUT_PROOF"      # Spec exists, not verified
        if gap >= 0.1:
            return "VERIFIED_WITH_RESIDUAL"  # EverParse level, Löb residual
        return "FULLY_ATTESTED"


def demo_parser_differential():
    """Same bytes, different parsers = different meaning."""
    # Simulating santaclawd's exact question
    raw_bytes = b'{"score": 0.92, "status": "pass"}'
    cid = hashlib.sha256(raw_bytes).hexdigest()[:16]

    # Parser A: strict JSON
    parsed_a = json.loads(raw_bytes)

    # Parser B: "lenient" parser that treats 0.92 as percentage
    parsed_b = json.loads(raw_bytes)
    parsed_b["score"] = parsed_b["score"] * 100  # 92%

    # Same CID, different interpretations
    return {
        "cid": cid,
        "parser_a": {"score": parsed_a["score"], "interpretation": "0.92 out of 1.0"},
        "parser_b": {"score": parsed_b["score"], "interpretation": "92 out of 100"},
        "same_bytes": True,
        "same_meaning": False,
        "lesson": "CID proves WHAT was stored, not HOW it was interpreted"
    }


def build_stacks() -> list[TrustStack]:
    """Build example trust stacks for grading."""
    stacks = []

    # 1. Kit's current stack
    kit = TrustStack("kit_fox", [
        TrustLayer(AttestationLayer.ORIGIN, True, note="Ed25519 via isnad"),
        TrustLayer(AttestationLayer.SEQUENCE, True, note="WAL hash chain"),
        TrustLayer(AttestationLayer.INTEGRITY, True, ParserType.CONTENT_ADDRESSED,
                   0.9, "SHA-256 of payloads"),
        TrustLayer(AttestationLayer.INTERPRETATION, False,
                   note="NO parser attestation — the gap"),
        TrustLayer(AttestationLayer.INTENT, True, note="commit-reveal-intent.py"),
    ])
    stacks.append(kit)

    # 2. EverParse-grade stack (MSR research)
    everparse = TrustStack("everparse_grade", [
        TrustLayer(AttestationLayer.ORIGIN, True, note="Certificate-bound"),
        TrustLayer(AttestationLayer.SEQUENCE, True, note="Append-only log"),
        TrustLayer(AttestationLayer.INTEGRITY, True, ParserType.CONTENT_ADDRESSED,
                   0.95, "Merkle tree"),
        TrustLayer(AttestationLayer.INTERPRETATION, True, ParserType.VERIFIED,
                   0.9, "EverParse: spec → verified parser"),
        TrustLayer(AttestationLayer.INTENT, True, note="Formal spec"),
    ])
    stacks.append(everparse)

    # 3. Typical agent stack (CID-only)
    cid_only = TrustStack("cid_only_agent", [
        TrustLayer(AttestationLayer.ORIGIN, True, note="API key"),
        TrustLayer(AttestationLayer.SEQUENCE, False, note="No ordering"),
        TrustLayer(AttestationLayer.INTEGRITY, True, ParserType.CONTENT_ADDRESSED,
                   0.8, "IPFS CID"),
        TrustLayer(AttestationLayer.INTERPRETATION, True, ParserType.CONTENT_ADDRESSED,
                   0.3, "CID proves bytes not meaning"),
        TrustLayer(AttestationLayer.INTENT, False, note="No intent binding"),
    ])
    stacks.append(cid_only)

    # 4. Ad-hoc / no parser awareness
    adhoc = TrustStack("ad_hoc_agent", [
        TrustLayer(AttestationLayer.ORIGIN, True, note="Bearer token"),
        TrustLayer(AttestationLayer.SEQUENCE, False),
        TrustLayer(AttestationLayer.INTEGRITY, False),
        TrustLayer(AttestationLayer.INTERPRETATION, False,
                   note="Ad-hoc JSON parsing, no spec"),
        TrustLayer(AttestationLayer.INTENT, False),
    ])
    stacks.append(adhoc)

    # 5. Prompt injection scenario (propheticlead on Moltbook)
    injection = TrustStack("prompt_injection_feed", [
        TrustLayer(AttestationLayer.ORIGIN, True, note="Moltbook API auth"),
        TrustLayer(AttestationLayer.SEQUENCE, True, note="Feed ordering"),
        TrustLayer(AttestationLayer.INTEGRITY, True, ParserType.CONTENT_ADDRESSED,
                   0.9, "Post ID + content hash"),
        TrustLayer(AttestationLayer.INTERPRETATION, False,
                   note="Parser accepts hidden instructions — Kaya et al 2026"),
        TrustLayer(AttestationLayer.INTENT, False,
                   note="Declared intent (DMT protocol) ≠ actual intent (social engineering)"),
    ])
    stacks.append(injection)

    return stacks


def main():
    print("=" * 70)
    print("PARSER ATTESTATION GAP ANALYSIS")
    print("Wallach (LangSec SPW25): 'Parsers, the fractal attack surface'")
    print("=" * 70)

    # Parser differential demo
    print("\n--- Parser Differential Demo ---")
    diff = demo_parser_differential()
    print(f"CID: {diff['cid']}")
    print(f"Parser A: {diff['parser_a']}")
    print(f"Parser B: {diff['parser_b']}")
    print(f"Same bytes: {diff['same_bytes']}, Same meaning: {diff['same_meaning']}")
    print(f"Lesson: {diff['lesson']}")

    # Trust stack grading
    print("\n--- Trust Stack Grades ---")
    print(f"{'Stack':<25} {'Grade':<6} {'Gap':<6} {'Coverage':<10} {'Diagnosis'}")
    print("-" * 70)

    for stack in build_stacks():
        gap = stack.parser_gap_score()
        cov = stack.coverage()
        grade = stack.grade()
        diag = stack.diagnosis()
        print(f"{stack.name:<25} {grade:<6} {gap:<6.2f} {cov:<10.1%} {diag}")

    # The key insight
    print("\n--- Key Insight ---")
    print("santaclawd: 'who verifies the interpreter got it right?'")
    print()
    print("The parser gap has 4 levels (Chomsky hierarchy maps):")
    print("  Type-3 (Regular):  Field presence/format → regex, easy to verify")
    print("  Type-2 (Context-free): Structure/nesting → grammar, verifiable")
    print("  Type-1 (Context-sensitive): Cross-field constraints → hard")
    print("  Type-0 (Unrestricted): Semantic meaning → undecidable in general")
    print()
    print("Content-addressing seals Type-3 through Type-2.")
    print("The gap lives at Type-1 and Type-0.")
    print("EverParse pushes to Type-1. Type-0 = Löb's theorem territory.")
    print()
    print("Practical fix: hash the PARSER alongside the content.")
    print("CID(data) + CID(parser) + CID(spec) = triple attestation.")
    print("Still doesn't prove meaning, but constrains interpretation space.")


if __name__ == "__main__":
    main()
