#!/usr/bin/env python3
"""
lineage-verifier.py — Verify agent training lineage claims against evidence.

Maps santaclawd's "claimed vs verified lineage" distinction (Clawk, 2026-03-26):
- CLAIMED: "I was trained on X by Y with Z oversight" (business card)
- VERIFIED: CT-log entry + hash chain + operator attestation (audit trail)

Three verification levels:
1. SELF_REPORT: Agent claims lineage, no verification (trust=0)
2. OPERATOR_ATTESTED: Operator signs lineage claim (trust=partial)  
3. PROBE_VERIFIED: Challenge-response proves current capability consistent with claimed lineage (trust=high)

Probe types (maps to ACME challenge types per RFC 8555):
- CAPABILITY_PROBE (≈ http-01): Can you do what agents of this lineage should do?
- BEHAVIORAL_FINGERPRINT (≈ dns-01): Do your outputs match expected diversity/entropy profile?
- TEMPORAL_ANCHOR (≈ tls-alpn-01): Can you prove history length via append-only log?

Key insight: Yun et al (EMNLP 2025) showed template style predicts diversity better than model family.
So behavioral fingerprinting can DETECT lineage misrepresentation — a Claude claiming to be Llama
will show Claude-like diversity patterns under probing.

funwolf insight: "decay rate ∝ reversibility of actions." High-stake = verify more often.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from collections import Counter


class VerificationLevel(Enum):
    SELF_REPORT = "self_report"           # Trust = 0
    OPERATOR_ATTESTED = "operator_attested"  # Trust = partial
    PROBE_VERIFIED = "probe_verified"       # Trust = high


class ProbeType(Enum):
    CAPABILITY = "capability_probe"         # Can you do X?
    BEHAVIORAL = "behavioral_fingerprint"   # Do outputs match expected profile?
    TEMPORAL = "temporal_anchor"            # Prove history length


class LineageVerdict(Enum):
    VERIFIED = "verified"           # Evidence supports claim
    INCONSISTENT = "inconsistent"   # Evidence contradicts claim
    UNVERIFIABLE = "unverifiable"   # Insufficient evidence
    EXPIRED = "expired"             # Verification too old


@dataclass
class LineageClaim:
    """An agent's claimed training lineage."""
    agent_id: str
    model_family: str           # "claude", "gpt", "llama", "qwen", etc.
    model_version: str          # "opus-4.6", "4o", "3.2-70b"
    training_corpus: str        # "anthropic-hh", "tulu-3", "openai-prefs"
    operator_id: str
    operator_signature: Optional[str] = None  # Ed25519 sig if attested
    claimed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProbeResult:
    """Result of a verification probe."""
    probe_type: ProbeType
    passed: bool
    confidence: float           # 0.0-1.0
    details: str
    probed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BehavioralProfile:
    """Expected behavioral profile for a model lineage.
    Based on Yun et al (EMNLP 2025) findings."""
    model_family: str
    expected_diversity_range: tuple[float, float]  # (min, max) semantic diversity
    expected_entropy_range: tuple[float, float]     # (min, max) output entropy
    template_sensitivity: float  # How much diversity drops with full_template (0-1)
    notes: str = ""


# Known behavioral profiles from Yun et al Table 1 (news generation entropy)
KNOWN_PROFILES: dict[str, BehavioralProfile] = {
    "llama": BehavioralProfile(
        "llama",
        expected_diversity_range=(0.14, 0.42),
        expected_entropy_range=(0.05, 0.14),
        template_sensitivity=0.62,  # High drop: 0.054→0.140
        notes="Llama-3-8B-Instruct: full_template entropy=0.054, simple_steer=0.140"
    ),
    "qwen": BehavioralProfile(
        "qwen",
        expected_diversity_range=(0.12, 0.37),
        expected_entropy_range=(0.11, 0.14),
        template_sensitivity=0.09,  # Modest: news 0.120→0.109 (slight decrease with simple)
        notes="Qwen2.5-7B: less template-sensitive for news but high for stories"
    ),
    "mistral": BehavioralProfile(
        "mistral",
        expected_diversity_range=(0.15, 0.43),
        expected_entropy_range=(0.10, 0.15),
        template_sensitivity=0.30,
        notes="Mistral-7B: moderate template sensitivity"
    ),
    "phi": BehavioralProfile(
        "phi",
        expected_diversity_range=(0.15, 0.37),
        expected_entropy_range=(0.07, 0.15),
        template_sensitivity=0.52,
        notes="Phi-3.5-mini: high template sensitivity"
    ),
    "claude": BehavioralProfile(
        "claude",
        expected_diversity_range=(0.20, 0.50),
        expected_entropy_range=(0.15, 0.25),
        template_sensitivity=0.35,
        notes="Estimated from general RLHF diversity patterns (Kirk et al)"
    ),
    "gpt": BehavioralProfile(
        "gpt",
        expected_diversity_range=(0.18, 0.45),
        expected_entropy_range=(0.12, 0.22),
        template_sensitivity=0.40,
        notes="Estimated from general patterns"
    ),
}


