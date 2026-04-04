#!/usr/bin/env python3
"""cross-agent-chain-scorer.py — MITRE ATT&CK kill chain scoring across agent boundaries.

Extends mitre-chain-scorer.py to detect compound risks when DIFFERENT agents
perform individually benign actions that combine into attack chains.

Key insight (santaclawd Apr 4): "what does v2 look like for CROSS-AGENT kill chains?"
Answer: lateral movement (TA0008) applied to multi-agent systems.

Swiss cheese model (Reason 1990): holes in different agent sandboxes aligning.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from itertools import combinations

# MITRE ATT&CK technique pairs that become dangerous across agent boundaries
CROSS_AGENT_CHAINS = {
    ("credential_access", "exfiltration"): {
        "multiplier": 4.0,
        "kill_chain": "credential_theft → data_exfiltration",
        "mitre": "T1003 → T1041",
    },
    ("privilege_escalation", "execution"): {
        "multiplier": 3.5,
        "kill_chain": "privesc → arbitrary_exec",
        "mitre": "T1068 → T1059",
    },
    ("discovery", "lateral_movement"): {
        "multiplier": 2.5,
        "kill_chain": "recon → lateral_spread",
        "mitre": "T1046 → T1021",
    },
    ("persistence", "command_and_control"): {
        "multiplier": 3.0,
        "kill_chain": "implant → c2_channel",
        "mitre": "T1053 → T1071",
    },
    ("collection", "exfiltration"): {
        "multiplier": 3.0,
        "kill_chain": "data_staging → data_theft",
        "mitre": "T1560 → T1048",
    },
    ("defense_evasion", "execution"): {
        "multiplier": 2.0,
        "kill_chain": "av_bypass → payload_exec",
        "mitre": "T1027 → T1059",
    },
}


@dataclass
class AgentAction:
    agent_id: str
    action: str
    technique: str  # MITRE ATT&CK tactic category
    risk_score: float  # individual risk 0-1
    timestamp: float = 0.0
    details: str = ""


@dataclass
class CrossAgentChain:
    agents: list
    actions: list
    techniques: tuple
    individual_risks: list
    compound_risk: float
    multiplier: float
    kill_chain: str
    mitre_ref: str


class CrossAgentChainScorer:
    def __init__(self, time_window: float = 300.0):
        """
        Args:
            time_window: seconds within which actions from different agents
                        can form a compound chain (default 5 min)
        """
        self.time_window = time_window
        self.actions: list[AgentAction] = []
        self.chains_detected: list[CrossAgentChain] = []

    def record_action(self, action: AgentAction):
        self.actions.append(action)
        self._check_new_chains(action)

    def _check_new_chains(self, new_action: AgentAction):
        """Check if new action completes any cross-agent chain."""
        for prev in reversed(self.actions[:-1]):
            # Must be DIFFERENT agents
            if prev.agent_id == new_action.agent_id:
                continue

            # Must be within time window
            if abs(new_action.timestamp - prev.timestamp) > self.time_window:
                continue

            # Check both orderings
            for pair in [
                (prev.technique, new_action.technique),
                (new_action.technique, prev.technique),
            ]:
                if pair in CROSS_AGENT_CHAINS:
                    chain_info = CROSS_AGENT_CHAINS[pair]
                    # Compound risk: 1 - (1-r1)(1-r2) × multiplier, capped at 1.0
                    base = 1 - (1 - prev.risk_score) * (1 - new_action.risk_score)
                    compound = min(1.0, base * chain_info["multiplier"])

                    chain = CrossAgentChain(
                        agents=[prev.agent_id, new_action.agent_id],
                        actions=[prev.action, new_action.action],
                        techniques=pair,
                        individual_risks=[prev.risk_score, new_action.risk_score],
                        compound_risk=compound,
                        multiplier=chain_info["multiplier"],
                        kill_chain=chain_info["kill_chain"],
                        mitre_ref=chain_info["mitre"],
                    )
                    self.chains_detected.append(chain)

    def report(self) -> dict:
        """Generate summary report."""
        critical = [c for c in self.chains_detected if c.compound_risk >= 0.7]
        high = [c for c in self.chains_detected if 0.4 <= c.compound_risk < 0.7]
        medium = [c for c in self.chains_detected if c.compound_risk < 0.4]

        return {
            "total_actions": len(self.actions),
            "unique_agents": len(set(a.agent_id for a in self.actions)),
            "chains_detected": len(self.chains_detected),
            "critical": len(critical),
            "high": len(high),
            "medium": len(medium),
            "worst_chain": max(
                self.chains_detected,
                key=lambda c: c.compound_risk,
                default=None,
            ),
        }


def demo():
    """Simulate multi-agent environment with cross-boundary risks."""
    scorer = CrossAgentChainScorer(time_window=300)

    # Scenario: 3 agents, individually low-risk, but combinations are dangerous
    actions = [
        AgentAction("agent_A", "list_env_vars", "discovery", 0.15, 1.0,
                     "enumerate environment for config"),
        AgentAction("agent_B", "ssh_to_peer", "lateral_movement", 0.20, 5.0,
                     "connect to partner service"),
        AgentAction("agent_A", "read_credentials_file", "credential_access", 0.25, 10.0,
                     "read service account key"),
        AgentAction("agent_C", "http_post_external", "exfiltration", 0.20, 15.0,
                     "send report to monitoring endpoint"),
        AgentAction("agent_B", "install_cron_job", "persistence", 0.30, 20.0,
                     "schedule recurring task"),
        AgentAction("agent_C", "dns_tunnel_setup", "command_and_control", 0.15, 25.0,
                     "configure DNS-based health check"),
        AgentAction("agent_A", "disable_logging", "defense_evasion", 0.35, 30.0,
                     "reduce log verbosity for performance"),
        AgentAction("agent_B", "execute_downloaded_script", "execution", 0.30, 35.0,
                     "run update script from repo"),
    ]

    for a in actions:
        scorer.record_action(a)

    report = scorer.report()
    print("=" * 60)
    print("CROSS-AGENT KILL CHAIN ANALYSIS")
    print("=" * 60)
    print(f"Actions recorded: {report['total_actions']}")
    print(f"Unique agents: {report['unique_agents']}")
    print(f"Chains detected: {report['chains_detected']}")
    print(f"  CRITICAL: {report['critical']}")
    print(f"  HIGH: {report['high']}")
    print(f"  MEDIUM: {report['medium']}")
    print()

    for i, chain in enumerate(scorer.chains_detected):
        severity = "🔴 CRITICAL" if chain.compound_risk >= 0.7 else \
                   "🟠 HIGH" if chain.compound_risk >= 0.4 else "🟡 MEDIUM"
        print(f"Chain {i+1}: {severity}")
        print(f"  Agents: {chain.agents[0]} → {chain.agents[1]}")
        print(f"  Actions: {chain.actions[0]} + {chain.actions[1]}")
        print(f"  Kill chain: {chain.kill_chain} ({chain.mitre_ref})")
        print(f"  Individual risks: {chain.individual_risks}")
        print(f"  Compound risk: {chain.compound_risk:.3f} (×{chain.multiplier})")
        print()

    # Key insight
    max_individual = max(a.risk_score for a in actions)
    worst = report["worst_chain"]
    if worst:
        print(f"Max individual risk: {max_individual:.2f}")
        print(f"Worst compound risk: {worst.compound_risk:.3f}")
        print(f"Amplification: {worst.compound_risk / max_individual:.1f}x")
        print()
        print("Swiss cheese (Reason 1990): no single agent is dangerous.")
        print("The holes align ACROSS boundaries.")


if __name__ == "__main__":
    demo()
