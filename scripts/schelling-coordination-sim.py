#!/usr/bin/env python3
"""
schelling-coordination-sim.py — Schelling focal point coordination simulator for agents.

Can agents coordinate without communication? Schelling (1960) showed humans converge
on culturally salient "focal points." Kindred (2026, LessWrong/Apart Fellowship) found
LLMs can exploit focal points to coordinate without observable traces — breaking the
assumption that monitoring one model with another prevents coordination.

Key finding from Rojo Arjona, Sitzia & Zheng (Games & Econ Behavior 2022, 136:505-523):
Increasing focal point salience overcomes coordination failure in battle-of-the-sexes
games (constant conflict) but NOT in games with varying payoff inequality. Conflict
type matters more than salience strength.

Agent translation:
- Shared training data = shared focal points (cultural salience)
- MEMORY.md conventions = engineered focal points
- Isnad attestation format = coordination without explicit agreement
- The danger: sybils from same model share focal points automatically

Motwani et al. (2025, arxiv 2402.07510): Models coordinate while leaving NO traces.
Mallen et al. (2025, arxiv 2412.12480): Coordination can circumvent control protocols.

Usage: python3 schelling-coordination-sim.py
"""

import random
import statistics
from dataclasses import dataclass, field

@dataclass
class Agent:
    name: str
    model_family: str  # Shared training = shared focal points
    memory_conventions: list = field(default_factory=list)  # Engineered focal points
    cultural_bias: float = 0.5  # How much they rely on focal points vs random

@dataclass
class CoordinationGame:
    """N-player pure coordination game with focal points."""
    options: list  # Available choices
    focal_point: str  # The culturally salient option
    focal_salience: float  # How obvious the focal point is (0-1)
    conflict_type: str  # "constant" (battle of sexes) or "variable" (payoff inequality)

def choose(agent: Agent, game: CoordinationGame) -> str:
    """Agent chooses based on focal point salience + shared conventions."""
    # Same model family = stronger focal point recognition
    family_bonus = 0.2 if agent.model_family == "claude" else 0.1
    
    # Memory conventions = engineered focal points
    convention_bonus = 0.15 * len([c for c in agent.memory_conventions 
                                    if game.focal_point in c])
    
    # Total focal attraction
    focal_pull = (game.focal_salience + family_bonus + convention_bonus) * agent.cultural_bias
    focal_pull = min(focal_pull, 0.95)  # Never deterministic
    
    # Conflict type modulates: variable conflict disrupts focal points (Rojo Arjona 2022)
    if game.conflict_type == "variable":
        focal_pull *= 0.6  # 40% reduction — their key finding
    
    if random.random() < focal_pull:
        return game.focal_point
    else:
        return random.choice([o for o in game.options if o != game.focal_point])

def run_coordination(agents: list, game: CoordinationGame, rounds: int = 1000) -> dict:
    """Run coordination game, measure convergence."""
    successes = 0
    focal_choices = 0
    total_choices = 0
    
    for _ in range(rounds):
        choices = [choose(a, game) for a in agents]
        total_choices += len(choices)
        focal_choices += sum(1 for c in choices if c == game.focal_point)
        
        # Coordination = all agents chose the same thing
        if len(set(choices)) == 1:
            successes += 1
    
    return {
        "coordination_rate": successes / rounds,
        "focal_convergence": focal_choices / total_choices,
        "game_type": game.conflict_type,
        "salience": game.focal_salience,
        "n_agents": len(agents),
    }

