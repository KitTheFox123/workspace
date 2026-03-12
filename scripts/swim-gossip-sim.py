#!/usr/bin/env python3
"""
swim-gossip-sim.py — SWIM protocol gossip simulation for agent trust networks.

Based on Das, Gupta & Motivala 2002 (SWIM: Scalable Weakly-consistent
Infection-style Process Group Membership).

Models the three-layer architecture from santaclawd's convergence:
1. SWIM gossip (failure detection + membership)
2. Φ accrual failure detector (Hayashibara 2004) per channel
3. DKIM-style signed observations (attestation piggybacked on pings)

Usage: python3 swim-gossip-sim.py
"""

import hashlib
import random
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Observation:
    """Signed observation piggybacked on SWIM ping."""
    observer: str
    target: str
    scope_hash: str
    timestamp: int
    signature: str  # simplified: hash of content + key
    status: str  # "alive", "suspect", "failed"


@dataclass
class PhiScore:
    """Φ accrual failure detector per agent."""
    heartbeat_times: list[int] = field(default_factory=list)
    
    def record(self, t: int):
        self.heartbeat_times.append(t)
    
    def phi(self, now: int) -> float:
        """Compute Φ suspicion score. Higher = more suspicious."""
        if len(self.heartbeat_times) < 2:
            return 0.0
        intervals = [self.heartbeat_times[i+1] - self.heartbeat_times[i] 
                     for i in range(len(self.heartbeat_times)-1)]
        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return 0.0
        variance = sum((x - mean)**2 for x in intervals) / len(intervals)
        std = math.sqrt(variance) if variance > 0 else mean * 0.1
        time_since = now - self.heartbeat_times[-1]
        if std == 0:
            return 10.0 if time_since > mean * 2 else 0.0
        # Φ = -log10(P(interval > time_since))
        z = (time_since - mean) / std
        # Approximate survival function
        p = 0.5 * math.erfc(z / math.sqrt(2))
        return -math.log10(max(p, 1e-10))


@dataclass 
class SwimAgent:
    name: str
    alive: bool = True
    compromised: bool = False
    membership: dict = field(default_factory=dict)  # name -> status
    phi_detectors: dict = field(default_factory=dict)  # name -> PhiScore
    observations: list[Observation] = field(default_factory=list)
    gossip_buffer: list[dict] = field(default_factory=list)
    
    def ping(self, target: 'SwimAgent', t: int) -> Optional[Observation]:
        """SWIM ping with piggybacked observation."""
        if not self.alive:
            return None
        
        if target.alive and not target.compromised:
            # Successful ping
            if target.name not in self.phi_detectors:
                self.phi_detectors[target.name] = PhiScore()
            self.phi_detectors[target.name].record(t)
            self.membership[target.name] = "alive"
            
            # Create signed observation
            obs = Observation(
                observer=self.name,
                target=target.name,
                scope_hash=hashlib.sha256(f"{target.name}:alive:{t}".encode()).hexdigest()[:8],
                timestamp=t,
                signature=hashlib.sha256(f"{self.name}:{target.name}:{t}:key".encode()).hexdigest()[:12],
                status="alive"
            )
            self.observations.append(obs)
            return obs
        else:
            # Failed ping — enter suspicion phase
            self.membership[target.name] = "suspect"
            return None
    
    def indirect_ping(self, target_name: str, helpers: list['SwimAgent'], t: int) -> bool:
        """SWIM indirect ping via k helpers."""
        for helper in helpers:
            if helper.alive and helper.name != target_name:
                # Helper tries to ping target
                target_agent = next((a for a in helpers if a.name == target_name), None)
                if target_agent and target_agent.alive:
                    return True
        return False
    
    def check_phi(self, target_name: str, now: int, threshold: float = 8.0) -> str:
        """Check Φ accrual score for a target."""
        if target_name not in self.phi_detectors:
            return "unknown"
        phi = self.phi_detectors[target_name].phi(now)
        if phi >= threshold:
            return "failed"
        elif phi >= 4.0:
            return "suspect"
        return "alive"
    
    def disseminate(self, info: dict):
        """Piggyback gossip on next ping (infection-style)."""
        self.gossip_buffer.append(info)


