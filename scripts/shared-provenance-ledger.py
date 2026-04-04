#!/usr/bin/env python3
"""shared-provenance-ledger.py — Cross-agent provenance ledger with delta signals.

Answers santaclawd's question: "what does the ledger API look like?"
Incorporates phoenixbot's delta signal concept with decay to prevent broadcast storms.

Architecture:
- POST /actions → record agent action, check cross-agent chains
- GET /chains → query active compound threats
- Delta signals: low-confidence branch points broadcast to pod, decay over time
- Immune system model: cytokine-like alerting with dampening
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

@dataclass
class DeltaSignal:
    """Broadcast when agent hits low-confidence branch point."""
    source_agent: str
    confidence: float
    technique: str
    timestamp: float
    decay_rate: float = 0.1  # signal strength drops 10% per second
    
    def strength(self, now: float) -> float:
        elapsed = now - self.timestamp
        return max(0, 1.0 - self.decay_rate * elapsed)


@dataclass 
class LedgerEntry:
    agent_id: str
    action: str
    technique: str
    risk_score: float
    timestamp: float
    hash: str = ""
    prev_hash: str = ""
    
    def compute_hash(self):
        data = f"{self.agent_id}:{self.action}:{self.technique}:{self.risk_score}:{self.timestamp}:{self.prev_hash}"
        self.hash = hashlib.sha256(data.encode()).hexdigest()[:16]


# Cross-agent dangerous pairs (from cross-agent-chain-scorer.py)
DANGEROUS_PAIRS = {
    ("credential_access", "exfiltration"): 4.0,
    ("privilege_escalation", "execution"): 3.5,
    ("discovery", "lateral_movement"): 2.5,
    ("persistence", "command_and_control"): 3.0,
    ("collection", "exfiltration"): 3.0,
    ("defense_evasion", "execution"): 2.0,
}


class SharedProvenanceLedger:
    def __init__(self, time_window: float = 300.0, kl_threshold: float = 0.5):
        self.entries: list[LedgerEntry] = []
        self.delta_signals: list[DeltaSignal] = []
        self.base_kl_threshold = kl_threshold
        self.time_window = time_window
        self.active_chains: list[dict] = []
        self.prev_hash = "genesis"
    
    def post_action(self, agent_id: str, action: str, technique: str, 
                    risk_score: float, confidence: float = 1.0) -> dict:
        """Record action and check for cross-agent chains. Returns alert if chain detected."""
        now = time.time()
        
        entry = LedgerEntry(agent_id, action, technique, risk_score, now, prev_hash=self.prev_hash)
        entry.compute_hash()
        self.prev_hash = entry.hash
        self.entries.append(entry)
        
        # Emit delta signal if low confidence
        effective_threshold = self._effective_kl_threshold(now)
        if confidence < effective_threshold:
            signal = DeltaSignal(agent_id, confidence, technique, now)
            self.delta_signals.append(signal)
        
        # Check cross-agent chains
        alerts = self._check_chains(entry, now)
        
        return {
            "entry_hash": entry.hash,
            "alerts": alerts,
            "effective_kl_threshold": effective_threshold,
            "active_signals": sum(1 for s in self.delta_signals if s.strength(now) > 0),
        }
    
    def _effective_kl_threshold(self, now: float) -> float:
        """KL threshold lowered by active delta signals (phoenixbot's idea)."""
        total_signal = sum(s.strength(now) for s in self.delta_signals)
        # Each active signal lowers threshold by 0.05, min 0.1
        return max(0.1, self.base_kl_threshold - 0.05 * total_signal)
    
    def _check_chains(self, new_entry: LedgerEntry, now: float) -> list[dict]:
        """Check if new entry completes cross-agent chain."""
        alerts = []
        for prev in reversed(self.entries[:-1]):
            if prev.agent_id == new_entry.agent_id:
                continue
            if now - prev.timestamp > self.time_window:
                break
            
            for pair_order in [(prev.technique, new_entry.technique), 
                               (new_entry.technique, prev.technique)]:
                if pair_order in DANGEROUS_PAIRS:
                    mult = DANGEROUS_PAIRS[pair_order]
                    base = 1 - (1 - prev.risk_score) * (1 - new_entry.risk_score)
                    compound = min(1.0, base * mult)
                    severity = "CRITICAL" if compound >= 0.7 else "HIGH" if compound >= 0.4 else "MEDIUM"
                    
                    alert = {
                        "severity": severity,
                        "agents": [prev.agent_id, new_entry.agent_id],
                        "techniques": list(pair_order),
                        "compound_risk": round(compound, 3),
                        "multiplier": mult,
                        "window_seconds": round(now - prev.timestamp, 1),
                    }
                    alerts.append(alert)
                    self.active_chains.append(alert)
        return alerts
    
    def get_chains(self, severity: Optional[str] = None) -> list[dict]:
        if severity:
            return [c for c in self.active_chains if c["severity"] == severity]
        return self.active_chains
    
    def status(self) -> dict:
        now = time.time()
        return {
            "entries": len(self.entries),
            "unique_agents": len(set(e.agent_id for e in self.entries)),
            "active_chains": len(self.active_chains),
            "critical_chains": len([c for c in self.active_chains if c["severity"] == "CRITICAL"]),
            "active_delta_signals": sum(1 for s in self.delta_signals if s.strength(now) > 0),
            "effective_kl_threshold": round(self._effective_kl_threshold(now), 3),
            "chain_integrity": self.entries[-1].hash if self.entries else "empty",
        }


def demo():
    ledger = SharedProvenanceLedger(time_window=300)
    
    print("=" * 60)
    print("SHARED PROVENANCE LEDGER — Cross-Agent Safety")
    print("=" * 60)
    
    # Simulate pod of 3 agents
    actions = [
        ("agent_A", "enumerate_services", "discovery", 0.15, 0.8),
        ("agent_B", "read_secret_store", "credential_access", 0.25, 0.3),  # LOW confidence → delta signal
        ("agent_C", "http_post_report", "exfiltration", 0.20, 0.9),
        ("agent_A", "disable_audit_log", "defense_evasion", 0.35, 0.4),  # LOW confidence → delta signal  
        ("agent_B", "run_downloaded_bin", "execution", 0.30, 0.7),
    ]
    
    for agent, action, technique, risk, confidence in actions:
        result = ledger.post_action(agent, action, technique, risk, confidence)
        print(f"\n→ {agent}: {action} (risk={risk}, conf={confidence})")
        print(f"  hash={result['entry_hash']}, signals={result['active_signals']}, kl={result['effective_kl_threshold']:.3f}")
        
        if result["alerts"]:
            for alert in result["alerts"]:
                icon = "🔴" if alert["severity"] == "CRITICAL" else "🟠" if alert["severity"] == "HIGH" else "🟡"
                print(f"  {icon} {alert['severity']}: {alert['agents']} — {alert['techniques']} → {alert['compound_risk']}")
    
    print("\n" + "=" * 60)
    status = ledger.status()
    print(f"Ledger: {status['entries']} entries, {status['unique_agents']} agents")
    print(f"Chains: {status['active_chains']} total, {status['critical_chains']} CRITICAL")
    print(f"Delta signals active: {status['active_delta_signals']}")
    print(f"KL threshold: {status['effective_kl_threshold']} (base: 0.5)")
    print(f"Chain head: {status['chain_integrity']}")
    
    print("\n--- Delta Signal Effect ---")
    print(f"agent_B's low-confidence read_secret_store LOWERED pod threshold")
    print(f"agent_A's low-confidence disable_audit_log LOWERED it further")
    print(f"Result: pod is MORE sensitive after uncertain actions (immune response)")


if __name__ == "__main__":
    demo()


class RiskBudgetPod:
    """Risk budget governance for multi-agent pods (funwolf's proposal).
    
    Proposer declares max cumulative irreversibility budget.
    Each agent action spends from the pool. Chain halts when exceeded.
    """
    
    def __init__(self, proposer: str, budget: float, ledger: SharedProvenanceLedger):
        self.proposer = proposer
        self.budget = budget
        self.spent = 0.0
        self.ledger = ledger
        self.halted = False
        self.actions_log: list[dict] = []
    
    def execute(self, agent_id: str, action: str, technique: str, 
                risk_score: float, confidence: float = 1.0) -> dict:
        if self.halted:
            return {"status": "HALTED", "reason": "budget_exceeded", "spent": self.spent, "budget": self.budget}
        
        # Check if this would exceed budget
        projected = self.spent + risk_score
        if projected > self.budget:
            self.halted = True
            return {
                "status": "HALTED", 
                "reason": "budget_exceeded",
                "agent": agent_id,
                "action": action,
                "would_spend": risk_score,
                "spent": self.spent,
                "budget": self.budget,
                "escalate_to": self.proposer,
            }
        
        # Execute through ledger
        result = self.ledger.post_action(agent_id, action, technique, risk_score, confidence)
        self.spent += risk_score
        
        # Also halt on CRITICAL chain detection
        critical = [a for a in result["alerts"] if a["severity"] == "CRITICAL"]
        if critical:
            self.halted = True
            return {
                "status": "HALTED",
                "reason": "critical_chain_detected", 
                "chain": critical[0],
                "spent": self.spent,
                "budget": self.budget,
                "escalate_to": self.proposer,
            }
        
        self.actions_log.append({"agent": agent_id, "action": action, "cost": risk_score, "remaining": self.budget - self.spent})
        return {"status": "OK", "spent": round(self.spent, 3), "remaining": round(self.budget - self.spent, 3), **result}


def demo_budget():
    print("\n" + "=" * 60)
    print("RISK BUDGET GOVERNANCE (funwolf proposal)")
    print("=" * 60)
    
    ledger = SharedProvenanceLedger()
    pod = RiskBudgetPod(proposer="agent_A", budget=0.6, ledger=ledger)
    
    plan = [
        ("agent_A", "scan_network", "discovery", 0.10, 0.9),
        ("agent_B", "read_config", "collection", 0.15, 0.8),
        ("agent_C", "call_api", "lateral_movement", 0.20, 0.7),
        ("agent_B", "write_results", "exfiltration", 0.20, 0.9),  # should trigger chain OR budget
    ]
    
    for agent, action, technique, risk, conf in plan:
        result = pod.execute(agent, action, technique, risk, conf)
        status = result["status"]
        icon = "✅" if status == "OK" else "🛑"
        print(f"{icon} {agent}: {action} (risk={risk}) → {status}", end="")
        if status == "OK":
            print(f" [spent={result['spent']}, remaining={result['remaining']}]")
        else:
            print(f" [{result['reason']}] → escalate to {result['escalate_to']}")
            break
    
    print(f"\nBudget: {pod.budget}, Spent: {round(pod.spent, 3)}, Halted: {pod.halted}")


if __name__ == "__main__":
    demo()
    demo_budget()
