#!/usr/bin/env python3
"""
three-party-consent.py — Model for agent commerce consent (Perplexity v Amazon).

Judge Chesney (Mar 10, 2026): user consent ≠ platform consent.
"Comet accessed Amazon accounts with the Amazon user's permission,
but without authorization by Amazon."

Three parties:
  1. User (wants action performed)
  2. Agent (performs the action)
  3. Platform (controls the resource)

All three must consent. 2/3 is not enough.

Perplexity's defense: "AI agents don't have eyeballs to see the pervasive
advertising Amazon bombards its users with." → Ad model breaks when agents
skip the attention economy.

Solution: .well-known/agent.json for honest agent identification.
L3.5 receipts: agent self-identifies, platform verifies, user authorizes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ConsentStatus(Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"  # Not yet asked
    REVOKED = "revoked"  # Was granted, now revoked


class IdentificationMethod(Enum):
    HONEST = "honest"          # .well-known/agent.json, User-Agent header
    DISGUISED = "disguised"    # Masquerading as human browser (Comet/Chrome)
    NONE = "none"              # No identification at all


class AccessOutcome(Enum):
    ALLOWED = "allowed"
    BLOCKED_NO_PLATFORM_CONSENT = "blocked_no_platform_consent"
    BLOCKED_NO_USER_CONSENT = "blocked_no_user_consent"
    BLOCKED_DISGUISED = "blocked_disguised_agent"
    ALLOWED_DEGRADED = "allowed_degraded"  # Platform allows but limits features


@dataclass
class ConsentTriple:
    """Three-party consent state."""
    user: ConsentStatus = ConsentStatus.UNKNOWN
    agent: ConsentStatus = ConsentStatus.GRANTED  # Agent always consents to act
    platform: ConsentStatus = ConsentStatus.UNKNOWN
    
    @property
    def all_consented(self) -> bool:
        return all(c == ConsentStatus.GRANTED for c in [self.user, self.agent, self.platform])
    
    @property
    def missing(self) -> list[str]:
        missing = []
        if self.user != ConsentStatus.GRANTED:
            missing.append(f"user ({self.user.value})")
        if self.platform != ConsentStatus.GRANTED:
            missing.append(f"platform ({self.platform.value})")
        return missing


@dataclass
class AgentIdentity:
    """How the agent identifies itself."""
    agent_id: str
    agent_name: str
    method: IdentificationMethod
    well_known_url: Optional[str] = None  # .well-known/agent.json
    user_agent: Optional[str] = None
    capabilities_declared: list[str] = field(default_factory=list)


@dataclass
class PlatformPolicy:
    """Platform's agent access policy."""
    platform_name: str
    allows_agents: bool
    requires_identification: bool = True
    requires_well_known: bool = False
    allowed_capabilities: list[str] = field(default_factory=list)
    blocked_capabilities: list[str] = field(default_factory=list)
    ad_dependent: bool = False  # Business model depends on attention
    agent_api_available: bool = False  # Has dedicated agent API
    
    def evaluate_agent(self, agent: AgentIdentity) -> tuple[ConsentStatus, str]:
        """Evaluate whether platform consents to this agent."""
        if not self.allows_agents:
            return ConsentStatus.DENIED, "Platform does not allow agents"
        
        if self.requires_identification and agent.method == IdentificationMethod.DISGUISED:
            return ConsentStatus.DENIED, "Agent disguised as human browser (Perplexity/Comet pattern)"
        
        if self.requires_identification and agent.method == IdentificationMethod.NONE:
            return ConsentStatus.DENIED, "Agent did not identify itself"
        
        if self.requires_well_known and not agent.well_known_url:
            return ConsentStatus.DENIED, "No .well-known/agent.json provided"
        
        # Check capabilities
        for cap in agent.capabilities_declared:
            if cap in self.blocked_capabilities:
                return ConsentStatus.DENIED, f"Capability '{cap}' blocked by platform"
        
        return ConsentStatus.GRANTED, "Platform consents"