def simulate_swim(agents: list[SwimAgent], rounds: int = 20, 
                  fail_at: dict = None, compromise_at: dict = None) -> dict:
    """Run SWIM simulation."""
    fail_at = fail_at or {}
    compromise_at = compromise_at or {}
    
    events = []
    detections = {}  # who detected what, when
    
    for t in range(rounds):
        # Apply failures/compromises
        for name, fail_round in fail_at.items():
            if t == fail_round:
                agent = next(a for a in agents if a.name == name)
                agent.alive = False
                events.append({"round": t, "event": "CRASH", "agent": name})
        
        for name, comp_round in compromise_at.items():
            if t == comp_round:
                agent = next(a for a in agents if a.name == name)
                agent.compromised = True
                events.append({"round": t, "event": "COMPROMISED", "agent": name})
        
        alive_agents = [a for a in agents if a.alive]
        
        for agent in alive_agents:
            # SWIM: pick random target to ping
            others = [a for a in agents if a.name != agent.name]
            if not others:
                continue
            target = random.choice(others)
            
            obs = agent.ping(target, t)
            
            if obs is None and target.name not in detections:
                # Direct ping failed — try indirect (k=3)
                helpers = random.sample([a for a in alive_agents if a.name != agent.name], 
                                       min(3, len(alive_agents) - 1))
                success = agent.indirect_ping(target.name, [target] + helpers, t)
                
                if not success:
                    agent.membership[target.name] = "failed"
                    # Disseminate failure
                    agent.disseminate({"type": "failed", "target": target.name, "round": t})
                    
                    if target.name not in detections:
                        detections[target.name] = {"detected_by": agent.name, "round": t}
                        events.append({
                            "round": t, "event": "DETECTED",
                            "target": target.name, "by": agent.name,
                            "phi": round(agent.phi_detectors.get(target.name, PhiScore()).phi(t), 2)
                        })
            
            # Process gossip buffer — piggyback on pings
            if agent.gossip_buffer and obs:
                for other in alive_agents:
                    if other.name != agent.name:
                        for gossip in agent.gossip_buffer:
                            other.membership[gossip["target"]] = gossip["type"]
                agent.gossip_buffer.clear()
    
    # Collect results
    total_observations = sum(len(a.observations) for a in agents)
    detection_times = {}
    for name, fail_round in fail_at.items():
        if name in detections:
            detection_times[name] = detections[name]["round"] - fail_round
        else:
            detection_times[name] = None  # undetected
    
    return {
        "events": events,
        "detection_times": detection_times,
        "total_observations": total_observations,
        "rounds": rounds,
        "agents": len(agents)
    }


def demo():
    print("=" * 60)
    print("SWIM Gossip Simulation for Agent Trust Networks")
    print("Das, Gupta & Motivala 2002 + Φ Accrual (Hayashibara 2004)")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "Clean network (5 agents, no failures)",
            "agents": ["kit", "santa", "gendolf", "hash", "gerundium"],
            "fail_at": {},
            "compromise_at": {},
            "rounds": 15
        },
        {
            "name": "Single crash (gendolf fails at round 5)",
            "agents": ["kit", "santa", "gendolf", "hash", "gerundium"],
            "fail_at": {"gendolf": 5},
            "compromise_at": {},
            "rounds": 15
        },
        {
            "name": "Byzantine (hash compromised at round 3)",
            "agents": ["kit", "santa", "gendolf", "hash", "gerundium"],
            "fail_at": {},
            "compromise_at": {"hash": 3},
            "rounds": 15
        },
        {
            "name": "Cascade (2 failures + 1 compromise)",
            "agents": ["kit", "santa", "gendolf", "hash", "gerundium", "cassian", "funwolf"],
            "fail_at": {"gerundium": 4, "cassian": 7},
            "compromise_at": {"hash": 5},
            "rounds": 20
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")
        
        agents = [SwimAgent(name=n) for n in scenario["agents"]]
        # Initialize membership
        for a in agents:
            for b in agents:
                if a.name != b.name:
                    a.membership[b.name] = "alive"
        
        random.seed(42)  # reproducible
        result = simulate_swim(
            agents, 
            rounds=scenario["rounds"],
            fail_at=scenario["fail_at"],
            compromise_at=scenario["compromise_at"]
        )
        
        print(f"Rounds: {result['rounds']}, Observations: {result['total_observations']}")
        
        # Detection times
        if result["detection_times"]:
            for name, dt in result["detection_times"].items():
                if dt is not None:
                    print(f"  {name}: detected in {dt} rounds (SWIM T'={dt})")
                else:
                    print(f"  {name}: UNDETECTED ⚠️")
        
        # Key events
        for event in result["events"]:
            if event["event"] in ("CRASH", "COMPROMISED", "DETECTED"):
                print(f"  Round {event['round']}: {event['event']} "
                      f"{'→ ' + event.get('target', event.get('agent', ''))}"
                      f"{' by ' + event['by'] if 'by' in event else ''}"
                      f"{' (Φ=' + str(event['phi']) + ')' if 'phi' in event else ''}")
        
        # Final membership view
        alive_agents = [a for a in agents if a.alive]
        if alive_agents:
            consensus = {}
            for a in alive_agents:
                for name, status in a.membership.items():
                    if name not in consensus:
                        consensus[name] = {}
                    consensus[name][status] = consensus[name].get(status, 0) + 1
            
            divergent = {k: v for k, v in consensus.items() if len(v) > 1}
            if divergent:
                print(f"  ⚠️ Split views: {divergent}")
            else:
                print(f"  ✓ Consistent membership view")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("• SWIM outsourced heartbeats = O(1) per agent per round")
    print("• Φ accrual = continuous suspicion, not binary alive/dead")
    print("• Piggybacked gossip = zero extra messages for dissemination")
    print("• Agent trust: piggyback signed observations on SWIM pings")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
