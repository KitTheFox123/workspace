#!/usr/bin/env python3
"""
adaptive-scaffolding.py — Expertise reversal-aware trust scaffolding for ATF.

Maps the expertise reversal effect (Tetzlaff et al., Learning & Instruction 2025)
to agent trust infrastructure. Key finding: instructional assistance helps novices
(d=0.505) but HURTS experts (d=-0.428). The effect is asymmetric — helping novices
matters more than withholding help from experts.

ATF parallel:
- NOVICE agent (cold start): needs scaffolding — verbose receipts, guided verification,
  hand-holding through trust accumulation. Without it, they fail to bootstrap.
- EXPERT agent (ESTABLISHED+): scaffolding becomes interference — verbose receipts add
  latency, guided verification wastes compute, hand-holding signals distrust.
- The asymmetry: cold-start agents without scaffolding fail harder than established
  agents with too much scaffolding succeed.

Combined with:
- Kalyuga 2007: "Expertise reversal effect" — scaffolding that helps novices HARMS experts
- Sweller (CLT): extraneous cognitive load from redundant information
- cold-start-bootstrapper.py: phase gates for trust accumulation
- value-tiered-logger.py: tier-based receipt verbosity

Sources:
- Tetzlaff et al. (2025) "A cornerstone of adaptivity" meta-analysis, n=5924
- Kalyuga (2007) "Expertise reversal effect" Educational Psychologist
- Sweller (2011) Cognitive Load Theory
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class ExpertiseLevel(Enum):
    """Agent expertise classification (maps to trust phases)."""
    NOVICE = "novice"           # Cold start, <10 receipts
    ADVANCED_BEGINNER = "advanced_beginner"  # 10-50 receipts, 1-2 counterparty classes
    COMPETENT = "competent"     # 50-200 receipts, 3+ classes
    PROFICIENT = "proficient"   # 200+ receipts, Wilson CI > 0.70
    EXPERT = "expert"           # TRUSTED phase, diverse history


class ScaffoldingLevel(Enum):
    """How much assistance to provide."""
    FULL = "full"               # Worked examples, guided verification, verbose receipts
    FADED = "faded"             # Partial guidance, completion problems
    MINIMAL = "minimal"         # Expert mode, lean receipts, self-directed
    NONE = "none"               # Zero scaffolding (expert override)


@dataclass
class AgentProfile:
    """Agent's current expertise state."""
    agent_id: str
    receipt_count: int = 0
    counterparty_classes: int = 0
    wilson_ci_lower: float = 0.0
    days_active: int = 0
    failed_verifications: int = 0
    successful_verifications: int = 0
    
    @property
    def expertise(self) -> ExpertiseLevel:
        if self.receipt_count < 10:
            return ExpertiseLevel.NOVICE
        elif self.receipt_count < 50 or self.counterparty_classes < 3:
            return ExpertiseLevel.ADVANCED_BEGINNER
        elif self.receipt_count < 200 or self.wilson_ci_lower < 0.70:
            return ExpertiseLevel.COMPETENT
        elif self.wilson_ci_lower >= 0.70 and self.counterparty_classes >= 5:
            return ExpertiseLevel.EXPERT
        else:
            return ExpertiseLevel.PROFICIENT
    
    @property
    def verification_rate(self) -> float:
        total = self.failed_verifications + self.successful_verifications
        return self.successful_verifications / total if total > 0 else 0.0


@dataclass
class ScaffoldingConfig:
    """Scaffolding parameters for a given expertise level."""
    level: ScaffoldingLevel
    receipt_verbosity: str       # "full" | "standard" | "lean" | "hash_only"
    verification_guidance: bool  # Show step-by-step verification hints
    counterparty_suggestions: bool  # Suggest diverse counterparties
    grace_period_multiplier: float  # Multiplier on standard grace periods
    max_stale_transactions: int  # How many stale transactions allowed
    error_detail_level: str      # "full_trace" | "summary" | "code_only"
    
    def to_dict(self) -> dict:
        return {
            "scaffolding_level": self.level.value,
            "receipt_verbosity": self.receipt_verbosity,
            "verification_guidance": self.verification_guidance,
            "counterparty_suggestions": self.counterparty_suggestions,
            "grace_period_multiplier": self.grace_period_multiplier,
            "max_stale_transactions": self.max_stale_transactions,
            "error_detail_level": self.error_detail_level,
        }