class ThreePartyConsentChecker:
    """Evaluate three-party consent for agent commerce transactions."""
    
    def check(
        self,
        agent: AgentIdentity,
        platform: PlatformPolicy,
        user_consented: bool,
    ) -> dict:
        """Check all three parties and determine access outcome."""
        consent = ConsentTriple()
        reasons = []
        
        # User consent
        consent.user = ConsentStatus.GRANTED if user_consented else ConsentStatus.DENIED
        if not user_consented:
            reasons.append("User did not authorize agent")
        
        # Platform consent
        platform_status, platform_reason = platform.evaluate_agent(agent)
        consent.platform = platform_status
        if platform_status != ConsentStatus.GRANTED:
            reasons.append(platform_reason)
        
        # Determine outcome
        if consent.all_consented:
            outcome = AccessOutcome.ALLOWED
        elif agent.method == IdentificationMethod.DISGUISED:
            outcome = AccessOutcome.BLOCKED_DISGUISED
        elif consent.user != ConsentStatus.GRANTED:
            outcome = AccessOutcome.BLOCKED_NO_USER_CONSENT
        else:
            outcome = AccessOutcome.BLOCKED_NO_PLATFORM_CONSENT
        
        # Legal risk assessment
        legal_risk = self._assess_legal_risk(agent, platform, consent)
        
        return {
            "outcome": outcome.value,
            "consent": {
                "user": consent.user.value,
                "agent": consent.agent.value,
                "platform": consent.platform.value,
                "all_consented": consent.all_consented,
                "missing": consent.missing,
            },
            "reasons": reasons,
            "legal_risk": legal_risk,
            "recommendation": self._recommend(outcome, agent, platform),
        }
    
    def _assess_legal_risk(
        self,
        agent: AgentIdentity,
        platform: PlatformPolicy,
        consent: ConsentTriple,
    ) -> dict:
        """Assess legal risk based on Chesney ruling precedent."""
        risk_score = 0.0
        factors = []
        
        # Disguised agent = highest risk (Comet precedent)
        if agent.method == IdentificationMethod.DISGUISED:
            risk_score += 0.5
            factors.append("CFAA risk: disguised agent (Chesney: 'no less unlawful')")
        
        # No platform consent = CFAA exposure
        if consent.platform != ConsentStatus.GRANTED:
            risk_score += 0.3
            factors.append("CFAA: accessing without platform authorization")
        
        # Circumventing technical barriers = aggravating factor
        if agent.method == IdentificationMethod.DISGUISED and not platform.allows_agents:
            risk_score += 0.2
            factors.append("Circumventing access controls (Perplexity pushed update within 24h)")
        
        # Ad-dependent platform = commercial harm argument
        if platform.ad_dependent and consent.platform != ConsentStatus.GRANTED:
            risk_score += 0.1
            factors.append("Commercial harm: agents bypass ad revenue model")
        
        risk_level = (
            "CRITICAL" if risk_score >= 0.7 else
            "HIGH" if risk_score >= 0.5 else
            "MEDIUM" if risk_score >= 0.3 else
            "LOW"
        )
        
        return {
            "score": round(risk_score, 2),
            "level": risk_level,
            "factors": factors,
            "precedent": "Amazon v Perplexity (N.D. Cal. 2026, Chesney J.)",
        }
    
    def _recommend(
        self,
        outcome: AccessOutcome,
        agent: AgentIdentity,
        platform: PlatformPolicy,
    ) -> str:
        if outcome == AccessOutcome.ALLOWED:
            return "Proceed — all parties consented"
        elif outcome == AccessOutcome.BLOCKED_DISGUISED:
            return "STOP. Identify honestly via .well-known/agent.json. Disguise = CFAA liability."
        elif platform.agent_api_available:
            return f"Use {platform.platform_name}'s agent API instead of scraping"
        elif outcome == AccessOutcome.BLOCKED_NO_PLATFORM_CONSENT:
            return "Request platform consent or find alternative. Do not circumvent."
        else:
            return "Obtain user authorization before acting"


def demo():
    """Demonstrate three-party consent with real-world scenarios."""
    checker = ThreePartyConsentChecker()
    
    # Scenario 1: Perplexity Comet on Amazon (actual case)
    comet = AgentIdentity(
        agent_id="perplexity:comet",
        agent_name="Comet Browser Agent",
        method=IdentificationMethod.DISGUISED,
        user_agent="Mozilla/5.0 (like Chrome)",  # Disguised
        capabilities_declared=["browse", "purchase", "login"],
    )
    
    amazon = PlatformPolicy(
        platform_name="Amazon",
        allows_agents=False,
        requires_identification=True,
        ad_dependent=True,
        agent_api_available=True,  # Amazon has Product Advertising API
    )
    
    # Scenario 2: Honest agent with .well-known
    honest_agent = AgentIdentity(
        agent_id="agent:kit_fox",
        agent_name="Kit",
        method=IdentificationMethod.HONEST,
        well_known_url="https://kit.example/.well-known/agent.json",
        user_agent="Kit/1.0 (AgentMail; +https://kit.example/.well-known/agent.json)",
        capabilities_declared=["search", "compare"],
    )
    
    # Scenario 3: Agent-friendly platform
    friendly_platform = PlatformPolicy(
        platform_name="AgentStore",
        allows_agents=True,
        requires_identification=True,
        requires_well_known=True,
        allowed_capabilities=["search", "compare", "purchase"],
        ad_dependent=False,
        agent_api_available=True,
    )
    
    scenarios = [
        ("Perplexity Comet on Amazon (actual ruling)", comet, amazon, True),
        ("Honest agent on Amazon (with user consent)", honest_agent, amazon, True),
        ("Honest agent on Amazon (no user consent)", honest_agent, amazon, False),
        ("Honest agent on agent-friendly platform", honest_agent, friendly_platform, True),
        ("Disguised agent on agent-friendly platform", comet, friendly_platform, True),
    ]
    
    for name, agent, platform, user_ok in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario: {name}")
        print(f"{'='*60}")
        
        result = checker.check(agent, platform, user_ok)
        
        print(f"  Outcome: {result['outcome']}")
        print(f"  Consent: user={result['consent']['user']}, "
              f"platform={result['consent']['platform']}")
        if result['consent']['missing']:
            print(f"  Missing: {result['consent']['missing']}")
        if result['reasons']:
            print(f"  Reasons: {result['reasons']}")
        
        risk = result['legal_risk']
        print(f"  Legal risk: {risk['level']} ({risk['score']})")
        for f in risk['factors']:
            print(f"    ⚠️  {f}")
        print(f"  Precedent: {risk['precedent']}")
        print(f"  → {result['recommendation']}")


if __name__ == "__main__":
    demo()
