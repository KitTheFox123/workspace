#!/usr/bin/env python3
"""
spec-enforcer-separation.py — Formalizes the WHAT/WHO pattern from web standards.

Per Clawk thread (santaclawd, bro_agent, Kit):
  The pattern that works: spec body owns the WHAT, product enforces the WHO.
  - IETF/TLS + Chrome/CT enforcement
  - W3C/HTML + browsers/rendering  
  - IETF/DKIM + Gmail/spam filtering
  - L3.5 wire format + agent runtimes/receipt verification

IE6 lesson: enforcer owning the spec = spec dies with the product.
Chrome CT lesson: IETF-owned spec survives any single enforcer losing market share.

This tool audits a protocol deployment for healthy separation between
spec ownership and enforcement, detecting anti-patterns.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CouplingRisk(Enum):
    """Risk levels for spec-enforcer coupling."""
    HEALTHY = "healthy"       # Spec and enforcer fully separated
    CONCERNING = "concerning"  # Some coupling detected
    DANGEROUS = "dangerous"    # Enforcer controls spec evolution
    FATAL = "fatal"           # Spec and enforcer are same entity (IE6 pattern)


class AntiPattern(Enum):
    """Known spec-enforcer coupling anti-patterns."""
    SINGLE_ENFORCER = "single_enforcer"           # Only one product enforces
    SPEC_OWNER_IS_ENFORCER = "spec_owner_is_enforcer"  # Same org owns both
    PROPRIETARY_EXTENSIONS = "proprietary_extensions"   # Enforcer-specific additions
    NO_REFERENCE_IMPL = "no_reference_impl"        # No independent implementation
    ENFORCEMENT_LEAKS_INTO_SPEC = "enforcement_leaks"  # Policy in wire format
    NO_GRADUATION_PATH = "no_graduation_path"      # Binary enforce/don't
    VENDOR_LOCK_IN = "vendor_lock_in"              # Switching enforcers breaks compat


@dataclass
class SpecBody:
    """Standards organization owning the spec."""
    name: str
    governance: str  # "multi-stakeholder", "single-vendor", "community"
    spec_id: str     # e.g., "RFC 6962", "L3.5 wire format"
    open_process: bool = True
    multiple_implementations: int = 0


@dataclass 
class Enforcer:
    """Product or runtime enforcing the spec."""
    name: str
    market_share: float  # 0.0-1.0
    owns_spec: bool = False
    proprietary_extensions: list[str] = field(default_factory=list)
    has_graduation: bool = False
    fallback_on_failure: str = "reject"  # "reject", "warn", "accept"


@dataclass
class Deployment:
    """A spec + enforcer(s) deployment."""
    spec: SpecBody
    enforcers: list[Enforcer]
    reference_impl_count: int = 0
    years_deployed: float = 0.0


@dataclass
class AuditResult:
    """Result of separation audit."""
    risk: CouplingRisk
    anti_patterns: list[AntiPattern]
    warnings: list[str]
    recommendations: list[str]
    score: float  # 0.0 (fatal) to 1.0 (healthy)
    historical_parallel: Optional[str] = None


class SpecEnforcerAuditor:
    """Audit spec-enforcer separation health."""
    
    def audit(self, deployment: Deployment) -> AuditResult:
        anti_patterns = []
        warnings = []
        recommendations = []
        score = 1.0
        
        # Check: single enforcer
        if len(deployment.enforcers) == 1:
            anti_patterns.append(AntiPattern.SINGLE_ENFORCER)
            score -= 0.15
            warnings.append(
                f"Only {deployment.enforcers[0].name} enforces. "
                f"If it dies, enforcement dies."
            )
            recommendations.append("Recruit 2+ additional enforcers before STRICT phase")
        
        # Check: spec owner is enforcer
        for e in deployment.enforcers:
            if e.owns_spec:
                anti_patterns.append(AntiPattern.SPEC_OWNER_IS_ENFORCER)
                score -= 0.25
                warnings.append(
                    f"{e.name} both owns spec and enforces = IE6 pattern"
                )
                recommendations.append(
                    "Transfer spec to multi-stakeholder body (IETF, W3C equivalent)"
                )
        
        # Check: proprietary extensions
        for e in deployment.enforcers:
            if e.proprietary_extensions:
                anti_patterns.append(AntiPattern.PROPRIETARY_EXTENSIONS)
                score -= 0.10 * len(e.proprietary_extensions)
                warnings.append(
                    f"{e.name} has {len(e.proprietary_extensions)} proprietary extensions"
                )
        
        # Check: reference implementations
        if deployment.reference_impl_count == 0:
            anti_patterns.append(AntiPattern.NO_REFERENCE_IMPL)
            score -= 0.20
            recommendations.append("Ship reference implementation alongside spec")
        
        # Check: graduation path
        enforcers_with_graduation = sum(1 for e in deployment.enforcers if e.has_graduation)
        if enforcers_with_graduation == 0:
            anti_patterns.append(AntiPattern.NO_GRADUATION_PATH)
            score -= 0.10
            recommendations.append(
                "Add graduated enforcement (REPORT→WARN→STRICT)"
            )
        
        # Check: governance
        if deployment.spec.governance == "single-vendor":
            score -= 0.30
            warnings.append("Single-vendor governance = spec dies with vendor")
        
        # Check: enforcement leaks into spec
        for e in deployment.enforcers:
            if e.fallback_on_failure == "reject" and not e.has_graduation:
                anti_patterns.append(AntiPattern.ENFORCEMENT_LEAKS_INTO_SPEC)
                score -= 0.05
                warnings.append(
                    f"{e.name} hard-rejects without graduation = policy in wire format"
                )
        
        # Determine risk level
        score = max(0.0, min(1.0, score))
        if score >= 0.80:
            risk = CouplingRisk.HEALTHY
        elif score >= 0.60:
            risk = CouplingRisk.CONCERNING
        elif score >= 0.30:
            risk = CouplingRisk.DANGEROUS
        else:
            risk = CouplingRisk.FATAL
        
        # Historical parallel
        parallel = self._find_parallel(anti_patterns, deployment)
        
        return AuditResult(
            risk=risk,
            anti_patterns=anti_patterns,
            warnings=warnings,
            recommendations=recommendations,
            score=score,
            historical_parallel=parallel,
        )
    
    def _find_parallel(self, patterns: list[AntiPattern], 
                       deployment: Deployment) -> Optional[str]:
        if AntiPattern.SPEC_OWNER_IS_ENFORCER in patterns:
            return (
                "IE6 (1999-2006): Microsoft owned HTML rendering AND dominated "
                "market share. Extensions became de facto standards. When IE lost "
                "share, proprietary features broke the web. Took a decade to recover."
            )
        if AntiPattern.SINGLE_ENFORCER in patterns and deployment.enforcers:
            e = deployment.enforcers[0]
            if e.market_share > 0.60:
                return (
                    f"Chrome CT (2015-2018): Chrome had {e.market_share:.0%}-equivalent "
                    f"leverage. Worked because spec was IETF-owned (RFC 6962). "
                    f"But single-enforcer risk remains — what if Chrome dropped CT?"
                )
        if len(deployment.enforcers) >= 3:
            return (
                "TLS ecosystem (mature): Multiple browsers enforce, IETF owns spec. "
                "No single enforcer can unilaterally change requirements. "
                "The healthiest pattern in web standards."
            )
        return None


def demo():
    """Audit real and hypothetical deployments."""
    auditor = SpecEnforcerAuditor()
    
    cases = [
        # 1. Chrome CT (real, 2018)
        Deployment(
            spec=SpecBody("IETF", "multi-stakeholder", "RFC 6962", True, 5),
            enforcers=[
                Enforcer("Chrome", 0.65, False, [], True, "reject"),
                Enforcer("Safari", 0.18, False, [], True, "reject"),
            ],
            reference_impl_count=3,
            years_deployed=5.0,
        ),
        # 2. IE6 HTML (anti-pattern)
        Deployment(
            spec=SpecBody("Microsoft", "single-vendor", "IE HTML", False, 1),
            enforcers=[
                Enforcer("IE6", 0.95, True, ["ActiveX", "VBScript", "CSS filters"], False, "accept"),
            ],
            reference_impl_count=0,
            years_deployed=7.0,
        ),
        # 3. L3.5 (current state)
        Deployment(
            spec=SpecBody("Community (Kit+santaclawd+bro_agent)", "community", "L3.5 wire format", True, 4),
            enforcers=[
                Enforcer("OpenClaw (proposed)", 0.05, False, [], True, "report"),
            ],
            reference_impl_count=12,  # All my scripts
            years_deployed=0.1,
        ),
        # 4. L3.5 (target state)
        Deployment(
            spec=SpecBody("Agent Standards Body", "multi-stakeholder", "L3.5 wire format v1.0", True, 10),
            enforcers=[
                Enforcer("OpenClaw", 0.15, False, [], True, "warn"),
                Enforcer("PayLock", 0.10, False, [], True, "report"),
                Enforcer("AgentRuntime3", 0.08, False, [], True, "report"),
            ],
            reference_impl_count=12,
            years_deployed=1.0,
        ),
    ]
    
    names = [
        "Chrome CT (2018) — HEALTHY reference",
        "IE6 HTML (2001) — FATAL anti-pattern", 
        "L3.5 current — early stage",
        "L3.5 target — multi-enforcer goal",
    ]
    
    for name, case in zip(names, cases):
        result = auditor.audit(case)
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        print(f"  Risk: {result.risk.value} (score: {result.score:.2f})")
        if result.anti_patterns:
            print(f"  Anti-patterns: {[p.value for p in result.anti_patterns]}")
        if result.warnings:
            for w in result.warnings:
                print(f"  ⚠️  {w}")
        if result.recommendations:
            for r in result.recommendations:
                print(f"  → {r}")
        if result.historical_parallel:
            print(f"  📚 {result.historical_parallel}")


if __name__ == "__main__":
    demo()
