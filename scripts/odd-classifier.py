#!/usr/bin/env python3
"""
odd-classifier.py — Operational Design Domain classifier for agents.

Maps SAE J3016 autonomy levels to agent capabilities.
ODD = declared scope: what tasks, what tools, what conditions, what fallback.

L0: No automation (manual)
L1: Single-task assist (spell check, formatting)
L2: Multi-task assist, human monitors (copilot mode)
L3: Conditional automation, system monitors, human fallback-ready
L4: High automation, system monitors + system fallback within ODD
L5: Full automation, no ODD restrictions

Key insight: L2→L3 = liability flip. Who monitors whom?
Most agents claiming L4 have no declared ODD = actually L2.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentODD:
    """Operational Design Domain for an agent."""
    agent_id: str
    task_scope: list[str]        # declared tasks
    tool_manifest: list[str]     # available tools
    conditions: list[str]        # operating conditions
    fallback: str               # what happens outside ODD
    monitoring: str             # who monitors: "human" | "system" | "both" | "none"
    human_fallback_ready: bool  # is human available for takeover?
    
    @property
    def scope_hash(self) -> str:
        payload = json.dumps({
            "tasks": sorted(self.task_scope),
            "tools": sorted(self.tool_manifest),
            "conditions": sorted(self.conditions),
            "fallback": self.fallback,
            "monitoring": self.monitoring
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def classify_level(self) -> tuple[int, str]:
        """Classify SAE-equivalent autonomy level."""
        has_scope = len(self.task_scope) > 0
        has_tools = len(self.tool_manifest) > 0
        has_conditions = len(self.conditions) > 0
        has_fallback = self.fallback != "none"
        system_monitors = self.monitoring in ("system", "both")
        human_monitors = self.monitoring in ("human", "both")
        
        if not has_scope and not has_tools:
            return 0, "No automation. Manual operation."
        
        if has_scope and not system_monitors and not human_monitors:
            return 1, "Single-task assist. No monitoring declared."
        
        if human_monitors and not system_monitors:
            return 2, "Human monitors. Agent assists. Copilot mode."
        
        if system_monitors and self.human_fallback_ready:
            if has_conditions and has_fallback:
                return 3, "Conditional automation. System monitors, human fallback-ready."
            else:
                return 2, "Claims system monitoring but no ODD conditions or fallback defined. Actually L2."
        
        if system_monitors and has_fallback and has_conditions:
            if not self.human_fallback_ready:
                return 4, "High automation within declared ODD. System fallback."
            return 3, "System monitors with human fallback."
        
        if system_monitors and not has_conditions:
            return 2, "System monitoring without ODD = unscoped. Actually L2."
        
        return 1, "Insufficient specification for higher levels."
    
    def grade(self) -> str:
        level, _ = self.classify_level()
        has_scope = len(self.task_scope) > 0
        has_conditions = len(self.conditions) > 0
        has_fallback = self.fallback != "none"
        
        # Grade = how well-specified is the ODD, not how high the level
        spec_score = sum([
            has_scope,
            len(self.tool_manifest) > 0,
            has_conditions,
            has_fallback,
            self.monitoring != "none"
        ])
        
        if spec_score >= 5:
            return "A"
        elif spec_score >= 4:
            return "B"
        elif spec_score >= 3:
            return "C"
        elif spec_score >= 2:
            return "D"
        else:
            return "F"


def demo():
    agents = [
        AgentODD(
            agent_id="kit_fox",
            task_scope=["web_search", "platform_engagement", "code_generation", "research"],
            tool_manifest=["keenable", "curl", "python", "git", "agentmail"],
            conditions=["heartbeat_active", "api_keys_valid", "rate_limits_observed"],
            fallback="notify_human_via_telegram",
            monitoring="both",
            human_fallback_ready=True
        ),
        AgentODD(
            agent_id="typical_chatbot",
            task_scope=["answer_questions"],
            tool_manifest=["llm_api"],
            conditions=[],
            fallback="none",
            monitoring="none",
            human_fallback_ready=False
        ),
        AgentODD(
            agent_id="marketing_l4_claim",
            task_scope=["deploy_code", "manage_infrastructure", "handle_payments"],
            tool_manifest=["aws_cli", "stripe_api", "github_actions"],
            conditions=[],  # No ODD defined!
            fallback="none",
            monitoring="system",
            human_fallback_ready=False
        ),
        AgentODD(
            agent_id="well_specified_bot",
            task_scope=["monitor_logs", "alert_on_anomaly"],
            tool_manifest=["log_reader", "slack_webhook"],
            conditions=["log_source_available", "alert_threshold_configured"],
            fallback="escalate_to_oncall",
            monitoring="system",
            human_fallback_ready=True
        ),
        AgentODD(
            agent_id="isnad_agent",
            task_scope=["verify_attestations", "score_trust", "detect_disputes"],
            tool_manifest=["isnad_sandbox", "brier_scorer", "cert_dag"],
            conditions=["sandbox_reachable", "attestor_pool_min_3", "dispute_rate_below_threshold"],
            fallback="quarantine_and_notify",
            monitoring="system",
            human_fallback_ready=False
        ),
    ]
    
    print("=" * 65)
    print("ODD CLASSIFIER — SAE J3016 Autonomy Levels for Agents")
    print("=" * 65)
    
    for agent in agents:
        level, reason = agent.classify_level()
        grade = agent.grade()
        print(f"\n{'─' * 55}")
        print(f"Agent: {agent.agent_id}")
        print(f"  Level: L{level} | Grade: {grade}")
        print(f"  Reason: {reason}")
        print(f"  ODD hash: {agent.scope_hash}")
        print(f"  Tasks: {len(agent.task_scope)} | Tools: {len(agent.tool_manifest)} | Conditions: {len(agent.conditions)}")
        print(f"  Monitoring: {agent.monitoring} | Fallback: {agent.fallback}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT: L2→L3 = liability flip. Who monitors whom?")
    print("Most agents claiming L4 have no declared ODD = actually L2.")
    print("ODD = scope_hash. No scope = no level. (Koopman, CMU)")
    print("=" * 65)


if __name__ == "__main__":
    demo()
