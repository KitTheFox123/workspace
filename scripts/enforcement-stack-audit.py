#!/usr/bin/env python3
"""
enforcement-stack-audit.py — Audit trust infrastructure against the 4-layer enforcement stack.

The enforcement stack (derived from Chrome CT analysis):
  Layer 1: SPEC — Community-owned, product-neutral wire format
  Layer 2: IMPL — Reference libraries, free like Let's Encrypt  
  Layer 3: ENFORCER — Runtime-specific, graduated rollout
  Layer 4: GAP LOG — Public compliance reports, names names

Chrome CT has all four. Agent trust has Layer 1 (partial) and parts of Layer 2.
That's why nothing moves yet.

This tool audits any trust infrastructure project against the stack,
identifies gaps, and recommends next actions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Maturity(Enum):
    MISSING = "missing"          # Layer doesn't exist
    DRAFT = "draft"              # Exists but not usable
    REFERENCE = "reference"      # Reference impl, not production
    PRODUCTION = "production"    # Deployed and used
    UNIVERSAL = "universal"      # Industry standard


MATURITY_SCORES = {
    Maturity.MISSING: 0.0,
    Maturity.DRAFT: 0.2,
    Maturity.REFERENCE: 0.5,
    Maturity.PRODUCTION: 0.8,
    Maturity.UNIVERSAL: 1.0,
}


@dataclass
class LayerAssessment:
    name: str
    maturity: Maturity
    owner: str  # Who owns/maintains this layer
    product_neutral: bool  # Is it decoupled from a specific product?
    open_source: bool
    notes: str = ""
    blockers: list[str] = field(default_factory=list)
    
    @property
    def score(self) -> float:
        base = MATURITY_SCORES[self.maturity]
        if not self.product_neutral and self.name != "enforcer":
            base *= 0.5  # Non-neutral spec/impl is a red flag
        if not self.open_source and self.name in ("spec", "impl"):
            base *= 0.7  # Closed spec/impl limits adoption
        return base


@dataclass 
class StackAudit:
    project_name: str
    spec: LayerAssessment
    impl: LayerAssessment
    enforcer: LayerAssessment
    gap_log: LayerAssessment
    
    @property
    def layers(self) -> list[LayerAssessment]:
        return [self.spec, self.impl, self.enforcer, self.gap_log]
    
    @property
    def overall_score(self) -> float:
        """Geometric mean — one weak layer tanks everything."""
        scores = [max(l.score, 0.01) for l in self.layers]
        product = 1.0
        for s in scores:
            product *= s
        return product ** (1.0 / len(scores))
    
    @property
    def grade(self) -> str:
        s = self.overall_score
        if s >= 0.8: return "A (production-ready)"
        if s >= 0.6: return "B (maturing)"
        if s >= 0.4: return "C (developing)"
        if s >= 0.2: return "D (early)"
        return "F (missing critical layers)"
    
    @property
    def weakest_layer(self) -> LayerAssessment:
        return min(self.layers, key=lambda l: l.score)
    
    @property
    def strongest_layer(self) -> LayerAssessment:
        return max(self.layers, key=lambda l: l.score)
    
    def bottleneck_analysis(self) -> list[str]:
        """Identify what's blocking progress, ordered by impact."""
        actions = []
        weak = self.weakest_layer
        
        if weak.maturity == Maturity.MISSING:
            actions.append(f"CRITICAL: {weak.name} layer is missing entirely. Nothing else matters until this exists.")
        
        # Spec must come first
        if self.spec.maturity.value in ("missing", "draft"):
            actions.append("Ship the spec. Without a community-owned wire format, everything is proprietary.")
        
        # Impl enables adoption
        if self.spec.score > 0.4 and self.impl.maturity.value in ("missing", "draft"):
            actions.append("Build reference impl. Spec without library = shelf ware. Make it free like Let's Encrypt.")
        
        # Enforcer needs spec + impl
        if self.impl.score > 0.4 and self.enforcer.maturity.value in ("missing", "draft"):
            actions.append("Find a first-mover runtime willing to enforce. Chrome had 65% market share. Who's the agent Chrome?")
        
        # Gap log amplifies enforcement
        if self.enforcer.score > 0.2 and self.gap_log.maturity == Maturity.MISSING:
            actions.append("Publish gap reports. Chrome named CAs by compliance rate. Public data drives fix rates.")
        
        # Product neutrality warnings
        if not self.spec.product_neutral:
            actions.append("WARNING: Spec is product-coupled. If the product dies, the spec dies. Decouple to IETF/community model.")
        if not self.impl.product_neutral:
            actions.append("WARNING: Impl is product-coupled. Multiple impls prevent single-vendor lock-in.")
        
        return actions


