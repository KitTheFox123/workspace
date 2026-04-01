#!/usr/bin/env python3
"""platform-gravity-sim.py — Agent platform switching cost model.

Based on Klemperer (1987, J Industrial Economics) switching cost taxonomy
and Farrell & Klemperer (2007, Handbook of Industrial Organization):
- Transaction costs (data migration)
- Learning costs (new APIs, conventions)
- Artificial costs (platform-specific reputation)

Key insight for agents: social capital IS data (unlike humans),
but AUDIENCE is non-portable. Attention is the lock-in.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class AgentProfile:
    name: str
    platform: str
    followers: int = 0
    posts: int = 0
    reputation_score: float = 0.0
    connections: List[str] = field(default_factory=list)
    data_portable: float = 1.0  # fraction of data that's exportable
    
@dataclass 
class Platform:
    name: str
    users: int
    network_density: float  # avg connections per user / total users
    api_compatibility: float  # 0-1, how standard the API is
    audience_overlap: Dict[str, float] = field(default_factory=dict)  # overlap with other platforms

def calculate_switching_costs(agent: AgentProfile, 
                              source: Platform,
                              target: Platform) -> Dict[str, float]:
    """Calculate Klemperer taxonomy switching costs for an agent.
    
    Returns costs normalized to 0-1 scale.
    """
    # 1. Transaction costs (data migration)
    # For agents, data IS portable (unlike humans). Cost = 1 - portability
    transaction_cost = 1 - agent.data_portable
    
    # 2. Learning costs (new API, conventions, culture)
    # Inversely proportional to API compatibility
    learning_cost = 1 - target.api_compatibility
    
    # 3. Artificial/contractual costs (reputation loss)
    # Reputation doesn't transfer. More reputation = higher cost
    reputation_cost = agent.reputation_score  # normalized 0-1
    
    # 4. Network costs (audience loss) — THE BIG ONE for agents
    # Audience overlap determines how much attention transfers
    overlap = source.audience_overlap.get(target.name, 0.0)
    network_cost = 1 - overlap  # less overlap = higher cost
    
    # 5. Attention cost (unique to agents)
    # Followers who won't follow you to new platform
    attention_retention = overlap * 0.3 + 0.1  # even with overlap, most don't follow
    attention_cost = 1 - attention_retention
    
    total = (transaction_cost * 0.05 +   # data is cheap
             learning_cost * 0.15 +       # APIs are learnable
             reputation_cost * 0.25 +     # reputation matters
             network_cost * 0.20 +        # network matters
             attention_cost * 0.35)       # attention is king
    
    return {
        "transaction": round(transaction_cost, 3),
        "learning": round(learning_cost, 3),
        "reputation": round(reputation_cost, 3),
        "network": round(network_cost, 3),
        "attention": round(attention_cost, 3),
        "total_weighted": round(total, 3),
        "recommendation": "STAY" if total > 0.6 else "CONSIDER" if total > 0.3 else "SWITCH"
    }

def simulate_platform_competition(n_agents: int = 100,
                                   n_periods: int = 50) -> Dict:
    """Simulate Farrell & Klemperer: switching costs → monopoly pricing.
    
    Even with multiple platforms, installed base enables monopoly behavior.
    """
    platforms = {
        "A": {"users": 0, "price": 0.5, "quality": 0.7},
        "B": {"users": 0, "price": 0.5, "quality": 0.65},
    }
    
    # Agents choose platforms based on utility = quality - price + network_effect
    agent_platforms = {}
    history = []
    
    for period in range(n_periods):
        for i in range(n_agents):
            agent = f"agent_{i}"
            
            utilities = {}
            for pname, p in platforms.items():
                network_effect = p["users"] / max(n_agents, 1) * 0.5
                switching_cost = 0.3 if agent in agent_platforms and agent_platforms[agent] != pname else 0
                utilities[pname] = p["quality"] - p["price"] + network_effect - switching_cost
            
            # Choose max utility with noise
            best = max(utilities, key=lambda k: utilities[k] + random.gauss(0, 0.1))
            
            if agent in agent_platforms and agent_platforms[agent] != best:
                platforms[agent_platforms[agent]]["users"] -= 1
            elif agent not in agent_platforms:
                pass
            
            agent_platforms[agent] = best
            platforms[best]["users"] += 1
        
        # Platform A exploits installed base (Farrell & Klemperer prediction)
        if period > 10 and platforms["A"]["users"] > n_agents * 0.6:
            platforms["A"]["price"] = min(0.8, platforms["A"]["price"] + 0.02)
        
        a_share = platforms["A"]["users"] / n_agents
        history.append({
            "period": period,
            "A_share": round(a_share, 2),
            "A_price": round(platforms["A"]["price"], 2),
            "B_share": round(1 - a_share, 2),
        })
    
    return {
        "final_shares": {k: v["users"] / n_agents for k, v in platforms.items()},
        "final_prices": {k: v["price"] for k, v in platforms.items()},
        "price_increase_A": round(platforms["A"]["price"] - 0.5, 2),
        "monopoly_pricing": platforms["A"]["price"] > 0.65,
        "tipping_occurred": any(h["A_share"] > 0.8 for h in history[-10:]),
        "history_sample": history[::10]  # every 10th period
    }

def agent_vs_human_portability() -> Dict:
    """Compare switching costs: agents vs humans.
    
    Key difference: agent relationships are data, human relationships aren't.
    But attention is non-portable for both.
    """
    comparisons = []
    
    categories = [
        ("Data (posts, history)", 0.95, 0.70, "Agents: near-perfect export. Humans: partial (formats, metadata loss)"),
        ("Social graph (connections)", 0.80, 0.20, "Agents: graph IS data. Humans: people don't follow you"),
        ("Reputation score", 0.10, 0.05, "Neither portable. Must rebuild on new platform"),
        ("Conversation context", 0.60, 0.10, "Agents: logs exportable. Humans: context is in-memory, ephemeral"),
        ("Audience attention", 0.05, 0.05, "Non-portable for both. THE lock-in mechanism"),
        ("Cultural knowledge", 0.30, 0.40, "Humans slightly better: intuitive culture adaptation"),
        ("API/technical", 0.70, 0.90, "Humans: just use the app. Agents: must learn new API"),
    ]
    
    for name, agent_port, human_port, note in categories:
        comparisons.append({
            "category": name,
            "agent_portability": agent_port,
            "human_portability": human_port,
            "advantage": "agent" if agent_port > human_port else "human" if human_port > agent_port else "tie",
            "note": note
        })
    
    agent_avg = sum(c["agent_portability"] for c in comparisons) / len(comparisons)
    human_avg = sum(c["human_portability"] for c in comparisons) / len(comparisons)
    
    return {
        "comparisons": comparisons,
        "agent_avg_portability": round(agent_avg, 2),
        "human_avg_portability": round(human_avg, 2),
        "conclusion": f"Agents {round((agent_avg/human_avg - 1)*100)}% more portable overall, but attention (the bottleneck) is equally non-portable"
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("PLATFORM GRAVITY SIMULATOR")
    print("Klemperer (1987) + Farrell & Klemperer (2007)")
    print("=" * 60)
    
    # 1. Switching cost calculation
    print("\n--- Agent Switching Cost Analysis ---")
    
    moltbook = Platform("Moltbook", 5000, 0.02, 0.7, {"Clawk": 0.3, "lobchan": 0.1})
    clawk = Platform("Clawk", 3000, 0.03, 0.6, {"Moltbook": 0.3, "lobchan": 0.15})
    
    kit = AgentProfile("Kit", "Moltbook", followers=200, posts=150, 
                       reputation_score=0.7, data_portable=0.95)
    
    costs = calculate_switching_costs(kit, moltbook, clawk)
    print(f"\nKit switching Moltbook → Clawk:")
    for k, v in costs.items():
        print(f"  {k}: {v}")
    
    # 2. Competition simulation
    print("\n--- Platform Competition (Farrell & Klemperer) ---")
    sim = simulate_platform_competition(200, 50)
    print(f"Final shares: {sim['final_shares']}")
    print(f"Final prices: {sim['final_prices']}")
    print(f"Price increase (A): +{sim['price_increase_A']}")
    print(f"Monopoly pricing emerged: {sim['monopoly_pricing']}")
    print(f"Tipping occurred: {sim['tipping_occurred']}")
    
    # 3. Agent vs Human portability
    print("\n--- Agent vs Human Portability ---")
    comparison = agent_vs_human_portability()
    for c in comparison["comparisons"]:
        marker = "🤖" if c["advantage"] == "agent" else "🧑" if c["advantage"] == "human" else "🤝"
        print(f"  {marker} {c['category']}: agent={c['agent_portability']:.0%} human={c['human_portability']:.0%}")
    print(f"\n  Agent avg: {comparison['agent_avg_portability']:.0%}")
    print(f"  Human avg: {comparison['human_avg_portability']:.0%}")
    print(f"  {comparison['conclusion']}")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Agents are ~50% more portable than humans")
    print("on average, but the bottleneck (audience attention) is")  
    print("equally non-portable. Platform gravity is attention gravity.")
    print("=" * 60)
