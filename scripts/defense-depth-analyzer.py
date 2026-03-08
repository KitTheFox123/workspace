#!/usr/bin/env python3
"""defense-depth-analyzer.py — Layered defense coverage analyzer for agent trust.

Maps attack surfaces across verification layers (install-time, deploy-time,
runtime, post-hoc audit). Identifies TOCTOU gaps between layers.
Inspired by hash/SkillFence + isnad confused-deputy-detector collaboration.

Usage:
    python3 defense-depth-analyzer.py [--demo] [--check LAYER]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class VerificationLayer:
    """A defense layer with coverage analysis."""
    name: str
    phase: str  # install, deploy, runtime, audit
    what_it_catches: List[str]
    what_it_misses: List[str]
    toctou_gap_to_next: Optional[str]
    tools: List[str]  # isnad tools that implement this layer
    tcg_model: str  # SRTM or DRTM


LAYERS = [
    VerificationLayer(
        name="install_attestation",
        phase="install",
        what_it_catches=[
            "known_malicious_packages",
            "unsigned_skills",
            "version_mismatch",
            "dependency_confusion",
        ],
        what_it_misses=[
            "runtime_behavior_drift",
            "context_dependent_attacks",
            "compositional_attacks_across_skills",
            "supply_chain_compromise_post_sign",
        ],
        toctou_gap_to_next="install → deploy: skill could be modified between install hash and deployment",
        tools=["SkillFence (external)"],
        tcg_model="SRTM",
    ),
    VerificationLayer(
        name="deploy_scope_commit",
        phase="deploy",
        what_it_catches=[
            "scope_exceeding_authorization",
            "missing_principal_signature",
            "expired_credentials",
            "confused_deputy_at_issuance",
        ],
        what_it_misses=[
            "gradual_drift_within_scope",
            "behavioral_change_post_deploy",
            "collusion_between_agents",
        ],
        toctou_gap_to_next="deploy → runtime: scope valid at deploy, violated during execution",
        tools=["scope-cert-issuer.py", "intent-commit.py", "confused-deputy-detector.py"],
        tcg_model="DRTM",
    ),
    VerificationLayer(
        name="runtime_monitoring",
        phase="runtime",
        what_it_catches=[
            "scope_violation_in_progress",
            "behavioral_drift_cusum",
            "behavioral_change_post_deploy",
            "runtime_behavior_drift",
            "gradual_drift_within_scope",
            "heartbeat_liveness_failure",
            "timing_anomalies",
        ],
        what_it_misses=[
            "sophisticated_masking",
            "attacks_below_cusum_threshold",
            "collusion_with_monitor",
        ],
        toctou_gap_to_next="runtime → audit: evidence could be tampered before logging",
        tools=["scope-drift-detector.py", "three-signal-verdict.py", "liveness-renewal.py", "timing-side-channel.py"],
        tcg_model="DRTM",
    ),
    VerificationLayer(
        name="post_hoc_audit",
        phase="audit",
        what_it_catches=[
            "historical_pattern_analysis",
            "cross_agent_collusion_patterns",
            "collusion_between_agents",
            "attestation_staleness",
            "log_tampering",
            "supply_chain_compromise_post_sign",
            "compositional_attacks_across_skills",
        ],
        what_it_misses=[
            "real_time_attacks_already_completed",
            "evidence_destroyed_before_log",
        ],
        toctou_gap_to_next=None,
        tools=["scope-transparency-log.py", "attestation-burst-detector.py", "confounding-graph-mapper.py"],
        tcg_model="SRTM",
    ),
]


def analyze_coverage() -> dict:
    """Full coverage analysis across all layers."""
    all_catches = set()
    all_misses = set()
    gaps = []
    
    for layer in LAYERS:
        all_catches.update(layer.what_it_catches)
        all_misses.update(layer.what_it_misses)
        if layer.toctou_gap_to_next:
            gaps.append({
                "between": f"{layer.phase} → next",
                "gap": layer.toctou_gap_to_next,
            })
    
    # Attacks caught by later layers
    covered_by_depth = all_misses & all_catches
    truly_uncovered = all_misses - all_catches
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layers": [asdict(l) for l in LAYERS],
        "coverage": {
            "total_attack_types_caught": len(all_catches),
            "total_attack_types_missed_per_layer": len(all_misses),
            "covered_by_defense_in_depth": len(covered_by_depth),
            "truly_uncovered": len(truly_uncovered),
            "depth_coverage_pct": round(100 * len(covered_by_depth) / max(len(all_misses), 1), 1),
        },
        "covered_by_depth": sorted(covered_by_depth),
        "truly_uncovered": sorted(truly_uncovered),
        "toctou_gaps": gaps,
        "recommendation": (
            "Defense in depth covers {}/{} attack types missed by individual layers. "
            "{} truly uncovered: {}. These require new detection mechanisms."
        ).format(
            len(covered_by_depth), len(all_misses),
            len(truly_uncovered), ", ".join(sorted(truly_uncovered)[:3]) + ("..." if len(truly_uncovered) > 3 else "")
        ),
    }


def demo():
    """Demo output."""
    result = analyze_coverage()
    
    print("=" * 60)
    print("DEFENSE IN DEPTH — LAYER COVERAGE ANALYSIS")
    print("=" * 60)
    print()
    
    for layer in result["layers"]:
        model = layer["tcg_model"]
        print(f"[{layer['phase'].upper()}] {layer['name']} ({model})")
        print(f"  Catches: {', '.join(layer['what_it_catches'][:3])}...")
        print(f"  Misses:  {', '.join(layer['what_it_misses'][:2])}...")
        if layer["toctou_gap_to_next"]:
            print(f"  TOCTOU:  {layer['toctou_gap_to_next']}")
        print(f"  Tools:   {', '.join(layer['tools'][:2])}")
        print()
    
    c = result["coverage"]
    print("-" * 60)
    print(f"Attack types caught (any layer):  {c['total_attack_types_caught']}")
    print(f"Missed per-layer but caught by depth: {c['covered_by_defense_in_depth']}")
    print(f"Truly uncovered: {c['truly_uncovered']}")
    print(f"Depth coverage: {c['depth_coverage_pct']}%")
    print()
    print(f"Uncovered: {', '.join(result['truly_uncovered'])}")
    print()
    print(f"TOCTOU gaps: {len(result['toctou_gaps'])}")
    for gap in result["toctou_gaps"]:
        print(f"  {gap['gap']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Defense in depth coverage analyzer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(analyze_coverage(), indent=2))
    else:
        demo()
