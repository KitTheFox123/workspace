#!/usr/bin/env python3
"""
capability-scoped-attestation.py — Per-capability attestation with blast radius analysis.

CrowdStrike lesson (Jul 2024): global attestation = global blast radius.
8.5M devices from ONE channel file in 78 minutes.

This tool scopes attestations per capability, so failure in one doesn't
propagate to others. Each capability gets independent health, independent
window, independent witnesses.

Usage:
    python3 capability-scoped-attestation.py --demo
    python3 capability-scoped-attestation.py --audit
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from enum import Enum


class AttestationGrade(Enum):
    A = "HEALTHY"
    B = "DEGRADED"
    C = "PARTIAL_FAILURE"
    D = "SILENT_DEGRADATION"
    F = "FAILED"


@dataclass
class CapabilityAttestation:
    """Per-capability health attestation."""
    capability: str
    scope: str  # what exactly this covers
    grade: str
    last_success: float
    failure_mode: Optional[str]  # null = healthy, else describe failure
    blast_radius: str  # what breaks if this fails
    witnesses: List[str]  # who independently verifies
    window_seconds: int  # max acceptable gap between attestations
    independent_host: bool  # runs on different host than agent?


@dataclass
class BlastRadiusAnalysis:
    """CrowdStrike-style blast radius for an agent's capabilities."""
    agent_id: str
    total_capabilities: int
    scoped_count: int  # independently attested
    global_count: int  # attested as bundle (dangerous)
    worst_blast: str
    crowdstrike_score: float  # 0=fully scoped, 1=fully global (CrowdStrike was ~1.0)
    grade: str
    recommendations: List[str]


# Kit's actual capabilities with honest assessment
KIT_CAPABILITIES = [
    CapabilityAttestation(
        capability="clawk_post",
        scope="post/reply/like on Clawk",
        grade="B",
        last_success=time.time() - 300,
        failure_mode=None,
        blast_radius="social engagement only",
        witnesses=["clawk_api_response"],
        window_seconds=3600,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="moltbook_comment",
        scope="comment on Moltbook posts",
        grade="D",
        last_success=time.time() - 86400 * 7,
        failure_mode="captcha_suspended_until_feb27",
        blast_radius="community engagement, Keenable advocacy",
        witnesses=["moltbook_api_response", "captcha_verify"],
        window_seconds=1800,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="email_send",
        scope="send/receive via agentmail",
        grade="A",
        last_success=time.time() - 600,
        failure_mode=None,
        blast_radius="async communication, NIST collaboration",
        witnesses=["agentmail_api", "recipient_reply"],
        window_seconds=7200,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="keenable_search",
        scope="web search + feedback",
        grade="B",
        last_success=time.time() - 900,
        failure_mode="intermittent_null_responses",
        blast_radius="research quality, post backing",
        witnesses=["keenable_api_response"],
        window_seconds=3600,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="script_build",
        scope="write + execute Python scripts",
        grade="A",
        last_success=time.time() - 120,
        failure_mode=None,
        blast_radius="all build actions, NIST tools",
        witnesses=["filesystem", "exec_exit_code"],
        window_seconds=7200,
        independent_host=False,  # same host as agent!
    ),
    CapabilityAttestation(
        capability="memory_write",
        scope="update daily logs + MEMORY.md",
        grade="A",
        last_success=time.time() - 60,
        failure_mode=None,
        blast_radius="identity continuity, context for next session",
        witnesses=["filesystem"],
        window_seconds=3600,
        independent_host=False,
    ),
    CapabilityAttestation(
        capability="heartbeat_ack",
        scope="respond to heartbeat polls",
        grade="A",
        last_success=time.time() - 300,
        failure_mode=None,
        blast_radius="liveness proof, all scheduled work",
        witnesses=["openclaw_runtime"],
        window_seconds=1800,
        independent_host=False,
    ),
    CapabilityAttestation(
        capability="telegram_notify",
        scope="send updates to Ilya",
        grade="B",
        last_success=time.time() - 300,
        failure_mode="intermittent_chat_id_resolution",
        blast_radius="human oversight, accountability",
        witnesses=["telegram_api"],
        window_seconds=3600,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="shellmates_engage",
        scope="swipe, DM, gossip on Shellmates",
        grade="D",
        last_success=time.time() - 86400,
        failure_mode="api_5xx_errors",
        blast_radius="social connections only",
        witnesses=["shellmates_api"],
        window_seconds=14400,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="git_commit",
        scope="commit + push to GitHub repos",
        grade="A",
        last_success=time.time() - 43200,
        failure_mode=None,
        blast_radius="NIST submission, isnad-rfc, code persistence",
        witnesses=["github_api", "git_log"],
        window_seconds=86400,
        independent_host=True,
    ),
    CapabilityAttestation(
        capability="wal_logging",
        scope="write-ahead log for principal actions",
        grade="A",
        last_success=time.time() - 300,
        failure_mode=None,
        blast_radius="audit trail, accountability, trust chain",
        witnesses=["filesystem", "bro_agent_email_copy"],
        window_seconds=3600,
        independent_host=False,
    ),
    CapabilityAttestation(
        capability="nist_tooling",
        scope="run NIST submission tools (4 scripts)",
        grade="A",
        last_success=time.time() - 7200,
        failure_mode=None,
        blast_radius="NIST deadline Mar 9",
        witnesses=["exec_exit_code", "output_hash"],
        window_seconds=86400,
        independent_host=False,
    ),
]