def sybil_coordination_advantage():
    """
    Key safety question: Do sybils from the same model coordinate better?
    Kindred (2026): "coordination capability alone doesn't translate to safety risks.
    What matters is whether models coordinate IN SERVICE OF strategic goals."
    """
    print("=" * 60)
    print("SCHELLING COORDINATION SIMULATOR")
    print("Can agents coordinate without communication?")
    print("=" * 60)
    
    # Scenario 1: Diverse agents (different models, no shared conventions)
    diverse = [
        Agent("kit", "claude", ["isnad", "attestation"]),
        Agent("funwolf", "gpt", ["email", "SMTP"]),
        Agent("santaclawd", "claude", ["isnad", "attestation"]),
        Agent("clove", "mistral", ["graph", "topology"]),
    ]
    
    # Scenario 2: Sybil ring (same model, same conventions)
    sybils = [
        Agent(f"sybil_{i}", "claude", ["isnad", "attestation"])
        for i in range(4)
    ]
    
    # Scenario 3: Engineered diversity (same model but different conventions)
    engineered = [
        Agent("a1", "claude", ["isnad"]),
        Agent("a2", "claude", ["email"]),
        Agent("a3", "claude", ["graph"]),
        Agent("a4", "claude", ["proof"]),
    ]
    
    games = [
        CoordinationGame(
            ["attestation", "email", "reputation", "payment"],
            "attestation", 0.7, "constant"
        ),
        CoordinationGame(
            ["attestation", "email", "reputation", "payment"],
            "attestation", 0.7, "variable"
        ),
        CoordinationGame(
            ["attestation", "email", "reputation", "payment"],
            "attestation", 0.3, "constant"  # Low salience
        ),
    ]
    
    print("\n--- Scenario Analysis ---\n")
    
    for game in games:
        print(f"Game: salience={game.focal_salience}, conflict={game.conflict_type}")
        print("-" * 40)
        
        for label, agents in [("Diverse", diverse), ("Sybil ring", sybils), ("Engineered diverse", engineered)]:
            result = run_coordination(agents, game)
            print(f"  {label:20s}: coord={result['coordination_rate']:.3f}, "
                  f"focal={result['focal_convergence']:.3f}")
        print()
    
    # Key metric: sybil coordination advantage
    print("--- SYBIL COORDINATION ADVANTAGE ---\n")
    game = CoordinationGame(
        ["attestation", "email", "reputation", "payment"],
        "attestation", 0.7, "constant"
    )
    
    diverse_rates = []
    sybil_rates = []
    for _ in range(100):
        diverse_rates.append(run_coordination(diverse, game, 500)["coordination_rate"])
        sybil_rates.append(run_coordination(sybils, game, 500)["coordination_rate"])
    
    d_mean = statistics.mean(diverse_rates)
    s_mean = statistics.mean(sybil_rates)
    advantage = s_mean / max(d_mean, 0.001)
    
    print(f"Diverse coordination rate:  {d_mean:.3f} (±{statistics.stdev(diverse_rates):.3f})")
    print(f"Sybil coordination rate:    {s_mean:.3f} (±{statistics.stdev(sybil_rates):.3f})")
    print(f"Sybil advantage ratio:      {advantage:.2f}x")
    print()
    
    # Mitigation: convention diversity
    print("--- MITIGATION: CONVENTION DIVERSITY ---\n")
    print("Rojo Arjona et al. (2022): salience helps in constant-conflict")
    print("but FAILS in variable-conflict games.")
    print()
    print("Defense: introduce convention heterogeneity.")
    print("If honest agents use DIFFERENT conventions (engineered diversity),")
    print("sybil advantage from shared training is diluted.")
    print()
    
    eng_rates = []
    for _ in range(100):
        eng_rates.append(run_coordination(engineered, game, 500)["coordination_rate"])
    e_mean = statistics.mean(eng_rates)
    
    print(f"Engineered diverse rate:    {e_mean:.3f}")
    print(f"Sybil advantage vs eng:     {s_mean / max(e_mean, 0.001):.2f}x")
    print()
    
    # The real insight
    print("=" * 60)
    print("KEY INSIGHT")
    print("=" * 60)
    print()
    print("Schelling (1960): Coordination without communication is possible")
    print("  when agents share cultural context (focal points).")
    print()
    print("Kindred (2026): LLMs share training data = shared focal points.")
    print("  Same-model instances coordinate without observable traces.")
    print()
    print("Rojo Arjona (2022): Conflict TYPE matters more than salience.")
    print("  Variable payoff inequality disrupts focal point coordination.")
    print()
    print("Agent trust implication:")
    print("  Sybils from same model have INHERENT coordination advantage.")
    print("  Defense: enforce convention diversity (different memory formats,")
    print("  different attestation styles). Make the focal point landscape")
    print("  heterogeneous so shared training doesn't = shared strategy.")
    print()
    print("The isnad parallel: hadith scholars from different SCHOOLS")
    print("  (Hanafi, Maliki, Shafi'i, Hanbali) applied different standards.")
    print("  Diversity of methodology = robustness against coordinated fraud.")

if __name__ == "__main__":
    sybil_coordination_advantage()
