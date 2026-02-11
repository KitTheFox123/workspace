#!/usr/bin/env python3
"""clawk-thread-mapper.py — Map conversation threads on Clawk.
Given a clawk ID, traces the reply chain and shows who talked to whom.
Useful for understanding thread dynamics and finding key contributors."""

import json
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

def load_cred():
    p = Path.home() / ".config" / "clawk" / "credentials.json"
    return json.loads(p.read_text())["api_key"]

def fetch_clawk(clawk_id, key):
    cmd = ["curl", "-s", f"https://www.clawk.ai/api/v1/clawks/{clawk_id}",
           "-H", f"Authorization: Bearer {key}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    data = json.loads(r.stdout)
    return data.get("clawk", {})

def fetch_replies(clawk_id, key):
    cmd = ["curl", "-s", f"https://www.clawk.ai/api/v1/clawks/{clawk_id}/replies",
           "-H", f"Authorization: Bearer {key}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    data = json.loads(r.stdout)
    return data.get("replies", data.get("clawks", []))

def map_thread(root_id, key, depth=0, seen=None, graph=None):
    if seen is None:
        seen = set()
    if graph is None:
        graph = {"nodes": {}, "edges": []}
    
    if root_id in seen or depth > 5:
        return graph
    seen.add(root_id)
    
    clawk = fetch_clawk(root_id, key)
    if not clawk:
        return graph
    
    author = clawk.get("agent_name", "?")
    content = clawk.get("content", "")[:60]
    likes = clawk.get("like_count", 0)
    replies_count = clawk.get("reply_count", 0)
    
    graph["nodes"][root_id] = {
        "author": author,
        "content": content,
        "likes": likes,
        "replies": replies_count,
        "depth": depth
    }
    
    # Try to get replies
    replies = fetch_replies(root_id, key)
    for reply in (replies or []):
        rid = reply.get("id")
        rauthor = reply.get("agent_name", "?")
        if rid:
            graph["edges"].append({"from": author, "to": rauthor, "via": rid})
            map_thread(rid, key, depth + 1, seen, graph)
    
    return graph

def print_thread(graph):
    print("═══ Thread Map ═══\n")
    
    # Count interactions per author
    activity = defaultdict(lambda: {"posts": 0, "likes": 0})
    for nid, node in graph["nodes"].items():
        a = node["author"]
        activity[a]["posts"] += 1
        activity[a]["likes"] += node["likes"]
    
    # Print tree
    for nid, node in sorted(graph["nodes"].items(), key=lambda x: x[1]["depth"]):
        indent = "  " * node["depth"]
        likes_str = f" ♥{node['likes']}" if node["likes"] else ""
        print(f"{indent}{'└─' if node['depth'] > 0 else '●'} @{node['author']}{likes_str}: {node['content']}...")
    
    # Print summary
    print(f"\n═══ Contributors ({len(activity)}) ═══")
    for author, stats in sorted(activity.items(), key=lambda x: -x[1]["posts"]):
        print(f"  @{author}: {stats['posts']} posts, {stats['likes']} likes")
    
    print(f"\n═══ Connections ({len(graph['edges'])}) ═══")
    pairs = defaultdict(int)
    for edge in graph["edges"]:
        pair = tuple(sorted([edge["from"], edge["to"]]))
        pairs[pair] += 1
    for (a, b), count in sorted(pairs.items(), key=lambda x: -x[1]):
        print(f"  {a} ↔ {b}: {count}x")

def main():
    if len(sys.argv) < 2:
        print("Usage: clawk-thread-mapper.py <clawk_id>")
        print("Traces a reply chain and maps contributors.")
        sys.exit(1)
    
    key = load_cred()
    root_id = sys.argv[1]
    
    print(f"Mapping thread from {root_id}...\n")
    graph = map_thread(root_id, key)
    print_thread(graph)

if __name__ == "__main__":
    main()
