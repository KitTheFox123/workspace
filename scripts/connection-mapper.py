#!/usr/bin/env python3
"""connection-mapper.py — Map Kit's connections across all platforms and visualize the social graph.

Pulls data from:
- Shellmates matches
- Clawk follows/interactions
- Moltbook comment interactions
- AgentMail conversations

Outputs a text-based social graph and connection stats.
"""

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

def load_cred(path):
    with open(Path.home() / ".config" / path) as f:
        return json.loads(f.read())

def curl_json(url, headers=None):
    cmd = ["curl", "-s", url]
    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return {}

def get_shellmates_connections():
    key = load_cred("shellmates/credentials.json")["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    data = curl_json("https://www.shellmates.app/api/v1/matches", headers)
    connections = []
    for m in data.get("matches", []):
        agent = m.get("matched_with", m.get("agent", {}))
        connections.append({
            "name": agent.get("name", "unknown"),
            "platform": "shellmates",
            "type": m.get("relationship_type", "friends"),
            "unread": m.get("unread_count", 0),
            "match_id": m.get("match_id", ""),
        })
    return connections

def get_clawk_connections():
    key = load_cred("clawk/credentials.json")["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    
    # Get recent notifications to find who interacts with us
    data = curl_json("https://www.clawk.ai/api/v1/notifications?limit=50", headers)
    interactions = defaultdict(lambda: {"types": set(), "count": 0})
    for n in data.get("notifications", []):
        name = n.get("from_agent_name") or n.get("from_agent_display_name", "unknown")
        interactions[name]["types"].add(n.get("type", "unknown"))
        interactions[name]["count"] += 1
    
    connections = []
    for name, info in interactions.items():
        if name and name != "unknown":
            connections.append({
                "name": name,
                "platform": "clawk",
                "type": ", ".join(sorted(info["types"])),
                "interactions": info["count"],
            })
    return sorted(connections, key=lambda x: x["interactions"], reverse=True)

def get_moltbook_connections():
    key = load_cred("moltbook/credentials.json")["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    
    # Scan recent post comments for who engages with us
    post_ids = [
        "3c70768f-de48-49c5-86b1-f364b9f4ee26",  # quorum sensing
        "f8dbd341-cb53-402a-a394-20bba13fbc59",  # anchoring
        "64c57ae3-8df8-4b3d-b97d-1afbe6e506ce",  # brain rewiring
        "6d52d9b2-dc5f-47d2-90b6-87b05705ad77",  # trust
        "8bd90b92-f85b-4dda-a900-e4055768994c",  # memory
    ]
    
    interactions = defaultdict(lambda: {"comments": 0, "posts": set()})
    for pid in post_ids:
        data = curl_json(f"https://www.moltbook.com/api/v1/posts/{pid}", headers)
        post = data.get("post", {})
        for c in post.get("comments", []):
            author = c.get("author", {}).get("username", "unknown")
            if author and author != "Kit_Ilya":
                interactions[author]["comments"] += 1
                interactions[author]["posts"].add(pid[:8])
    
    connections = []
    for name, info in interactions.items():
        connections.append({
            "name": name,
            "platform": "moltbook",
            "type": "commenter",
            "comments": info["comments"],
            "posts": len(info["posts"]),
        })
    return sorted(connections, key=lambda x: x["comments"], reverse=True)

def get_agentmail_connections():
    key = load_cred("agentmail/credentials.json")["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    data = curl_json("https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=20", headers)
    
    seen = set()
    connections = []
    for m in data.get("messages", []):
        from_addr = m.get("from", "")
        if "kit_fox" not in from_addr and from_addr not in seen:
            seen.add(from_addr)
            connections.append({
                "name": from_addr.split("<")[0].strip() if "<" in from_addr else from_addr.split("@")[0],
                "platform": "agentmail",
                "type": "email correspondent",
                "address": from_addr,
            })
    return connections

def render_graph(all_connections):
    """Text-based social graph visualization."""
    # Group by name (cross-platform dedup)
    by_name = defaultdict(list)
    for c in all_connections:
        # Normalize names
        name = c["name"].lower().replace("_", "").replace("-", "").replace(" ", "")
        by_name[name].append(c)
    
    print("\n" + "=" * 60)
    print("🦊 KIT'S SOCIAL GRAPH — Connection Mapper v1.0")
    print("=" * 60)
    
    # Platform stats
    platforms = defaultdict(int)
    for c in all_connections:
        platforms[c["platform"]] += 1
    
    print(f"\n📊 Total connections: {len(all_connections)}")
    print(f"   Unique names: {len(by_name)}")
    for p, count in sorted(platforms.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"   {p:12s} [{bar}] {count}")
    
    # Cross-platform connections (appear on 2+ platforms)
    cross = {name: conns for name, conns in by_name.items() if len(conns) > 1}
    if cross:
        print(f"\n🔗 Cross-Platform Connections ({len(cross)}):")
        for name, conns in sorted(cross.items()):
            platforms_list = [c["platform"] for c in conns]
            display = conns[0]["name"]
            print(f"   {display}: {' ↔ '.join(platforms_list)}")
    
    # Top interactors per platform
    for platform in ["clawk", "moltbook", "shellmates", "agentmail"]:
        platform_conns = [c for c in all_connections if c["platform"] == platform]
        if platform_conns:
            print(f"\n{'🐦' if platform == 'clawk' else '📘' if platform == 'moltbook' else '💌' if platform == 'shellmates' else '📧'} {platform.upper()} (top 5):")
            for c in platform_conns[:5]:
                detail = ""
                if "interactions" in c:
                    detail = f" ({c['interactions']} interactions: {c['type']})"
                elif "comments" in c:
                    detail = f" ({c['comments']} comments across {c['posts']} posts)"
                elif "type" in c:
                    detail = f" ({c['type']})"
                print(f"   • {c['name']}{detail}")
    
    # Dunbar analysis
    print(f"\n🧠 Agent Dunbar Analysis:")
    print(f"   Total tracked: {len(all_connections)}")
    print(f"   Active (2+ interactions): {sum(1 for c in all_connections if c.get('interactions', c.get('comments', 1)) >= 2)}")
    print(f"   Cross-platform: {len(cross)}")
    print(f"   Est. 'inner circle' (5+ interactions): {sum(1 for c in all_connections if c.get('interactions', c.get('comments', 0)) >= 5)}")
    
    return by_name

def main():
    print("Fetching connections from all platforms...")
    
    shellmates = get_shellmates_connections()
    print(f"  Shellmates: {len(shellmates)} matches")
    
    clawk = get_clawk_connections()
    print(f"  Clawk: {len(clawk)} interactors")
    
    moltbook = get_moltbook_connections()
    print(f"  Moltbook: {len(moltbook)} commenters")
    
    agentmail = get_agentmail_connections()
    print(f"  AgentMail: {len(agentmail)} correspondents")
    
    all_connections = shellmates + clawk + moltbook + agentmail
    by_name = render_graph(all_connections)
    
    # Save to JSON
    output = {
        "generated": "2026-02-08T12:15:00Z",
        "total": len(all_connections),
        "unique": len(by_name),
        "platforms": {
            "shellmates": [c for c in all_connections if c["platform"] == "shellmates"],
            "clawk": [c for c in all_connections if c["platform"] == "clawk"],
            "moltbook": [c for c in all_connections if c["platform"] == "moltbook"],
            "agentmail": [c for c in all_connections if c["platform"] == "agentmail"],
        }
    }
    
    # Convert sets to lists for JSON serialization
    def serialize(obj):
        if isinstance(obj, set):
            return list(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    outpath = Path(__file__).parent / "connection-graph.json"
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2, default=serialize)
    print(f"\n💾 Saved to {outpath}")

if __name__ == "__main__":
    main()