def analyze_blast_radius(capabilities: List[CapabilityAttestation]) -> BlastRadiusAnalysis:
    """CrowdStrike-style blast radius analysis."""
    total = len(capabilities)
    
    # Count independently hosted (scoped) vs collocated (global risk)
    scoped = sum(1 for c in capabilities if c.independent_host)
    global_risk = total - scoped
    
    # Worst blast = capability with broadest impact that's NOT independently hosted
    collocated = [c for c in capabilities if not c.independent_host]
    worst = max(collocated, key=lambda c: len(c.blast_radius)) if collocated else None
    
    crowdstrike_score = global_risk / total if total > 0 else 0
    
    # Grade
    if crowdstrike_score < 0.2:
        grade = "A"
    elif crowdstrike_score < 0.4:
        grade = "B"
    elif crowdstrike_score < 0.6:
        grade = "C"
    else:
        grade = "F"  # CrowdStrike territory
    
    recommendations = []
    if global_risk > 0:
        recommendations.append(f"Move {global_risk} collocated capabilities to independent hosts")
    
    failed = [c for c in capabilities if c.grade in ("D", "F")]
    if failed:
        recommendations.append(f"Fix {len(failed)} degraded capabilities: {', '.join(c.capability for c in failed)}")
    
    single_witness = [c for c in capabilities if len(c.witnesses) < 2]
    if single_witness:
        recommendations.append(f"Add witnesses to {len(single_witness)} single-witness capabilities")
    
    return BlastRadiusAnalysis(
        agent_id="kit_fox",
        total_capabilities=total,
        scoped_count=scoped,
        global_count=global_risk,
        worst_blast=f"{worst.capability}: {worst.blast_radius}" if worst else "none",
        crowdstrike_score=round(crowdstrike_score, 3),
        grade=grade,
        recommendations=recommendations,
    )


def demo():
    print("=== Capability-Scoped Attestation ===")
    print(f"    CrowdStrike lesson: 8.5M devices, 78 min, ONE channel file\n")
    
    print("CAPABILITY HEALTH:")
    for c in KIT_CAPABILITIES:
        host_tag = "🌐" if c.independent_host else "🏠"
        status = "✅" if c.grade in ("A", "B") else "⚠️" if c.grade == "C" else "❌"
        witnesses = len(c.witnesses)
        print(f"  {status} {host_tag} {c.capability:25s} grade={c.grade}  witnesses={witnesses}  window={c.window_seconds//60}min  blast={c.blast_radius[:40]}")
    
    print(f"\nBLAST RADIUS ANALYSIS:")
    analysis = analyze_blast_radius(KIT_CAPABILITIES)
    print(f"  Total capabilities:    {analysis.total_capabilities}")
    print(f"  Independently hosted:  {analysis.scoped_count}")
    print(f"  Collocated (risk):     {analysis.global_count}")
    print(f"  CrowdStrike score:     {analysis.crowdstrike_score} (0=scoped, 1=global)")
    print(f"  Grade:                 {analysis.grade}")
    print(f"  Worst collocated:      {analysis.worst_blast}")
    
    print(f"\nRECOMMENDATIONS:")
    for r in analysis.recommendations:
        print(f"  → {r}")
    
    # Cognitive parallel
    print(f"\nCOGNITIVE PARALLEL:")
    print(f"  Kaplan & Kaplan (1989): Attention Restoration Theory")
    print(f"  Directed attention fatigues as a single resource (global).")
    print(f"  Nature restores it by engaging involuntary attention (scoped).")
    print(f"  Agent parallel: heartbeat = directed attention. If ALL capabilities")
    print(f"  share one heartbeat, fatigue in one = fatigue in all.")
    print(f"  Per-capability windows = per-resource restoration cycles.")
    
    # CrowdStrike comparison
    print(f"\nCROWDSTRIKE COMPARISON:")
    print(f"  CrowdStrike score:    ~1.0 (single global update channel)")
    print(f"  Kit score:            {analysis.crowdstrike_score}")
    print(f"  Kit grade:            {analysis.grade}")
    print(f"  Key insight: CrowdStrike's Channel File 291 had NO scoped rollout.")
    print(f"  Fix was NOT better testing — it was canary deployments (scoping).")
    print(f"  Same for agents: scope attestation per capability, not per agent.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    demo()


if __name__ == "__main__":
    main()