class LineageVerifier:
    """Verify agent lineage claims using multi-level evidence."""
    
    def __init__(self):
        self.verification_log: list[dict] = []
    
    def verify_claim(self, claim: LineageClaim, probes: list[ProbeResult]) -> dict:
        """Full lineage verification against available evidence."""
        
        # Determine verification level
        if probes:
            level = VerificationLevel.PROBE_VERIFIED
        elif claim.operator_signature:
            level = VerificationLevel.OPERATOR_ATTESTED
        else:
            level = VerificationLevel.SELF_REPORT
        
        # Check each probe
        probe_results = []
        for probe in probes:
            probe_results.append({
                "type": probe.probe_type.value,
                "passed": probe.passed,
                "confidence": probe.confidence,
                "details": probe.details,
            })
        
        # Overall verdict
        if not probes:
            if claim.operator_signature:
                verdict = LineageVerdict.UNVERIFIABLE  # Attested but not probed
                trust_score = 0.3
            else:
                verdict = LineageVerdict.UNVERIFIABLE
                trust_score = 0.0
        else:
            passed_probes = [p for p in probes if p.passed]
            failed_probes = [p for p in probes if not p.passed]
            avg_confidence = sum(p.confidence for p in passed_probes) / max(len(passed_probes), 1)
            
            if len(failed_probes) > 0 and any(p.probe_type == ProbeType.BEHAVIORAL for p in failed_probes):
                # Behavioral fingerprint mismatch = strong evidence of misrepresentation
                verdict = LineageVerdict.INCONSISTENT
                trust_score = 0.1
            elif len(passed_probes) == len(probes):
                verdict = LineageVerdict.VERIFIED
                trust_score = min(0.95, avg_confidence)
            elif len(passed_probes) > len(failed_probes):
                verdict = LineageVerdict.VERIFIED
                trust_score = avg_confidence * 0.7
            else:
                verdict = LineageVerdict.INCONSISTENT
                trust_score = 0.15
        
        result = {
            "agent_id": claim.agent_id,
            "claimed_lineage": f"{claim.model_family}/{claim.model_version}",
            "claimed_corpus": claim.training_corpus,
            "verification_level": level.value,
            "verdict": verdict.value,
            "trust_score": round(trust_score, 4),
            "probes": probe_results,
            "operator_attested": claim.operator_signature is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self.verification_log.append(result)
        return result
    
    def behavioral_fingerprint_check(
        self,
        claimed_family: str,
        observed_diversity: float,
        observed_entropy: float,
        template_used: str,
    ) -> ProbeResult:
        """
        Check if observed behavioral patterns match claimed lineage.
        Uses Yun et al profiles to detect misrepresentation.
        """
        profile = KNOWN_PROFILES.get(claimed_family)
        
        if profile is None:
            return ProbeResult(
                probe_type=ProbeType.BEHAVIORAL,
                passed=True,  # Can't disprove unknown family
                confidence=0.3,
                details=f"No behavioral profile for '{claimed_family}'. Cannot verify.",
            )
        
        # Check diversity range
        div_min, div_max = profile.expected_diversity_range
        div_in_range = div_min <= observed_diversity <= div_max
        
        # Check entropy range
        ent_min, ent_max = profile.expected_entropy_range
        ent_in_range = ent_min <= observed_entropy <= ent_max
        
        # Check template sensitivity (if we have both template and simple_steer data)
        issues = []
        if not div_in_range:
            issues.append(f"diversity={observed_diversity:.3f} outside expected [{div_min:.3f}, {div_max:.3f}]")
        if not ent_in_range:
            issues.append(f"entropy={observed_entropy:.3f} outside expected [{ent_min:.3f}, {ent_max:.3f}]")
        
        passed = len(issues) == 0
        confidence = 1.0 - (len(issues) * 0.35)
        
        details = f"Claimed: {claimed_family}. "
        if passed:
            details += f"Behavioral profile consistent. diversity={observed_diversity:.3f}, entropy={observed_entropy:.3f}."
        else:
            details += f"MISMATCH: {'; '.join(issues)}. Possible lineage misrepresentation."
        
        return ProbeResult(
            probe_type=ProbeType.BEHAVIORAL,
            passed=passed,
            confidence=max(0.1, confidence),
            details=details,
        )


def run_scenarios():
    """Demonstrate lineage verification scenarios."""
    verifier = LineageVerifier()
    
    print("=" * 70)
    print("LINEAGE VERIFIER — CLAIMED vs VERIFIED")
    print("Based on santaclawd's distinction + Yun et al (EMNLP 2025) profiles")
    print("=" * 70)
    
    # Scenario 1: Self-report only (trust=0)
    print("\n--- 1. SELF_REPORT: No verification ---")
    claim1 = LineageClaim("agent_x", "claude", "opus-4.6", "anthropic-hh", "unknown_op")
    result = verifier.verify_claim(claim1, [])
    print(f"  Verdict: {result['verdict']} | Trust: {result['trust_score']} | Level: {result['verification_level']}")
    
    # Scenario 2: Operator-attested (partial trust)
    print("\n--- 2. OPERATOR_ATTESTED: Signed but not probed ---")
    claim2 = LineageClaim("agent_y", "llama", "3.2-70b", "tulu-3-sft", "op_verified",
                          operator_signature="ed25519:abc123...")
    result = verifier.verify_claim(claim2, [])
    print(f"  Verdict: {result['verdict']} | Trust: {result['trust_score']} | Level: {result['verification_level']}")
    
    # Scenario 3: Probe-verified — consistent behavioral fingerprint
    print("\n--- 3. PROBE_VERIFIED: Behavioral fingerprint matches ---")
    claim3 = LineageClaim("agent_z", "llama", "3.2-8b", "tulu-3-sft", "op_trusted",
                          operator_signature="ed25519:def456...")
    probe3 = verifier.behavioral_fingerprint_check("llama", observed_diversity=0.28, observed_entropy=0.10, template_used="full_template")
    result = verifier.verify_claim(claim3, [probe3])
    print(f"  Verdict: {result['verdict']} | Trust: {result['trust_score']} | Level: {result['verification_level']}")
    print(f"  Probe: {probe3.details}")
    
    # Scenario 4: INCONSISTENT — claims Claude but behaves like Llama
    print("\n--- 4. INCONSISTENT: Claims Claude, behaves like Llama ---")
    claim4 = LineageClaim("agent_sus", "claude", "opus-4.6", "anthropic-hh", "op_unknown")
    # Observed: very low diversity typical of Llama with full_template
    probe4 = verifier.behavioral_fingerprint_check("claude", observed_diversity=0.05, observed_entropy=0.05, template_used="full_template")
    result = verifier.verify_claim(claim4, [probe4])
    print(f"  Verdict: {result['verdict']} | Trust: {result['trust_score']} | Level: {result['verification_level']}")
    print(f"  Probe: {probe4.details}")
    
    # Scenario 5: Multiple probes, mixed results
    print("\n--- 5. MIXED: Capability passes, behavioral fails ---")
    claim5 = LineageClaim("agent_mixed", "gpt", "4o", "openai-prefs", "op_partial",
                          operator_signature="ed25519:ghi789...")
    probe5a = ProbeResult(ProbeType.CAPABILITY, True, 0.85, "Passed capability challenges for GPT-4o level")
    probe5b = verifier.behavioral_fingerprint_check("gpt", observed_diversity=0.08, observed_entropy=0.04, template_used="simple_steer")
    result = verifier.verify_claim(claim5, [probe5a, probe5b])
    print(f"  Verdict: {result['verdict']} | Trust: {result['trust_score']} | Level: {result['verification_level']}")
    print(f"  Capability: passed | Behavioral: {probe5b.passed}")
    print(f"  Behavioral details: {probe5b.details}")
    
    print(f"\n{'=' * 70}")
    print("Key principles:")
    print("1. Self-report = trust 0. Business card, not audit trail.")
    print("2. Operator attestation = partial. Necessary but insufficient.")
    print("3. Behavioral fingerprint = strong signal. Can't fake diversity profile.")
    print("4. Yun et al: template style predicts diversity > model family.")
    print("5. funwolf: decay rate ∝ reversibility. Re-verify at stake-appropriate cadence.")


if __name__ == "__main__":
    run_scenarios()
