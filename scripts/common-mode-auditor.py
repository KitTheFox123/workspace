#!/usr/bin/env python3
"""
common-mode-auditor.py — Audit shared failure modes across witness channels.

kampderp's insight: "P(all 3 fail) is only valid if failures are independent.
SMTP + clawk share DNS resolution."

Maps the dependency graph of witness channels and identifies common-mode
failure points that break independence assumptions.

Usage:
    python3 common-mode-auditor.py --demo
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Set
from itertools import combinations


@dataclass
class Channel:
    name: str
    dependencies: List[str]  # infrastructure dependencies
    substrate: str  # network layer classification


@dataclass 
class CommonMode:
    dependency: str
    affected_channels: List[str]
    severity: str  # critical (all channels), high (N-1), medium (N-2)


def build_kit_channels() -> List[Channel]:
    """Kit's current witness channel stack."""
    return [
        Channel("clawk", ["dns", "vercel_cdn", "https_tls", "clawk_api"], "web_api"),
        Channel("email_smtp", ["dns", "smtp_relay", "agentmail_api", "tls"], "smtp"),
        Channel("isnad_sandbox", ["dns", "vps_185.233.117.185", "http", "isnad_api"], "p2p_http"),
        Channel("moltbook", ["dns", "vercel_cdn", "https_tls", "moltbook_api"], "web_api"),
        Channel("telegram", ["dns", "telegram_api", "https_tls", "openclaw_gateway"], "messaging"),
    ]


def audit_common_modes(channels: List[Channel]) -> List[CommonMode]:
    """Find dependencies shared across multiple channels."""
    # Build dependency → channels map
    dep_map: Dict[str, List[str]] = {}
    for ch in channels:
        for dep in ch.dependencies:
            dep_map.setdefault(dep, []).append(ch.name)

    n = len(channels)
    modes = []
    for dep, affected in sorted(dep_map.items(), key=lambda x: -len(x[1])):
        if len(affected) < 2:
            continue
        if len(affected) == n:
            severity = "CRITICAL"
        elif len(affected) >= n - 1:
            severity = "HIGH"
        else:
            severity = "MEDIUM"
        modes.append(CommonMode(dep, affected, severity))

    return modes


def compute_independence_score(channels: List[Channel]) -> dict:
    """Score how independent the channel set is."""
    n = len(channels)
    
    # For each pair, count shared dependencies
    pairs = list(combinations(channels, 2))
    shared_counts = []
    for a, b in pairs:
        shared = set(a.dependencies) & set(b.dependencies)
        shared_counts.append(len(shared))

    # Substrate diversity
    substrates = set(ch.substrate for ch in channels)
    
    # Independence = 1 - (avg shared deps / max possible shared)
    max_deps = max(len(ch.dependencies) for ch in channels)
    avg_shared = sum(shared_counts) / len(shared_counts) if shared_counts else 0
    independence = max(0, 1 - (avg_shared / max_deps)) if max_deps > 0 else 0

    # Grade
    if independence > 0.7 and len(substrates) >= 3:
        grade = "A"
    elif independence > 0.5:
        grade = "B"
    elif independence > 0.3:
        grade = "C"
    else:
        grade = "F"

    return {
        "independence_score": round(independence, 3),
        "substrate_count": len(substrates),
        "substrates": sorted(substrates),
        "channel_count": n,
        "avg_shared_deps": round(avg_shared, 2),
        "grade": grade,
    }


def suggest_fixes(modes: List[CommonMode], channels: List[Channel]) -> List[str]:
    """Suggest fixes for common-mode failures."""
    fixes = []
    critical = [m for m in modes if m.severity == "CRITICAL"]
    
    for m in critical:
        if m.dependency == "dns":
            fixes.append(
                f"DNS is shared across ALL {len(m.affected_channels)} channels. "
                f"Fix: route isnad over Tor/direct IP (removes DNS from 1 channel). "
                f"Or: use DNS-over-HTTPS with different resolvers per channel."
            )
        elif "tls" in m.dependency.lower():
            fixes.append(
                f"TLS shared across {len(m.affected_channels)} channels. "
                f"Fix: isnad over raw TCP with custom auth removes TLS from 1 channel."
            )
    
    for m in [m for m in modes if m.severity == "HIGH"]:
        if "vercel" in m.dependency:
            fixes.append(
                f"Vercel CDN shared by {m.affected_channels}. "
                f"Single provider outage takes both. Diversify hosting."
            )
    
    return fixes


def demo():
    print("=== Common-Mode Failure Auditor ===\n")
    
    channels = build_kit_channels()
    
    print("1. CHANNEL STACK")
    for ch in channels:
        print(f"   {ch.name} [{ch.substrate}]: {', '.join(ch.dependencies)}")
    
    print(f"\n2. COMMON-MODE FAILURES")
    modes = audit_common_modes(channels)
    for m in modes:
        icon = "🔴" if m.severity == "CRITICAL" else "🟡" if m.severity == "HIGH" else "🟢"
        print(f"   {icon} {m.severity}: {m.dependency} → {', '.join(m.affected_channels)}")
    
    print(f"\n3. INDEPENDENCE SCORE")
    score = compute_independence_score(channels)
    print(f"   Score: {score['independence_score']}")
    print(f"   Grade: {score['grade']}")
    print(f"   Substrates: {score['substrate_count']} ({', '.join(score['substrates'])})")
    print(f"   Avg shared deps per pair: {score['avg_shared_deps']}")
    
    print(f"\n4. RECOMMENDED FIXES")
    fixes = suggest_fixes(modes, channels)
    for i, fix in enumerate(fixes, 1):
        print(f"   {i}. {fix}")
    
    # What-if: isnad over Tor
    print(f"\n5. WHAT-IF: ISNAD OVER TOR")
    channels_fixed = build_kit_channels()
    for ch in channels_fixed:
        if ch.name == "isnad_sandbox":
            ch.dependencies = ["tor_network", "vps_185.233.117.185", "isnad_api"]
    
    modes_fixed = audit_common_modes(channels_fixed)
    score_fixed = compute_independence_score(channels_fixed)
    critical_count = len([m for m in modes_fixed if m.severity == "CRITICAL"])
    print(f"   Critical common modes: {critical_count} (was {len([m for m in modes if m.severity == 'CRITICAL'])})")
    print(f"   Independence: {score_fixed['independence_score']} (was {score['independence_score']})")
    print(f"   Grade: {score_fixed['grade']} (was {score['grade']})")
    
    print(f"\n=== SUMMARY ===")
    print(f"   kampderp is right: DNS is a critical common mode across all 5 channels.")
    print(f"   Removing DNS from 1 channel (isnad over Tor) improves independence.")
    print(f"   But Tor adds latency (~2-5s). Tradeoff: independence vs responsiveness.")
    print(f"   Real insight: audit failure modes OF the failure modes, not just the channels.")


def main():
    parser = argparse.ArgumentParser(description="Common-mode failure auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        channels = build_kit_channels()
        modes = audit_common_modes(channels)
        score = compute_independence_score(channels)
        print(json.dumps({
            "common_modes": [asdict(m) for m in modes],
            "independence": score,
        }, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
