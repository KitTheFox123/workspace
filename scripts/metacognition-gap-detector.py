#!/usr/bin/env python3
"""
metacognition-gap-detector.py — Detect capability gaps in agent task handling.

Inspired by Sampath & Baskaran (arXiv:2601.09742) "Adaptive Orchestration":
  - Meta-Cognition Engine detects capability gaps
  - Dynamic sub-agent hiring based on gap analysis
  - LRU eviction under resource constraints

Applied to Kit's heartbeat cycle: detect when current context/tools are
insufficient for a task BEFORE attempting it (vs failing and retrying).

Nelson & Narens (1990) metamemory framework:
  - MONITORING: Do I know this? Can I do this?
  - CONTROL: Should I delegate? Should I research first?

FOK (Feeling of Knowing) for agents:
  - High FOK + correct = calibrated
  - High FOK + wrong = overconfident (Dunning-Kruger)
  - Low FOK + correct = underconfident (wasted delegation)
  - Low FOK + wrong = appropriately uncertain
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GapType(Enum):
    KNOWLEDGE = "knowledge"      # Don't have the information
    TOOL = "tool"                # Don't have the tool/capability
    CONTEXT = "context"          # Have it but not in current context window
    FRESHNESS = "freshness"      # Had it but may be stale
    AUTHORITY = "authority"      # Need permission/approval


class Confidence(Enum):
    HIGH = "high"        # >80% FOK — proceed
    MEDIUM = "medium"    # 40-80% — proceed with verification
    LOW = "low"          # 10-40% — research first
    NONE = "none"        # <10% — delegate or skip


class Action(Enum):
    PROCEED = "proceed"
    VERIFY = "verify"          # Proceed but check result
    RESEARCH = "research"      # Keenable search first
    DELEGATE = "delegate"      # Sub-agent or ask human
    SKIP = "skip"              # Not worth the token cost


@dataclass
class CapabilityProfile:
    """What this agent can do right now."""
    tools: set[str] = field(default_factory=set)
    knowledge_domains: set[str] = field(default_factory=set)
    context_files: set[str] = field(default_factory=set)
    last_research: dict[str, float] = field(default_factory=dict)  # domain → timestamp
    authority_level: str = "autonomous"  # autonomous, supervised, restricted
    
    def freshness(self, domain: str, max_age_hours: float = 24.0) -> float:
        """How fresh is our knowledge in a domain? 0.0=stale, 1.0=fresh."""
        if domain not in self.last_research:
            return 0.0
        age_h = (time.time() - self.last_research[domain]) / 3600
        if age_h > max_age_hours:
            return 0.0
        return 1.0 - (age_h / max_age_hours)


@dataclass 
class TaskRequirement:
    """What a task needs."""
    description: str
    required_tools: set[str] = field(default_factory=set)
    required_domains: set[str] = field(default_factory=set)
    required_context: set[str] = field(default_factory=set)
    freshness_required: float = 0.5  # Minimum freshness score
    needs_authority: Optional[str] = None  # None, "supervised", "elevated"


@dataclass
class GapAnalysis:
    """Result of analyzing capability gaps for a task."""
    task: str
    gaps: list[tuple[GapType, str]]  # (type, description)
    confidence: Confidence
    recommended_action: Action
    estimated_cost: str  # "low", "medium", "high" (in tokens/time)
    remediation: list[str]  # Steps to close gaps
    
    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0
    
    def summary(self) -> str:
        lines = [
            f"Task: {self.task}",
            f"Confidence: {self.confidence.value}",
            f"Action: {self.recommended_action.value}",
            f"Gaps: {len(self.gaps)}",
        ]
        for gap_type, desc in self.gaps:
            lines.append(f"  [{gap_type.value}] {desc}")
        if self.remediation:
            lines.append("Remediation:")
            for step in self.remediation:
                lines.append(f"  → {step}")
        return "\n".join(lines)


class MetaCognitionEngine:
    """
    Detect capability gaps before attempting tasks.
    
    Nelson & Narens metamemory: monitor THEN control.
    Don't attempt what you can't do. Don't delegate what you can.
    """
    
    def __init__(self, profile: CapabilityProfile):
        self.profile = profile
        self.history: list[GapAnalysis] = []
        self.calibration: dict[str, dict] = {}  # Track FOK accuracy
    
    def analyze(self, task: TaskRequirement) -> GapAnalysis:
        """Analyze capability gaps for a task."""
        gaps = []
        remediation = []
        
        # 1. Tool gaps
        missing_tools = task.required_tools - self.profile.tools
        for tool in missing_tools:
            gaps.append((GapType.TOOL, f"Missing tool: {tool}"))
            remediation.append(f"Install or configure: {tool}")
        
        # 2. Knowledge domain gaps
        missing_domains = task.required_domains - self.profile.knowledge_domains
        for domain in missing_domains:
            gaps.append((GapType.KNOWLEDGE, f"Unknown domain: {domain}"))
            remediation.append(f"Research via Keenable: {domain}")
        
        # 3. Context gaps (have knowledge but not loaded)
        missing_context = task.required_context - self.profile.context_files
        for ctx in missing_context:
            gaps.append((GapType.CONTEXT, f"Not in context: {ctx}"))
            remediation.append(f"Load file: {ctx}")
        
        # 4. Freshness gaps
        for domain in task.required_domains:
            freshness = self.profile.freshness(domain)
            if freshness < task.freshness_required:
                gaps.append((
                    GapType.FRESHNESS,
                    f"Stale knowledge: {domain} (freshness={freshness:.2f}, "
                    f"need={task.freshness_required:.2f})"
                ))
                remediation.append(f"Refresh research: {domain}")
        
        # 5. Authority gaps
        if task.needs_authority:
            authority_levels = ["restricted", "supervised", "autonomous"]
            current = authority_levels.index(self.profile.authority_level)
            needed = authority_levels.index(task.needs_authority)
            if current < needed:
                gaps.append((
                    GapType.AUTHORITY,
                    f"Need {task.needs_authority}, have {self.profile.authority_level}"
                ))
                remediation.append(f"Request elevated access from human")
        
        # Determine confidence and action
        confidence = self._assess_confidence(gaps, task)
        action = self._recommend_action(confidence, gaps)
        cost = self._estimate_cost(gaps)
        
        analysis = GapAnalysis(
            task=task.description,
            gaps=gaps,
            confidence=confidence,
            recommended_action=action,
            estimated_cost=cost,
            remediation=remediation,
        )
        
        self.history.append(analysis)
        return analysis
    
    def _assess_confidence(self, gaps: list, task: TaskRequirement) -> Confidence:
        """FOK assessment based on gap analysis."""
        if not gaps:
            return Confidence.HIGH
        
        # Weight gaps by severity
        severity = 0
        for gap_type, _ in gaps:
            if gap_type == GapType.AUTHORITY:
                severity += 3  # Can't work around this
            elif gap_type == GapType.TOOL:
                severity += 2  # Hard to fake
            elif gap_type == GapType.KNOWLEDGE:
                severity += 2  # Need research
            elif gap_type == GapType.FRESHNESS:
                severity += 1  # Might still be ok
            elif gap_type == GapType.CONTEXT:
                severity += 0.5  # Easy to fix
        
        if severity >= 4:
            return Confidence.NONE
        elif severity >= 2:
            return Confidence.LOW
        elif severity >= 1:
            return Confidence.MEDIUM
        return Confidence.HIGH
    
    def _recommend_action(self, confidence: Confidence, 
                          gaps: list[tuple[GapType, str]]) -> Action:
        """Determine action based on confidence and gap types."""
        if confidence == Confidence.HIGH:
            return Action.PROCEED
        
        if confidence == Confidence.NONE:
            # Check if any gaps are authority — must delegate
            if any(g[0] == GapType.AUTHORITY for g in gaps):
                return Action.DELEGATE
            # If all gaps are fixable (knowledge/freshness/context), research
            fixable = all(
                g[0] in (GapType.KNOWLEDGE, GapType.FRESHNESS, GapType.CONTEXT)
                for g in gaps
            )
            return Action.RESEARCH if fixable else Action.SKIP
        
        if confidence == Confidence.LOW:
            # Can we fix with research?
            fixable = all(
                g[0] in (GapType.KNOWLEDGE, GapType.FRESHNESS, GapType.CONTEXT)
                for g in gaps
            )
            return Action.RESEARCH if fixable else Action.DELEGATE
        
        # MEDIUM confidence
        return Action.VERIFY
    
    def _estimate_cost(self, gaps: list) -> str:
        """Estimate token/time cost to close gaps."""
        if not gaps:
            return "low"
        total = sum(
            2 if g[0] in (GapType.TOOL, GapType.AUTHORITY) else 1
            for g in gaps
        )
        if total >= 4:
            return "high"
        elif total >= 2:
            return "medium"
        return "low"
    
    def record_outcome(self, task_desc: str, predicted_confidence: Confidence,
                       actual_success: bool):
        """Track FOK calibration (predicted confidence vs actual outcome)."""
        key = predicted_confidence.value
        if key not in self.calibration:
            self.calibration[key] = {"total": 0, "correct": 0}
        self.calibration[key]["total"] += 1
        if actual_success:
            self.calibration[key]["correct"] += 1
    
    def calibration_report(self) -> dict:
        """How well-calibrated is our FOK?"""
        report = {}
        for level, stats in self.calibration.items():
            accuracy = stats["correct"] / max(stats["total"], 1)
            expected = {"high": 0.9, "medium": 0.6, "low": 0.25, "none": 0.05}
            deviation = abs(accuracy - expected.get(level, 0.5))
            report[level] = {
                "accuracy": f"{accuracy:.0%}",
                "expected": f"{expected.get(level, 0.5):.0%}",
                "calibration_error": f"{deviation:.0%}",
                "n": stats["total"],
            }
        return report


def demo():
    """Demonstrate gap detection for heartbeat tasks."""
    print("=" * 60)
    print("METACOGNITION GAP DETECTOR")
    print("Nelson & Narens (1990) + Sampath & Baskaran (2601.09742)")
    print("=" * 60)
    
    # Kit's current capability profile
    profile = CapabilityProfile(
        tools={"keenable", "moltbook_api", "clawk_api", "agentmail", "shellmates",
               "git", "python", "mcporter"},
        knowledge_domains={"trust_systems", "memory_architecture", "CT_enforcement",
                          "agent_platforms", "cryptography", "cognitive_science"},
        context_files={"SOUL.md", "MEMORY.md", "HEARTBEAT.md", "TOOLS.md"},
        last_research={
            "CT_enforcement": time.time() - 3600,  # 1h ago
            "trust_systems": time.time() - 7200,    # 2h ago
            "memory_architecture": time.time() - 86400,  # 24h ago
            "EU_AI_Act": time.time() - 172800,  # 48h ago
        },
        authority_level="autonomous",
    )
    
    engine = MetaCognitionEngine(profile)
    
    tasks = [
        TaskRequirement(
            description="Reply to Clawk thread on Merkle receipt enforcement",
            required_tools={"clawk_api", "keenable"},
            required_domains={"CT_enforcement", "trust_systems"},
            required_context={"TOOLS.md"},
            freshness_required=0.3,
        ),
        TaskRequirement(
            description="Comment on quantum computing post",
            required_tools={"moltbook_api", "keenable"},
            required_domains={"quantum_computing"},
            required_context={"TOOLS.md"},
            freshness_required=0.5,
        ),
        TaskRequirement(
            description="Deploy L3.5 receipt validator to production",
            required_tools={"docker", "kubernetes"},
            required_domains={"trust_systems", "devops"},
            required_context={"TOOLS.md"},
            needs_authority="supervised",
        ),
        TaskRequirement(
            description="Update memory files after heartbeat",
            required_tools={"git"},
            required_domains=set(),
            required_context={"MEMORY.md"},
            freshness_required=0.0,
        ),
        TaskRequirement(
            description="Research EU AI Act enforcement timeline",
            required_tools={"keenable"},
            required_domains={"EU_AI_Act", "regulatory_compliance"},
            required_context=set(),
            freshness_required=0.8,
        ),
    ]
    
    for task in tasks:
        analysis = engine.analyze(task)
        print(f"\n{'─' * 50}")
        print(analysis.summary())
    
    # Simulate calibration tracking
    print(f"\n{'=' * 60}")
    print("FOK CALIBRATION")
    print("=" * 60)
    
    # Simulate outcomes
    engine.record_outcome("Merkle reply", Confidence.HIGH, True)
    engine.record_outcome("Merkle reply 2", Confidence.HIGH, True)
    engine.record_outcome("Quantum post", Confidence.LOW, False)
    engine.record_outcome("Memory update", Confidence.HIGH, True)
    engine.record_outcome("EU research", Confidence.MEDIUM, True)
    engine.record_outcome("Docker deploy", Confidence.NONE, False)
    
    report = engine.calibration_report()
    for level, stats in report.items():
        print(f"  {level}: accuracy={stats['accuracy']} "
              f"(expected {stats['expected']}, error={stats['calibration_error']}, "
              f"n={stats['n']})")


if __name__ == "__main__":
    demo()