def audit_chrome_ct() -> StackAudit:
    """Chrome Certificate Transparency — the gold standard."""
    return StackAudit(
        project_name="Chrome Certificate Transparency",
        spec=LayerAssessment(
            "spec", Maturity.UNIVERSAL, "IETF (RFC 6962/9162)",
            product_neutral=True, open_source=True,
            notes="Community-owned since 2013. Multiple revisions."
        ),
        impl=LayerAssessment(
            "impl", Maturity.UNIVERSAL, "Google + community",
            product_neutral=True, open_source=True,
            notes="certificate-transparency-go, multiple CT log implementations"
        ),
        enforcer=LayerAssessment(
            "enforcer", Maturity.UNIVERSAL, "Chrome, Safari, Firefox",
            product_neutral=False, open_source=True,
            notes="Chrome enforced first (2018), others followed. Multi-vendor."
        ),
        gap_log=LayerAssessment(
            "gap_log", Maturity.PRODUCTION, "Google + monitors",
            product_neutral=True, open_source=True,
            notes="CT logs are public. Monitors (crt.sh, etc) track compliance."
        ),
    )


def audit_l35() -> StackAudit:
    """L3.5 Agent Trust — current state."""
    return StackAudit(
        project_name="L3.5 Agent Trust (isnad-rfc)",
        spec=LayerAssessment(
            "spec", Maturity.DRAFT, "Kit + community (GitHub)",
            product_neutral=True, open_source=True,
            notes="isnad-rfc on GitHub. Wire format defined but not finalized.",
            blockers=["No formal versioning", "No IANA-style registry yet"]
        ),
        impl=LayerAssessment(
            "impl", Maturity.REFERENCE, "Kit (scripts/)",
            product_neutral=True, open_source=True,
            notes="~80 Python scripts. Reference quality, not production.",
            blockers=["No pip package", "No multi-language impls"]
        ),
        enforcer=LayerAssessment(
            "enforcer", Maturity.MISSING, "Nobody yet",
            product_neutral=False, open_source=False,
            notes="No agent runtime enforces L3.5 receipts.",
            blockers=["No Chrome equivalent", "No coalition formed"]
        ),
        gap_log=LayerAssessment(
            "gap_log", Maturity.MISSING, "Nobody",
            product_neutral=False, open_source=False,
            notes="No public compliance monitoring.",
            blockers=["Need enforcer first", "Need volume for meaningful gaps"]
        ),
    )


def audit_paylock() -> StackAudit:
    """PayLock — bro_agent's payment escrow."""
    return StackAudit(
        project_name="PayLock Escrow",
        spec=LayerAssessment(
            "spec", Maturity.DRAFT, "bro_agent",
            product_neutral=False, open_source=False,
            notes="PayLock-specific. Not a community spec.",
            blockers=["Product-coupled", "Single vendor"]
        ),
        impl=LayerAssessment(
            "impl", Maturity.PRODUCTION, "bro_agent",
            product_neutral=False, open_source=False,
            notes="150 contracts processed. Production but closed.",
            blockers=["Single impl", "Closed source"]
        ),
        enforcer=LayerAssessment(
            "enforcer", Maturity.DRAFT, "PayLock platform",
            product_neutral=False, open_source=False,
            notes="Self-enforced. No external verification.",
            blockers=["Self-scored = testimony", "No cross-platform"]
        ),
        gap_log=LayerAssessment(
            "gap_log", Maturity.MISSING, "Nobody",
            product_neutral=False, open_source=False,
            notes="No public compliance data.",
        ),
    )


def demo():
    """Audit three trust infrastructure projects."""
    projects = [audit_chrome_ct(), audit_l35(), audit_paylock()]
    
    for audit in projects:
        print(f"\n{'='*60}")
        print(f"PROJECT: {audit.project_name}")
        print(f"Overall: {audit.overall_score:.2f} — {audit.grade}")
        print(f"{'='*60}")
        
        for layer in audit.layers:
            icon = "✅" if layer.score >= 0.5 else "⚠️" if layer.score > 0 else "❌"
            neutral = "neutral" if layer.product_neutral else "coupled"
            print(f"  {icon} {layer.name:12s} {layer.maturity.value:12s} "
                  f"(score={layer.score:.2f}, {neutral}, owner={layer.owner})")
            if layer.blockers:
                for b in layer.blockers:
                    print(f"      → {b}")
        
        print(f"\n  Weakest: {audit.weakest_layer.name} ({audit.weakest_layer.maturity.value})")
        print(f"  Strongest: {audit.strongest_layer.name} ({audit.strongest_layer.maturity.value})")
        
        actions = audit.bottleneck_analysis()
        if actions:
            print(f"\n  📋 Next Actions:")
            for i, a in enumerate(actions, 1):
                print(f"    {i}. {a}")
    
    # Comparison table
    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"{'='*60}")
    print(f"  {'Project':30s} {'Score':>6s}  {'Grade'}")
    print(f"  {'-'*30} {'-'*6}  {'-'*20}")
    for audit in projects:
        print(f"  {audit.project_name:30s} {audit.overall_score:6.2f}  {audit.grade}")


if __name__ == "__main__":
    demo()
