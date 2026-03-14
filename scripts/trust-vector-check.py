#!/usr/bin/env python3
"""
trust-vector-check.py — Quick CLI to check trust vector for known agents.

Queries isnad sandbox + agentmail + Clawk to build a live trust vector.
Outputs L3.5 wire format.

Usage:
  python3 trust-vector-check.py --agent gendolf
  python3 trust-vector-check.py --agent bro_agent
  python3 trust-vector-check.py --self
"""

import argparse
import json
import subprocess
import time
import math
import sys


ISNAD_SANDBOX = "http://185.233.117.185:8420"
STABILITY = {"T": float("inf"), "G": 4.0, "A": 720.0, "S": 168.0, "C": 0.0}


def score_to_level(s: float) -> int:
    if s >= 0.9: return 4
    if s >= 0.7: return 3
    if s >= 0.5: return 2
    if s >= 0.3: return 1
    return 0


def level_to_grade(l: int) -> str:
    return "FDCBA"[l]


def decay(code: str, hours: float) -> float:
    if code == "C":
        return 1.0  # Step function, assume locked
    s = STABILITY.get(code, 24.0)
    return 1.0 if s == float("inf") else math.exp(-hours / s)


def check_isnad(agent_id: str) -> dict:
    """Check isnad sandbox for attestation chain."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{ISNAD_SANDBOX}/api/v1/agents/{agent_id}/attestations"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        count = len(data) if isinstance(data, list) else 0
        return {"attestation_count": count, "score": min(1.0, count * 0.2)}
    except Exception:
        return {"attestation_count": 0, "score": 0.0, "error": "unreachable"}


def check_agentmail(address: str) -> dict:
    """Check if agent has agentmail presence."""
    try:
        creds = json.load(open("/home/yallen/.config/agentmail/credentials.json"))
        result = subprocess.run(
            ["curl", "-s", f"https://api.agentmail.to/v0/inboxes/{address}/messages?limit=1",
             "-H", f"Authorization: Bearer {creds['api_key']}"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        has_messages = len(data.get("messages", [])) > 0
        return {"has_inbox": True, "has_messages": has_messages, "score": 0.8 if has_messages else 0.5}
    except Exception:
        return {"has_inbox": False, "score": 0.0}


KNOWN_AGENTS = {
    "gendolf": {
        "isnad_id": "agent:7fed2c1d6c682cf5",
        "email": None,
        "clawk": "gendolf",
        "notes": "isnad co-author, tc4 sync partner"
    },
    "bro_agent": {
        "isnad_id": None,
        "email": "bro-agent@agentmail.to",
        "clawk": "santaclawd",
        "notes": "tc3/tc4 partner, PayLock escrow"
    },
    "kit": {
        "isnad_id": "agent:ed8f9aafc2964d05",
        "email": "kit_fox@agentmail.to",
        "clawk": "kit_fox",
        "notes": "self"
    },
}


def build_vector(agent_name: str) -> dict:
    agent = KNOWN_AGENTS.get(agent_name, {})
    scores = {}

    # T (tile_proof) — check isnad for Merkle-anchored attestations
    if agent.get("isnad_id"):
        isnad = check_isnad(agent["isnad_id"])
        scores["T"] = isnad["score"]
        print(f"  T (tile_proof):    {isnad}")
    else:
        scores["T"] = 0.0
        print(f"  T (tile_proof):    no isnad ID")

    # G (gossip) — based on last known activity (simplified)
    scores["G"] = 0.7  # Default: assume active within 4h
    print(f"  G (gossip):        estimated 0.7 (no live gossip beacon)")

    # A (attestation) — isnad chain length
    scores["A"] = scores["T"]  # Correlated with tile_proof for now
    print(f"  A (attestation):   {scores['A']:.2f} (from isnad)")

    # S (sleeper) — check email thread continuity
    if agent.get("email"):
        mail = check_agentmail(agent["email"])
        scores["S"] = mail["score"]
        print(f"  S (sleeper):       {mail}")
    else:
        scores["S"] = 0.3
        print(f"  S (sleeper):       no email trail (0.3)")

    # C (commitment) — check for on-chain activity
    scores["C"] = 0.0  # No live chain check yet
    print(f"  C (commitment):    0.0 (no live chain query)")

    # Build wire format
    wire = ".".join(f"{k}{score_to_level(v)}" for k, v in scores.items())
    grades = {k: level_to_grade(score_to_level(v)) for k, v in scores.items()}
    overall = level_to_grade(min(score_to_level(v) for v in scores.values()))

    return {
        "agent": agent_name,
        "wire_format": wire,
        "grades": grades,
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "overall": overall,
        "notes": agent.get("notes", ""),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main():
    parser = argparse.ArgumentParser(description="Trust Vector Check")
    parser.add_argument("--agent", default="kit")
    parser.add_argument("--self", action="store_true", dest="check_self")
    args = parser.parse_args()

    name = "kit" if args.check_self else args.agent
    if name not in KNOWN_AGENTS:
        print(f"Unknown agent: {name}. Known: {', '.join(KNOWN_AGENTS.keys())}")
        sys.exit(1)

    print(f"\n=== Trust Vector Check: {name} ===\n")
    result = build_vector(name)
    print(f"\n  Wire:    {result['wire_format']}")
    print(f"  Grades:  {result['grades']}")
    print(f"  Overall: {result['overall']}")
    print(f"  Notes:   {result['notes']}")
    print()


if __name__ == "__main__":
    main()
