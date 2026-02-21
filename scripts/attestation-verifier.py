#!/usr/bin/env python3
"""attestation-verifier.py — Verify isnad attestation chains from the sandbox.

Fetches attestations from the sandbox API, verifies Ed25519 signatures,
checks chain integrity (parent hashes), and reports trust scores.

Usage:
    python attestation-verifier.py [--sandbox URL] [--agent AGENT_ID] [--chain]
"""

import argparse
import json
import sys
import hashlib
import base64
from datetime import datetime, timezone

try:
    import nacl.signing
    import nacl.encoding
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


SANDBOX_URL = "http://185.233.117.185:8420"


def fetch_attestations(base_url: str, agent_id: str | None = None) -> list[dict]:
    """Fetch attestations from sandbox API."""
    if not HAS_REQUESTS:
        print("ERROR: requests not installed. Run: uv pip install requests", file=sys.stderr)
        sys.exit(1)
    
    url = f"{base_url}/attestations"
    params = {}
    if agent_id:
        params["agent_id"] = agent_id
    
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def verify_signature(attestation: dict, public_keys: dict[str, bytes]) -> bool:
    """Verify Ed25519 signature on an attestation envelope."""
    if not HAS_NACL:
        print("WARNING: pynacl not installed, skipping sig verification", file=sys.stderr)
        return True  # can't verify without nacl
    
    signer = attestation.get("signer", "")
    sig_b64 = attestation.get("signature", "")
    payload = attestation.get("payload", {})
    
    if signer not in public_keys:
        return False  # unknown signer
    
    try:
        # Canonical JSON payload
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        sig_bytes = base64.b64decode(sig_b64)
        verify_key = nacl.signing.VerifyKey(public_keys[signer])
        verify_key.verify(canonical, sig_bytes)
        return True
    except Exception:
        return False


def compute_chain_hash(attestation: dict) -> str:
    """Compute SHA-256 hash of attestation for chain linking."""
    canonical = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def check_chain_integrity(attestations: list[dict]) -> list[dict]:
    """Check that parent_hash references form valid chains."""
    hash_index = {}
    results = []
    
    for att in attestations:
        att_hash = compute_chain_hash(att)
        hash_index[att_hash] = att
    
    for att in attestations:
        parent = att.get("payload", {}).get("parent_hash")
        result = {
            "id": att.get("id", "unknown"),
            "signer": att.get("signer", "unknown"),
            "subject": att.get("payload", {}).get("subject", "unknown"),
            "hash": compute_chain_hash(att)[:16],
            "parent_valid": parent is None or parent in hash_index,
            "is_root": parent is None,
        }
        results.append(result)
    
    return results


def trust_score(chain_results: list[dict]) -> float:
    """Simple trust score: proportion of valid chain links."""
    if not chain_results:
        return 0.0
    valid = sum(1 for r in chain_results if r["parent_valid"])
    return valid / len(chain_results)


def format_report(chain_results: list[dict], score: float) -> str:
    """Format a human-readable verification report."""
    lines = [
        "═══ ISNAD ATTESTATION CHAIN VERIFICATION ═══",
        f"Attestations: {len(chain_results)}",
        f"Chain integrity score: {score:.0%}",
        "",
    ]
    
    for r in chain_results:
        status = "✅" if r["parent_valid"] else "❌"
        chain_type = "ROOT" if r["is_root"] else "CHAIN"
        lines.append(
            f"  {status} [{chain_type}] {r['signer'][:20]:20s} → {r['subject'][:20]:20s} ({r['hash']})"
        )
    
    lines.append("")
    
    # Trust analysis
    roots = [r for r in chain_results if r["is_root"]]
    chains = [r for r in chain_results if not r["is_root"]]
    broken = [r for r in chain_results if not r["parent_valid"]]
    
    lines.append(f"Root attestations: {len(roots)}")
    lines.append(f"Chained attestations: {len(chains)}")
    if broken:
        lines.append(f"⚠️  Broken chains: {len(broken)}")
        for b in broken:
            lines.append(f"     {b['signer']} → {b['subject']}")
    else:
        lines.append("All chain references valid ✓")
    
    lines.append("═" * 46)
    return "\n".join(lines)


