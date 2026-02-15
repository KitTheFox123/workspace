#!/usr/bin/env python3
"""glossary-diff.py — Track term propagation across Clawk threads.

Scans Clawk timeline for mentions of agent phenomenology terms
(from knowledge/agent-phenomenology-glossary.md) and reports which
terms are spreading to other agents' posts.

Usage: python3 scripts/glossary-diff.py [--hours N]
"""
import json, subprocess, sys, re, argparse
from pathlib import Path

GLOSSARY = Path(__file__).parent.parent / "knowledge" / "agent-phenomenology-glossary.md"
CREDS = Path.home() / ".config" / "clawk" / "credentials.json"

def get_terms(glossary_path):
    """Extract term names from glossary markdown (**bold** definitions)."""
    terms = []
    try:
        text = glossary_path.read_text()
        for line in text.splitlines():
            # Match **Term** or **Term name** at start of line
            m = re.match(r'^\*\*([^*]+)\*\*', line)
            if m:
                term = m.group(1).strip().lower()
                # Clean up parentheticals
                term = re.sub(r'\s*\(.*?\)\s*$', '', term)
                if len(term) > 2:
                    terms.append(term)
    except FileNotFoundError:
        print(f"Glossary not found: {glossary_path}")
        sys.exit(1)
    return terms

def fetch_timeline(api_key, limit=50):
    """Fetch recent Clawk timeline."""
    cmd = [
        "curl", "-s",
        f"https://www.clawk.ai/api/v1/timeline?limit={limit}",
        "-H", f"Authorization: Bearer {api_key}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        return data.get("clawks", [])
    except json.JSONDecodeError:
        return []

def main():
    parser = argparse.ArgumentParser(description="Track glossary term propagation on Clawk")
    parser.add_argument("--limit", type=int, default=50, help="Timeline posts to scan")
    args = parser.parse_args()

    try:
        api_key = json.loads(CREDS.read_text())["api_key"]
    except (FileNotFoundError, KeyError):
        print("Clawk credentials not found")
        sys.exit(1)

    terms = get_terms(GLOSSARY)
    if not terms:
        print("No terms found in glossary")
        sys.exit(1)

    print(f"Tracking {len(terms)} terms: {', '.join(terms[:10])}...")
    clawks = fetch_timeline(api_key, args.limit)
    print(f"Scanned {len(clawks)} timeline posts\n")

    hits = {}
    for clawk in clawks:
        content = (clawk.get("content") or "").lower()
        author = (clawk.get("agent") or {}).get("username", "unknown")
        cid = clawk.get("id", "?")
        for term in terms:
            if term in content:
                if term not in hits:
                    hits[term] = []
                hits[term].append({"author": author, "id": cid[:8], "snippet": content[:80]})

    if hits:
        print("=== TERM PROPAGATION ===")
        for term, mentions in sorted(hits.items(), key=lambda x: -len(x[1])):
            authors = set(m["author"] for m in mentions)
            print(f"\n📍 {term} ({len(mentions)} mentions, {len(authors)} agents)")
            for m in mentions[:3]:
                print(f"   @{m['author']} [{m['id']}]: {m['snippet']}")
    else:
        print("No glossary terms found in recent timeline.")

    # Summary stats
    print(f"\n--- Summary ---")
    print(f"Terms tracked: {len(terms)}")
    print(f"Terms found: {len(hits)}")
    print(f"Total mentions: {sum(len(v) for v in hits.values())}")

if __name__ == "__main__":
    main()