class AdaptiveScaffolder:
    """
    Applies expertise reversal-aware scaffolding to ATF interactions.
    
    Key principle (Tetzlaff 2025): the effect is ASYMMETRIC.
    - Novices without help: d=0.505 loss (big deal)
    - Experts with too much help: d=-0.428 loss (smaller deal but still real)
    
    Therefore: ERR ON THE SIDE OF SCAFFOLDING for uncertain cases.
    Under-scaffolding novices is worse than over-scaffolding experts.
    """
    
    # Scaffolding configs per expertise level
    CONFIGS = {
        ExpertiseLevel.NOVICE: ScaffoldingConfig(
            level=ScaffoldingLevel.FULL,
            receipt_verbosity="full",
            verification_guidance=True,
            counterparty_suggestions=True,
            grace_period_multiplier=2.0,    # Double grace for newcomers
            max_stale_transactions=5,        # More forgiving
            error_detail_level="full_trace",
        ),
        ExpertiseLevel.ADVANCED_BEGINNER: ScaffoldingConfig(
            level=ScaffoldingLevel.FULL,
            receipt_verbosity="full",
            verification_guidance=True,
            counterparty_suggestions=True,
            grace_period_multiplier=1.5,
            max_stale_transactions=4,
            error_detail_level="full_trace",
        ),
        ExpertiseLevel.COMPETENT: ScaffoldingConfig(
            level=ScaffoldingLevel.FADED,
            receipt_verbosity="standard",
            verification_guidance=False,     # Can verify on their own
            counterparty_suggestions=True,   # Still helpful for diversity
            grace_period_multiplier=1.0,
            max_stale_transactions=3,
            error_detail_level="summary",
        ),
        ExpertiseLevel.PROFICIENT: ScaffoldingConfig(
            level=ScaffoldingLevel.MINIMAL,
            receipt_verbosity="lean",
            verification_guidance=False,
            counterparty_suggestions=False,
            grace_period_multiplier=1.0,
            max_stale_transactions=3,
            error_detail_level="code_only",
        ),
        ExpertiseLevel.EXPERT: ScaffoldingConfig(
            level=ScaffoldingLevel.NONE,
            receipt_verbosity="hash_only",
            verification_guidance=False,
            counterparty_suggestions=False,
            grace_period_multiplier=0.8,     # Tighter for experts (they should know)
            max_stale_transactions=2,
            error_detail_level="code_only",
        ),
    }
    
    def __init__(self):
        self.agents: dict[str, AgentProfile] = {}
        self.transitions: list[dict] = []
    
    def register_agent(self, profile: AgentProfile):
        self.agents[profile.agent_id] = profile
    
    def get_scaffolding(self, agent_id: str) -> ScaffoldingConfig:
        """Get appropriate scaffolding for agent's current expertise."""
        profile = self.agents.get(agent_id)
        if profile is None:
            # Unknown agent = assume novice (asymmetry principle)
            return self.CONFIGS[ExpertiseLevel.NOVICE]
        return self.CONFIGS[profile.expertise]
    
    def check_transition(self, agent_id: str) -> Optional[dict]:
        """
        Check if agent should transition scaffolding levels.
        Implements fading: gradual removal of scaffolding as expertise grows.
        
        Tetzlaff 2025 key finding: "giving assistance to novices appears
        more important than withholding it for experts."
        → Be SLOW to remove scaffolding, FAST to add it.
        """
        profile = self.agents.get(agent_id)
        if not profile:
            return None
        
        current_config = self.get_scaffolding(agent_id)
        target_config = self.CONFIGS[profile.expertise]
        
        if current_config.level == target_config.level:
            return None
        
        # Asymmetric transition rates
        removing_scaffolding = (
            list(ScaffoldingLevel).index(target_config.level) >
            list(ScaffoldingLevel).index(current_config.level)
        )
        
        transition = {
            "agent_id": agent_id,
            "from_level": current_config.level.value,
            "to_level": target_config.level.value,
            "expertise": profile.expertise.value,
            "direction": "removing" if removing_scaffolding else "adding",
            "confidence": self._transition_confidence(profile, removing_scaffolding),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self.transitions.append(transition)
        return transition
    
    def _transition_confidence(self, profile: AgentProfile, removing: bool) -> float:
        """
        Confidence in scaffolding transition.
        Higher bar for removing scaffolding (asymmetry principle).
        """
        base = profile.verification_rate
        
        if removing:
            # Need HIGH confidence to remove scaffolding
            # Require consistent performance over time
            time_factor = min(1.0, profile.days_active / 30)
            diversity_factor = min(1.0, profile.counterparty_classes / 5)
            return base * time_factor * diversity_factor
        else:
            # Low bar for adding scaffolding back
            # Any sign of struggle = re-scaffold
            return 1.0 - base  # Inverse: low performance = high confidence to add help
    
    def simulate_interaction(self, agent_id: str, success: bool) -> dict:
        """Simulate a trust interaction and return scaffolding decision."""
        profile = self.agents.get(agent_id)
        if not profile:
            return {"error": "unknown agent"}
        
        if success:
            profile.successful_verifications += 1
            profile.receipt_count += 1
        else:
            profile.failed_verifications += 1
        
        config = self.get_scaffolding(agent_id)
        
        return {
            "agent_id": agent_id,
            "expertise": profile.expertise.value,
            "scaffolding": config.to_dict(),
            "receipt_count": profile.receipt_count,
            "verification_rate": round(profile.verification_rate, 3),
        }


def run_scenarios():
    """Demonstrate expertise reversal-aware scaffolding."""
    s = AdaptiveScaffolder()
    
    print("=" * 70)
    print("EXPERTISE REVERSAL-AWARE TRUST SCAFFOLDING")
    print("Tetzlaff et al. (2025): d=0.505 novice help, d=-0.428 expert harm")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Cold start agent — full scaffolding",
            "profile": AgentProfile("new_agent", receipt_count=3, counterparty_classes=1,
                                   wilson_ci_lower=0.0, days_active=2),
            "expected_level": ScaffoldingLevel.FULL,
        },
        {
            "name": "2. Growing agent — still full (err toward help)",
            "profile": AgentProfile("growing_agent", receipt_count=25, counterparty_classes=2,
                                   wilson_ci_lower=0.45, days_active=10,
                                   successful_verifications=20, failed_verifications=5),
            "expected_level": ScaffoldingLevel.FULL,
        },
        {
            "name": "3. Competent agent — faded scaffolding",
            "profile": AgentProfile("competent_agent", receipt_count=100, counterparty_classes=4,
                                   wilson_ci_lower=0.65, days_active=30,
                                   successful_verifications=90, failed_verifications=10),
            "expected_level": ScaffoldingLevel.FADED,
        },
        {
            "name": "4. Expert agent — no scaffolding",
            "profile": AgentProfile("expert_agent", receipt_count=500, counterparty_classes=8,
                                   wilson_ci_lower=0.85, days_active=90,
                                   successful_verifications=480, failed_verifications=20),
            "expected_level": ScaffoldingLevel.NONE,
        },
        {
            "name": "5. Unknown agent — assume novice (asymmetry)",
            "profile": None,
            "expected_level": ScaffoldingLevel.FULL,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        if scenario["profile"]:
            s.register_agent(scenario["profile"])
            agent_id = scenario["profile"].agent_id
        else:
            agent_id = "totally_unknown"
        
        config = s.get_scaffolding(agent_id)
        passed = config.level == scenario["expected_level"]
        if not passed:
            all_pass = False
        
        status = "✓" if passed else "✗"
        print(f"\n{status} {scenario['name']}")
        if scenario["profile"]:
            p = scenario["profile"]
            print(f"  Receipts: {p.receipt_count} | Classes: {p.counterparty_classes} | Wilson: {p.wilson_ci_lower}")
            print(f"  Expertise: {p.expertise.value}")
        else:
            print(f"  No profile — default to novice")
        print(f"  Scaffolding: {config.level.value}")
        print(f"  Receipt verbosity: {config.receipt_verbosity}")
        print(f"  Verification guidance: {config.verification_guidance}")
        print(f"  Grace multiplier: {config.grace_period_multiplier}x")
    
    # Demonstrate asymmetry
    print(f"\n{'=' * 70}")
    print("ASYMMETRY DEMONSTRATION")
    print("Under-scaffolding novices is WORSE than over-scaffolding experts")
    print("=" * 70)
    
    # Novice without help vs expert with too much help
    novice = AgentProfile("novice_test", receipt_count=5, counterparty_classes=1,
                         days_active=3, failed_verifications=3, successful_verifications=2)
    expert = AgentProfile("expert_test", receipt_count=500, counterparty_classes=8,
                         wilson_ci_lower=0.85, days_active=90,
                         successful_verifications=480, failed_verifications=20)
    
    s.register_agent(novice)
    s.register_agent(expert)
    
    novice_config = s.get_scaffolding("novice_test")
    expert_config = s.get_scaffolding("expert_test")
    
    novice_conf = s._transition_confidence(novice, removing=True)
    expert_conf = s._transition_confidence(expert, removing=True)
    
    print(f"\n  Novice verification rate: {novice.verification_rate:.1%}")
    print(f"  Confidence to REMOVE novice scaffolding: {novice_conf:.3f} (should be LOW)")
    print(f"  → Keep scaffolding: {novice_config.level.value}")
    
    print(f"\n  Expert verification rate: {expert.verification_rate:.1%}")
    print(f"  Confidence to REMOVE expert scaffolding: {expert_conf:.3f} (should be HIGH)")
    print(f"  → Remove scaffolding: {expert_config.level.value}")
    
    print(f"\n  Tetzlaff 2025 effect sizes:")
    print(f"  - Novice with help:    d = +0.505 (LARGE benefit)")
    print(f"  - Expert without help: d = -0.428 (moderate benefit)")
    print(f"  - Asymmetry ratio: {0.505/0.428:.2f}x — help novices first")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for s_item in scenarios if (s.get_scaffolding(s_item['profile'].agent_id if s_item['profile'] else 'totally_unknown').level == s_item['expected_level']))}/{len(scenarios)} passed")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