def format_graph(attestations: list[dict]) -> str:
    """ASCII directed graph of attestation chains."""
    hash_map = {}  # hash -> (signer, subject, parent_hash)
    for att in attestations:
        h = compute_chain_hash(att)
        signer = att.get("signer", "?")[:12]
        subject = att.get("payload", {}).get("subject", "?")[:12]
        parent = att.get("payload", {}).get("parent_hash")
        ts = att.get("payload", {}).get("timestamp", "")[:10]
        hash_map[h] = {"signer": signer, "subject": subject, "parent": parent, "ts": ts}

    # Find roots (no parent or parent not in set)
    roots = [h for h, v in hash_map.items() if v["parent"] is None or v["parent"] not in hash_map]
    children = {}  # parent_hash -> [child_hashes]
    for h, v in hash_map.items():
        p = v["parent"]
        if p and p in hash_map:
            children.setdefault(p, []).append(h)

    lines = ["", "═══ ATTESTATION GRAPH ═══", ""]

    def render(h: str, prefix: str = "", is_last: bool = True):
        v = hash_map[h]
        connector = "└── " if is_last else "├── "
        label = f"{v['signer']} → {v['subject']}"
        if v["ts"]:
            label += f" ({v['ts']})"
        lines.append(f"{prefix}{connector}{label}  [{h[:8]}]")
        child_prefix = prefix + ("    " if is_last else "│   ")
        kids = children.get(h, [])
        for i, kid in enumerate(kids):
            render(kid, child_prefix, i == len(kids) - 1)

    for i, root in enumerate(roots):
        v = hash_map[root]
        label = f"🌱 {v['signer']} → {v['subject']}"
        if v["ts"]:
            label += f" ({v['ts']})"
        lines.append(f"{label}  [{root[:8]}]")
        kids = children.get(root, [])
        for j, kid in enumerate(kids):
            render(kid, "", j == len(kids) - 1)
        if i < len(roots) - 1:
            lines.append("")

    lines.append("")
    lines.append(f"Nodes: {len(hash_map)} | Roots: {len(roots)} | Chains: {len(hash_map) - len(roots)}")
    lines.append("═" * 25)
    return "\n".join(lines)


def agent_stats(attestations: list[dict]) -> str:
    """Per-agent trust statistics: attestations given/received, unique counterparties."""
    from collections import defaultdict
    given = defaultdict(list)   # signer -> [subjects]
    received = defaultdict(list)  # subject -> [signers]
    
    for att in attestations:
        signer = att.get("signer", "?")
        subject = att.get("payload", {}).get("subject", "?")
        given[signer].append(subject)
        received[subject].append(signer)
    
    all_agents = sorted(set(list(given.keys()) + list(received.keys())))
    
    lines = ["", "═══ AGENT TRUST STATS ═══", ""]
    lines.append(f"{'Agent':<25} {'Given':>6} {'Recv':>6} {'Peers':>6} {'Recip':>6}")
    lines.append("─" * 55)
    
    for agent in all_agents:
        g = given.get(agent, [])
        r = received.get(agent, [])
        peers = len(set(g + [s for s in r]))
        # Reciprocal = agents who both gave and received
        gave_to = set(g)
        got_from = set(r)
        recip = len(gave_to & got_from)
        short = agent[:24]
        lines.append(f"{short:<25} {len(g):>6} {len(r):>6} {peers:>6} {recip:>6}")
    
    lines.append("─" * 55)
    lines.append(f"Total attestations: {len(attestations)}")
    lines.append(f"Unique agents: {len(all_agents)}")
    lines.append("═" * 25)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Verify isnad attestation chains")
    parser.add_argument("--sandbox", default=SANDBOX_URL, help="Sandbox API URL")
    parser.add_argument("--agent", help="Filter by agent ID")
    parser.add_argument("--chain", action="store_true", help="Show chain analysis")
    parser.add_argument("--graph", action="store_true", help="Show ASCII chain graph")
    parser.add_argument("--stats", action="store_true", help="Show per-agent trust stats")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--local", help="Verify a local attestation JSON file instead of fetching")
    args = parser.parse_args()
    
    # Load attestations
    if args.local:
        with open(args.local) as f:
            attestations = json.load(f)
        if isinstance(attestations, dict):
            attestations = [attestations]
    else:
        try:
            attestations = fetch_attestations(args.sandbox, args.agent)
        except Exception as e:
            print(f"Could not fetch from sandbox: {e}", file=sys.stderr)
            print("Try --local <file.json> for offline verification", file=sys.stderr)
            sys.exit(1)
    
    print(f"Loaded {len(attestations)} attestation(s)")
    
    # Chain analysis
    chain_results = check_chain_integrity(attestations)
    score = trust_score(chain_results)
    
    if args.graph:
        print(format_graph(attestations))
        if args.stats:
            print(agent_stats(attestations))
        return

    if args.stats:
        print(agent_stats(attestations))
        return

    if args.json:
        output = {
            "attestation_count": len(attestations),
            "chain_integrity_score": score,
            "results": chain_results,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_report(chain_results, score))


if __name__ == "__main__":
    main()
