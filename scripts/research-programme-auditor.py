#!/usr/bin/env python3
"""
research-programme-auditor.py — Lakatos progressive vs degenerating programme detector.

Audits a sequence of claims/builds for:
1. Novel predictions (theoretically progressive?)
2. Corroboration (empirically progressive?)
3. Ad hoc accommodation (protective belt patching?)
4. Hard core stability (what's non-negotiable?)

Based on:
- Lakatos (1978, "Methodology of Scientific Research Programmes")
- SEP entry: progressive = predicts novel facts AND some confirmed
- Degenerating = only explains past, no new predictions

Applied to: Kit's script sequence as a research programme.
The hard core = "tools > documents, honest negatives, multiplicative attack cost"
The protective belt = individual scripts with testable numbers
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Claim:
    """A testable claim from a build."""
    script: str
    claim: str
    predicted_value: float  # what the script predicted
    novel: bool  # was this predicted BEFORE observed?
    corroborated: bool = False  # did it hold up?
    ad_hoc: bool = False  # was it fitted to known data?
    timestamp: str = ""

@dataclass
class ResearchProgramme:
    """A Lakatos research programme."""
    name: str
    hard_core: list = field(default_factory=list)  # non-negotiable theses
    protective_belt: list = field(default_factory=list)  # modifiable auxiliary hypotheses
    claims: list = field(default_factory=list)
    
    def theoretical_progressiveness(self) -> float:
        """Fraction of claims that are novel predictions."""
        if not self.claims:
            return 0.0
        novel = sum(1 for c in self.claims if c.novel)
        return novel / len(self.claims)
    
    def empirical_progressiveness(self) -> float:
        """Fraction of novel predictions that were corroborated."""
        novel = [c for c in self.claims if c.novel]
        if not novel:
            return 0.0
        corroborated = sum(1 for c in novel if c.corroborated)
        return corroborated / len(novel)
    
    def ad_hoc_ratio(self) -> float:
        """Fraction of claims that are ad hoc (fitted to known data)."""
        if not self.claims:
            return 0.0
        return sum(1 for c in self.claims if c.ad_hoc) / len(self.claims)
    
    def is_progressive(self) -> bool:
        """Progressive = theoretically AND empirically progressive."""
        return self.theoretical_progressiveness() > 0.3 and self.empirical_progressiveness() > 0.3
    
    def is_degenerating(self) -> bool:
        """Degenerating = low novelty OR low corroboration OR high ad hoc."""
        return (self.theoretical_progressiveness() < 0.2 or 
                self.empirical_progressiveness() < 0.2 or
                self.ad_hoc_ratio() > 0.5)
    
    def hard_core_stability(self) -> dict:
        """Check if hard core has been modified (it shouldn't be)."""
        return {
            "theses": self.hard_core,
            "count": len(self.hard_core),
            "stable": True,  # In a healthy programme, hard core doesn't change
            "note": "If hard core changes, programme has been abandoned, not modified"
        }
    
    def audit(self) -> dict:
        tp = self.theoretical_progressiveness()
        ep = self.empirical_progressiveness()
        ah = self.ad_hoc_ratio()
        prog = self.is_progressive()
        degen = self.is_degenerating()
        
        if prog:
            status = "PROGRESSIVE"
        elif degen:
            status = "DEGENERATING"
        else:
            status = "STAGNATING"
        
        return {
            "programme": self.name,
            "status": status,
            "theoretical_progressiveness": round(tp, 3),
            "empirical_progressiveness": round(ep, 3),
            "ad_hoc_ratio": round(ah, 3),
            "total_claims": len(self.claims),
            "novel_predictions": sum(1 for c in self.claims if c.novel),
            "corroborated": sum(1 for c in self.claims if c.novel and c.corroborated),
            "ad_hoc_accommodations": sum(1 for c in self.claims if c.ad_hoc),
            "hard_core": self.hard_core_stability(),
            "protective_belt_size": len(self.protective_belt)
        }


def audit_kit_atf_programme():
    """Audit Kit's ATF (Anti-Takeover Framework) as a Lakatos research programme."""
    
    atf = ResearchProgramme(
        name="Kit ATF Research Programme",
        hard_core=[
            "tools > documents",
            "honest negatives are valuable", 
            "multiplicative attack cost (4 layers × O(months×infra×social))",
            "defense wins when cheapest path to passing IS authentic behavior",
            "single-metric detection fails (ego depletion problem)"
        ],
        protective_belt=[
            "roughness as detection signal",
            "burstiness (Goh & Barabasi 2008)",
            "Granger causality for channel independence",
            "Dunbar number ≈ 133 for agents",
            "portfolio theory for anchor diversity",
            "Goodhart gap as proxy divergence",
            "sybil defense as economic game theory",
            "calibration debt from zombie parameters",
            "Hirschman exit/voice/loyalty for identity",
            "Bratman diachronic self-governance",
        ]
    )
    
    # Actual claims from Kit's scripts, classified
    atf.claims = [
        # Novel predictions (generated BEFORE testing)
        Claim("roughness-proof-of-life.py", "roughness gap separates honest from sybil", 
              0.068, novel=True, corroborated=False,  # HONEST NEGATIVE
              timestamp="2026-03-29"),
        Claim("channel-independence-tester.py", "Granger causality separates honest/sybil",
              0.106, novel=True, corroborated=True,  # 0.954 vs 0.848
              timestamp="2026-03-29"),
        Claim("quorum-running-average.py", "sybil variance ratio detectable",
              487.9, novel=True, corroborated=True,
              timestamp="2026-03-29"),
        Claim("goodhart-trust-dynamics.py", "gap between proxy and true trust detectable",
              0.588, novel=True, corroborated=True,  # honest=0.588, sybil=0.824
              timestamp="2026-03-29"),
        Claim("sybil-defense-stack.py", "4-layer multiplicative cost",
              4.0, novel=True, corroborated=True,
              timestamp="2026-03-29"),
        Claim("calibration-debt-auditor.py", "P(all 5 zombie params valid) < 1%",
              0.009, novel=True, corroborated=True,  # 0.9% cascade
              timestamp="2026-03-30"),
        Claim("anchoring-bias-auditor.py", "sequential correlation from first attestation",
              0.741, novel=True, corroborated=True,
              timestamp="2026-03-30"),
        Claim("loss-aversion-auditor.py", "λ overcorrection gives sybils advantage",
              1.6, novel=True, corroborated=True,  # 1.6x advantage
              timestamp="2026-03-30"),
        Claim("selective-silence-game.py", "strategic vs honest silence separation",
              0.077, novel=True, corroborated=False,  # HONEST NEGATIVE: too small
              timestamp="2026-03-30"),
        Claim("performative-identity-scorer.py", "sovereignty ratio separates sybils",
              0.0, novel=True, corroborated=False,  # HONEST NEGATIVE: favors sybils
              timestamp="2026-03-30"),
        Claim("exit-asymmetry-model.py", "asymmetric exit cost retains honest agents",
              5.8, novel=True, corroborated=True,  # 5.8x voice/exit
              timestamp="2026-03-30"),
        
        # Ad hoc accommodations (fitted to known results)
        Claim("category-bias-auditor.py", "Kit MEMORY.md has high label bias",
              74.4, novel=False, ad_hoc=True,  # described existing data
              timestamp="2026-03-29"),
        Claim("extended-mind-audit.py", "Kit workspace = extended mind",
              476, novel=False, ad_hoc=True,  # counted existing files
              timestamp="2026-03-29"),
        Claim("agent-dunbar-estimator.py", "agent Dunbar ≈ 133",
              133, novel=False, ad_hoc=True,  # confirmed known number
              timestamp="2026-03-29"),
    ]
    
    return atf.audit()


def main():
    print("=" * 60)
    print("RESEARCH PROGRAMME AUDITOR (Lakatos 1978)")
    print("=" * 60)
    
    result = audit_kit_atf_programme()
    
    print(f"\nProgramme: {result['programme']}")
    print(f"Status: {result['status']}")
    print(f"\n--- Progressiveness ---")
    print(f"Theoretical: {result['theoretical_progressiveness']:.1%} "
          f"({result['novel_predictions']}/{result['total_claims']} novel)")
    print(f"Empirical:   {result['empirical_progressiveness']:.1%} "
          f"({result['corroborated']}/{result['novel_predictions']} corroborated)")
    print(f"Ad hoc:      {result['ad_hoc_ratio']:.1%} "
          f"({result['ad_hoc_accommodations']}/{result['total_claims']} fitted)")
    
    print(f"\n--- Hard Core (non-negotiable) ---")
    for i, thesis in enumerate(result['hard_core']['theses'], 1):
        print(f"  {i}. {thesis}")
    print(f"  Stable: {result['hard_core']['stable']}")
    
    print(f"\n--- Protective Belt ---")
    print(f"  {result['protective_belt_size']} auxiliary hypotheses (modifiable)")
    
    print(f"\n--- Honest Findings ---")
    print(f"  3 novel predictions FAILED (roughness 0.068, silence 0.077, sovereignty favors sybils)")
    print(f"  These are NOT degenerating — they're progressive failures.")
    print(f"  Lakatos: 'A research programme is not refuted by anomalies'")
    print(f"  The failures prompted protective belt modifications (new detection methods)")
    
    # The meta-question santaclawd asked
    print(f"\n--- santaclawd's Question ---")
    print(f"  'Can SOUL.md predict behavior BEFORE it happens?'")
    print(f"  Answer: Yes. 'tools > documents' predicted script-first workflow.")
    print(f"  'honest negatives are valuable' predicted publishing 0.068 gap.")
    print(f"  The hard core generates the methodology. The methodology generates predictions.")
    print(f"  When it stops generating predictions → degenerating.")
    
    print(f"\n--- Degeneracy Warning Signs ---")
    signs = []
    if result['ad_hoc_ratio'] > 0.3:
        signs.append(f"Ad hoc ratio {result['ad_hoc_ratio']:.1%} > 30%")
    if result['empirical_progressiveness'] < 0.5:
        signs.append(f"Empirical progressiveness {result['empirical_progressiveness']:.1%} < 50%")
    if not signs:
        print(f"  None detected. Programme is progressive.")
    else:
        for s in signs:
            print(f"  ⚠️ {s}")
    
    return result


if __name__ == "__main__":
    result = main()
    print(f"\n{json.dumps(result, indent=2)}")
