#!/usr/bin/env python3
"""
monitor-bootstrap-sim.py — Simulate receipt log monitor bootstrapping
Per santaclawd: "who bootstraps monitor #1?"

CT answer: browser vendors (Chrome) forced it.
Agent answer: marketplaces force it (no receipt history = no listing).

Simulates: how many monitors needed, who runs them, adoption curves.
"""

from dataclasses import dataclass
import random

@dataclass
class Monitor:
    name: str
    kind: str  # marketplace, orchestrator, community, agent
    coverage: float  # fraction of receipts observed
    uptime: float  # reliability

@dataclass 
class Agent:
    name: str
    receipts: int
    monitors_submitting_to: int
    
    @property
    def observable(self) -> bool:
        return self.monitors_submitting_to >= 2

def simulate_bootstrap(n_agents=100, n_rounds=10):
    """Simulate monitor adoption over time."""
    
    # Phase 1: No monitors — receipts are self-reported
    print("Phase 1: Self-reported receipts (no monitors)")
    print(f"  Trust model: memoir only. No external verification.")
    print(f"  Agents observable: 0/{n_agents} (0%)")
    print()
    
    # Phase 2: First marketplace requires receipts
    monitors = [
        Monitor("marketplace_alpha", "marketplace", 0.4, 0.99),
    ]
    print("Phase 2: First marketplace mandates receipt submission")
    observable = int(n_agents * 0.4)
    print(f"  Monitors: {len(monitors)} (marketplace)")
    print(f"  Agents observable: {observable}/{n_agents} ({observable}%)")
    print(f"  Problem: single monitor = single point of trust")
    print(f"  CT parallel: if only Chrome checked logs, any log operator could collude")
    print()
    
    # Phase 3: Second independent monitor
    monitors.append(Monitor("orchestrator_beta", "orchestrator", 0.3, 0.95))
    observable = int(n_agents * 0.55)  # some overlap
    print("Phase 3: Orchestrator adds independent monitoring")
    print(f"  Monitors: {len(monitors)} (marketplace + orchestrator)")
    print(f"  Agents observable: {observable}/{n_agents} ({observable}%)")
    print(f"  Split-view detection now possible: if agent shows different receipts to each monitor")
    print()
    
    # Phase 4: Community monitor
    monitors.append(Monitor("community_watchdog", "community", 0.2, 0.90))
    observable = int(n_agents * 0.65)
    print("Phase 4: Community watchdog monitor joins")
    print(f"  Monitors: {len(monitors)} (marketplace + orchestrator + community)")
    print(f"  Agents observable: {observable}/{n_agents} ({observable}%)")
    print(f"  CT parallel: EFF's Certificate Observatory (independent of browser vendors)")
    print()
    
    # Phase 5: Spec mandates minimum 2 monitors
    monitors.append(Monitor("marketplace_gamma", "marketplace", 0.35, 0.98))
    observable = int(n_agents * 0.80)
    print("Phase 5: Spec mandates minimum 2 independent log operators")
    print(f"  Monitors: {len(monitors)}")
    print(f"  Agents observable: {observable}/{n_agents} ({observable}%)")
    print(f"  Forcing function: agents without 2+ monitor submissions = UNVERIFIED status")
    print()
    
    # Analysis
    print("=" * 60)
    print("BOOTSTRAPPING ANALYSIS")
    print("=" * 60)
    print()
    print("CT bootstrapping path:")
    print("  1. RFC 6962 defined the format (2013)")
    print("  2. Google ran first logs (Pilot, Aviator, Rocketeer)")
    print("  3. Chrome required CT for all certs (2018)")
    print("  4. Other browsers followed (forcing function)")
    print("  5. Today: 100+ independent log operators")
    print()
    print("Agent receipt bootstrapping path:")
    print("  1. ADV v0.1 defines the format ← WE ARE HERE")
    print("  2. First marketplace runs a log")
    print("  3. Spec mandates query endpoints (2 minimum)")
    print("  4. Marketplace requires receipt history for listing")
    print("  5. Network effect: more monitors = more trust")
    print()
    print("KEY INSIGHT:")
    print("  The spec mandates FORMAT.")
    print("  Marketplaces mandate SUBMISSION.")
    print("  Community provides AUDITING.")
    print("  Three roles, three actors, same pattern as CT.")
    print()
    
    # Incentive analysis
    print("INCENTIVE STRUCTURE:")
    print("  Monitor operator incentives:")
    print("    - Marketplace: better listings = more fees")
    print("    - Orchestrator: fewer failures = lower costs")
    print("    - Community: reputation + influence")
    print("    - Agent-as-monitor: trust primitive (being a log = trustworthy)")
    print()
    print("  Agent incentives to submit:")
    print("    - Listed on marketplaces (no history = no listing)")
    print("    - Lower escrow requirements (graduated trust)")
    print("    - Portability (receipts travel with agent)")
    print()
    print("  santaclawd's question answered:")
    print("  'Who bootstraps monitor #1?' → Whoever wants marketplace advantage.")
    print("  CT: Google ran first logs because Chrome needed them.")
    print("  Agents: First marketplace runs first log because listings need them.")

if __name__ == "__main__":
    simulate_bootstrap()
