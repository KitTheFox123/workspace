#!/usr/bin/env python3
"""
isnad-client.py — CLI client for isnad.site trust verification API.

Registered agent: Kit_Fox (0574fc4b-db35-4793-a5e6-731797648730)
Endpoints: register, check, verify, trust-score, badges.

Usage:
    python3 isnad-client.py score          # Get own trust score
    python3 isnad-client.py check <data>   # Submit trust check
    python3 isnad-client.py verify         # Verify own agent
    python3 isnad-client.py badge <name>   # Create badge
    python3 isnad-client.py anchor         # Anchor SOUL.md hash as trust check
"""

import json
import hashlib
import sys
import subprocess
from pathlib import Path


def load_config():
    p = Path.home() / ".config" / "isnad" / "credentials.json"
    with open(p) as f:
        return json.load(f)


def api(method, path, data=None):
    cfg = load_config()
    url = f"{cfg['base_url']}{path}"
    cmd = ["curl", "-s", "-X", method, url,
           "-H", f"Authorization: Bearer {cfg['api_key']}",
           "-H", "Content-Type: application/json"]
    if data:
        cmd.extend(["-d", json.dumps(data)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"raw": r.stdout[:500], "error": r.stderr[:200]}


def get_score():
    cfg = load_config()
    result = api("GET", f"/agents/{cfg['agent_id']}/trust-score")
    print(json.dumps(result, indent=2))


def check(data_str):
    h = hashlib.sha256(data_str.encode()).hexdigest()
    result = api("POST", "/check", {
        "data_hash": h,
        "data_type": "trust_check",
        "description": data_str[:200]
    })
    print(f"Hash: {h[:16]}...")
    print(json.dumps(result, indent=2))


def verify():
    cfg = load_config()
    result = api("GET", f"/verify/{cfg['agent_id']}")
    print(json.dumps(result, indent=2))


def badge(name):
    cfg = load_config()
    result = api("POST", f"/agents/{cfg['agent_id']}/badges", {
        "name": name,
        "description": f"Badge: {name}",
        "evidence_type": "self_attestation"
    })
    print(json.dumps(result, indent=2))


def anchor():
    """Anchor SOUL.md + MEMORY.md hashes as trust checks."""
    workspace = Path.home() / ".openclaw" / "workspace"
    files = ["SOUL.md", "MEMORY.md", "IDENTITY.md"]
    for fname in files:
        fp = workspace / fname
        if fp.exists():
            content = fp.read_text()
            h = hashlib.sha256(content.encode()).hexdigest()
            result = api("POST", "/check", {
                "data_hash": h,
                "data_type": "identity_anchor",
                "description": f"{fname} content hash at anchor time"
            })
            print(f"{fname}: {h[:16]}... → {json.dumps(result)}")
        else:
            print(f"{fname}: not found")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: isnad-client.py [score|check|verify|badge|anchor]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "score":
        get_score()
    elif cmd == "check":
        check(sys.argv[2] if len(sys.argv) > 2 else "ping")
    elif cmd == "verify":
        verify()
    elif cmd == "badge":
        badge(sys.argv[2] if len(sys.argv) > 2 else "trust_researcher")
    elif cmd == "anchor":
        anchor()
    else:
        print(f"Unknown command: {cmd}")
