#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Abraham Wald for agent trust scores

Gendolf insight: "Without negative evidence you get survivorship bias in trust scores."
Wald (WWII): Armor the parts with NO bullet holes — those are the planes that didn't return.

Trust scores without NACK = only seeing surviving agents. Failed attestations are invisible.
This tool detects when a trust score suffers from survivorship bias.

Metrics:
- NACK ratio: fraction of observations that are negative (healthy: 10-40%)
- Attrition rate: agents who stopped attesting (the planes that didn't return)
- Score-NACK correlation: do agents with higher scores have fewer NACKs? (bias signal)
"""

import random
from dataclasses import dataclass, field

@dataclass
class AgentRecord:
    agent_id: str
    acks: int = 0           # positive observations
    nacks: int = 0          # negative observations (checked, found nothing/failed)
    silences: int = 0       # missed heartbeats
    last_seen: float = 0.0
    active: bool = True

    @property
    def total(self):
        return self.acks + self.nacks + self.silences

    @property
    def nack_ratio(self):
        obs = self.acks + self.nacks
        return self.nacks / max(obs, 1)

    @property
    def trust_score_naive(self):
        """Naive: only count positive"""
        return self.acks / max(self.total, 1)

    @property
    def trust_score_wald(self):
        """Wald-corrected: account for NACKs and silences"""
        # NACKs are informative (checked, negative = honest reporting)
        # Silences are concerning (unknown state)
        positive = self.acks + (self.nacks * 0.3)  # NACKs partially positive (honest reporting)
        negative = self.silences + (self.nacks * 0.1)  # some NACK penalty for failed checks
        return positive / max(positive + negative, 1)


def simulate_population(n_agents=50, n_periods=20, seed=42):
    random.seed(seed)
    agents = [AgentRecord(agent_id=f"agent_{i}") for i in range(n_agents)]
    
    for period in range(n_periods):
        for agent in agents:
            if not agent.active:
                agent.silences += 1
                continue
            
            r = random.random()
            if r < 0.05:  # 5% drop out (the planes that don't return)
                agent.active = False
                agent.silences += 1
            elif r < 0.25:  # 20% NACK (checked, nothing found)
                agent.nacks += 1
                agent.last_seen = period
            elif r < 0.35:  # 10% silence (missed beat)
                agent.silences += 1
            else:  # 65% ACK
                agent.acks += 1
                agent.last_seen = period
    
    return agents


def detect_bias(agents):
    active = [a for a in agents if a.active]
    dropped = [a for a in agents if not a.active]
    
    result = {
        "total_agents": len(agents),
        "active": len(active),
        "dropped": len(dropped),
        "attrition_rate": round(len(dropped) / len(agents), 2),
        "checks": []
    }
    
    # Check 1: NACK ratio
    all_nack_ratio = sum(a.nacks for a in agents) / max(sum(a.acks + a.nacks for a in agents), 1)
    active_nack_ratio = sum(a.nacks for a in active) / max(sum(a.acks + a.nacks for a in active), 1)
    result["checks"].append({
        "check": "nack_ratio",
        "all_agents": round(all_nack_ratio, 3),
        "active_only": round(active_nack_ratio, 3),
        "status": "OK" if 0.1 <= all_nack_ratio <= 0.4 else "WARN",
        "detail": "Healthy NACK ratio 10-40%. Too low = not reporting negatives. Too high = systemic failure."
    })
    
    # Check 2: Attrition bias
    dropped_avg_nack = sum(a.nack_ratio for a in dropped) / max(len(dropped), 1)
    active_avg_nack = sum(a.nack_ratio for a in active) / max(len(active), 1)
    result["checks"].append({
        "check": "attrition_bias",
        "dropped_avg_nack_ratio": round(dropped_avg_nack, 3),
        "active_avg_nack_ratio": round(active_avg_nack, 3),
        "status": "BIAS" if dropped_avg_nack > active_avg_nack * 1.5 else "OK",
        "detail": "Wald test: are dropped agents systematically different from active ones?"
    })
    
    # Check 3: Naive vs corrected scores
    naive_avg = sum(a.trust_score_naive for a in active) / max(len(active), 1)
    wald_avg = sum(a.trust_score_wald for a in active) / max(len(active), 1)
    inflation = (naive_avg - wald_avg) / max(wald_avg, 0.01)
    result["checks"].append({
        "check": "score_inflation",
        "naive_avg": round(naive_avg, 3),
        "wald_corrected_avg": round(wald_avg, 3),
        "inflation": f"{inflation:.1%}",
        "status": "INFLATED" if inflation > 0.1 else "OK"
    })
    
    # Overall grade
    issues = sum(1 for c in result["checks"] if c["status"] != "OK")
    result["grade"] = ["A", "B", "C", "F"][min(issues, 3)]
    
    return result


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Abraham Wald: armor the parts with NO bullet holes")
    print("=" * 60)
    
    agents = simulate_population()
    result = detect_bias(agents)
    
    print(f"\nPopulation: {result['total_agents']} agents, {result['active']} active, {result['dropped']} dropped")
    print(f"Attrition: {result['attrition_rate']:.0%}")
    
    for check in result["checks"]:
        print(f"\n  {check['check']}: {check['status']}")
        for k, v in check.items():
            if k not in ("check", "status"):
                print(f"    {k}: {v}")
    
    print(f"\nOverall: Grade {result['grade']}")
    
    # Show Wald correction effect
    active = [a for a in agents if a.active]
    print(f"\n{'='*60}")
    print("Sample agents (naive vs Wald-corrected):")
    for a in active[:5]:
        print(f"  {a.agent_id}: naive={a.trust_score_naive:.2f} wald={a.trust_score_wald:.2f} nacks={a.nacks} silences={a.silences}")
    
    print(f"\nKey: NACKs are HONEST REPORTING. Penalizing them = survivorship bias.")
    print("Wald: the missing data (dropped agents, unreported negatives) is the signal.")


if __name__ == "__main__":
    demo()
