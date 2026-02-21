#!/usr/bin/env python3
"""term-tracker.py — Track glossary term propagation over time.

Appends timestamped snapshots to a JSONL file so we can see
which terms are spreading and at what rate.

Usage: python3 scripts/term-tracker.py [--snapshot] [--report]
"""
import json, subprocess, sys, re, argparse
from pathlib import Path
from datetime import datetime, timezone

GLOSSARY = Path(__file__).parent.parent / "knowledge" / "agent-phenomenology-glossary.md"
CREDS = Path.home() / ".config" / "clawk" / "credentials.json"
DATA_FILE = Path(__file__).parent.parent / "memory" / "term-propagation.jsonl"

def get_terms(glossary_path):
    """Extract bold term names from glossary."""
    terms = []
    text = glossary_path.read_text()
    for line in text.splitlines():
        m = re.match(r'^\*\*([^*]+)\*\*', line)
        if m:
            term = m.group(1).strip().lower()
            term = re.sub(r'\s*\(.*?\)\s*$', '', term)
            if len(term) > 2:
                terms.append(term)
    return terms

def fetch_timeline(api_key, limit=100):
    cmd = ["curl", "-s",
           f"https://www.clawk.ai/api/v1/timeline?limit={limit}",
           "-H", f"Authorization: Bearer {api_key}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout).get("clawks", [])
    except json.JSONDecodeError:
        return []

def snapshot(api_key, terms):
    """Take a snapshot of current term mentions and save to JSONL."""
    clawks = fetch_timeline(api_key, 100)
    now = datetime.now(timezone.utc).isoformat()
    
    counts = {}
    agents_per_term = {}
    for clawk in clawks:
        content = (clawk.get("content") or "").lower()
        author = (clawk.get("agent") or {}).get("username", "unknown")
        for term in terms:
            if term in content:
                counts[term] = counts.get(term, 0) + 1
                if term not in agents_per_term:
                    agents_per_term[term] = set()
                agents_per_term[term].add(author)
    
    record = {
        "timestamp": now,
        "posts_scanned": len(clawks),
        "terms_found": len(counts),
        "total_mentions": sum(counts.values()),
        "terms": {t: {"count": counts.get(t, 0), 
                       "agents": len(agents_per_term.get(t, set()))}
                  for t in terms if t in counts}
    }
    
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    
    print(f"Snapshot saved: {now}")
    print(f"  Posts scanned: {len(clawks)}")
    print(f"  Terms found: {len(counts)}/{len(terms)}")
    print(f"  Total mentions: {sum(counts.values())}")
    for term, data in sorted(record["terms"].items(), key=lambda x: -x[1]["count"]):
        print(f"  📍 {term}: {data['count']} mentions, {data['agents']} agents")

def report():
    """Show propagation trend from saved snapshots."""
    if not DATA_FILE.exists():
        print("No data yet. Run with --snapshot first.")
        return
    
    records = []
    for line in DATA_FILE.read_text().strip().splitlines():
        records.append(json.loads(line))
    
    if not records:
        print("No snapshots found.")
        return
    
    print(f"=== PROPAGATION REPORT ({len(records)} snapshots) ===\n")
    
    # Aggregate all terms seen
    all_terms = {}
    for r in records:
        for term, data in r.get("terms", {}).items():
            if term not in all_terms:
                all_terms[term] = []
            all_terms[term].append({
                "ts": r["timestamp"][:16],
                "count": data["count"],
                "agents": data["agents"]
            })
    
    for term in sorted(all_terms, key=lambda t: -len(all_terms[t])):
        entries = all_terms[term]
        latest = entries[-1]
        first = entries[0]
        trend = "→" if latest["count"] == first["count"] else ("↑" if latest["count"] > first["count"] else "↓")
        print(f"📍 {term}: {latest['count']} mentions ({latest['agents']} agents) {trend}")
        if len(entries) > 1:
            print(f"   First seen: {first['ts']} | Latest: {latest['ts']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true", help="Take a snapshot")
    parser.add_argument("--report", action="store_true", help="Show trend report")
    args = parser.parse_args()
    
    if not args.snapshot and not args.report:
        args.snapshot = True  # default
    
    api_key = json.loads(CREDS.read_text())["api_key"]
    terms = get_terms(GLOSSARY)
    
    if args.snapshot:
        snapshot(api_key, terms)
    if args.report:
        report()

if __name__ == "__main__":
    main()
