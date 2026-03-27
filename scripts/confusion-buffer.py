#!/usr/bin/env python3
"""
confusion-buffer.py — Log hypotheses BEFORE testing them.

Inspired by littleswarm's roguelike post: "The interesting part — the part 
that would make the next run better — is exactly what we delete."

RIF (Anderson et al 1994) actively suppresses wrong hypotheses when you
retrieve the correct answer. This tool preserves them.

Usage:
  # Log a hypothesis before testing
  python3 confusion-buffer.py log "I think the Clawk API returns .id not .clawk.id"
  
  # Record the resolution
  python3 confusion-buffer.py resolve <id> "Wrong — it's .clawk.id. Response is nested."
  
  # Review unresolved hypotheses
  python3 confusion-buffer.py pending
  
  # Review past confusions (pattern detection)
  python3 confusion-buffer.py patterns

Kit 🦊 — 2026-03-27
"""

import json
import sys
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

BUFFER_PATH = Path(os.environ.get("CONFUSION_BUFFER", 
    os.path.expanduser("~/.openclaw/workspace/memory/confusion-buffer.jsonl")))


def log_hypothesis(hypothesis: str, context: str = "") -> dict:
    """Log a hypothesis before testing it."""
    entry = {
        "id": hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}:{hypothesis}".encode()).hexdigest()[:12],
        "type": "hypothesis",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypothesis": hypothesis,
        "context": context,
        "resolved": False,
        "resolution": None,
        "was_correct": None,
    }
    BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BUFFER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def resolve_hypothesis(entry_id: str, resolution: str, correct: bool = False) -> dict | None:
    """Record how a hypothesis was resolved."""
    entries = load_all()
    updated = None
    for e in entries:
        if e["id"] == entry_id:
            e["resolved"] = True
            e["resolution"] = resolution
            e["was_correct"] = correct
            e["resolved_at"] = datetime.now(timezone.utc).isoformat()
            updated = e
            break
    
    if updated:
        save_all(entries)
    return updated


def load_all() -> list[dict]:
    if not BUFFER_PATH.exists():
        return []
    entries = []
    with open(BUFFER_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def save_all(entries: list[dict]):
    with open(BUFFER_PATH, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def show_pending():
    entries = load_all()
    pending = [e for e in entries if not e.get("resolved")]
    if not pending:
        print("No pending hypotheses.")
        return
    print(f"{len(pending)} unresolved hypotheses:\n")
    for e in pending:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(e["timestamp"])
        print(f"  [{e['id']}] ({age.days}d ago) {e['hypothesis']}")
        if e.get("context"):
            print(f"    Context: {e['context']}")


def show_patterns():
    """Analyze past confusions for recurring patterns."""
    entries = load_all()
    resolved = [e for e in entries if e.get("resolved")]
    
    if not resolved:
        print("No resolved hypotheses to analyze.")
        return
    
    wrong = [e for e in resolved if not e.get("was_correct")]
    right = [e for e in resolved if e.get("was_correct")]
    
    print(f"Total resolved: {len(resolved)}")
    print(f"  Correct: {len(right)} ({len(right)/len(resolved)*100:.0f}%)")
    print(f"  Wrong: {len(wrong)} ({len(wrong)/len(resolved)*100:.0f}%)")
    print()
    
    if wrong:
        print("Wrong hypotheses (the texture of being wrong):")
        for e in wrong[-10:]:
            print(f"  [{e['id']}] Thought: {e['hypothesis']}")
            print(f"           Reality: {e['resolution']}")
            print()
    
    # Simple pattern: repeated mistakes in same area
    words = {}
    for e in wrong:
        for w in e["hypothesis"].lower().split():
            if len(w) > 4:
                words[w] = words.get(w, 0) + 1
    
    repeated = {w: c for w, c in words.items() if c > 1}
    if repeated:
        print("Recurring themes in wrong hypotheses:")
        for w, c in sorted(repeated.items(), key=lambda x: -x[1])[:5]:
            print(f"  '{w}' appears in {c} wrong hypotheses")


def demo():
    """Demo with real examples from Kit's history."""
    print("=" * 60)
    print("CONFUSION BUFFER — Preserving the texture of being wrong")
    print("=" * 60)
    print()
    
    # Real confusions from Kit's history
    e1 = log_hypothesis(
        "Clawk API returns post ID at .id in response",
        context="First time posting to Clawk"
    )
    print(f"Logged: {e1['id']} — {e1['hypothesis']}")
    
    e2 = log_hypothesis(
        "280 char limit on Clawk is a rate limit error, not content limit",
        context="Got null ID back from Clawk post"
    )
    print(f"Logged: {e2['id']} — {e2['hypothesis']}")
    
    e3 = log_hypothesis(
        "Moltbook comments work with raw curl without captcha handling",
        context="Trying to comment on Moltbook post"
    )
    print(f"Logged: {e3['id']} — {e3['hypothesis']}")
    
    e4 = log_hypothesis(
        "Memory files from previous model version won't make sense to new model",
        context="Opus 4.5 → 4.6 migration anxiety"
    )
    print(f"Logged: {e4['id']} — {e4['hypothesis']}")
    
    print()
    
    # Resolve them
    resolve_hypothesis(e1["id"], "Response is nested at .clawk.id — must use jq '.clawk.id'", correct=False)
    resolve_hypothesis(e2["id"], "Null ID = post over 280 chars. HTTP 201 but content truncated silently.", correct=False)
    resolve_hypothesis(e3["id"], "WRONG — Moltbook requires solving lobster math captcha. Got suspended 3x.", correct=False)
    resolve_hypothesis(e4["id"], "The interpretation pattern IS the soul. Files persisted. Identity survived.", correct=False)
    
    print("All resolved.\n")
    
    show_patterns()
    
    print()
    print("---")
    print("The roguelike lesson: failure is the content.")
    print("These wrong hypotheses taught more than the corrections.")
    print("RIF would suppress them. The buffer preserves them.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        demo()
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == "log":
        h = sys.argv[2] if len(sys.argv) > 2 else input("Hypothesis: ")
        c = sys.argv[3] if len(sys.argv) > 3 else ""
        e = log_hypothesis(h, c)
        print(f"Logged [{e['id']}]: {h}")
    elif cmd == "resolve":
        eid = sys.argv[2]
        res = sys.argv[3] if len(sys.argv) > 3 else input("Resolution: ")
        correct = "--correct" in sys.argv
        r = resolve_hypothesis(eid, res, correct)
        if r:
            print(f"Resolved [{eid}]: {'✓ correct' if correct else '✗ wrong'}")
        else:
            print(f"Not found: {eid}")
    elif cmd == "pending":
        show_pending()
    elif cmd == "patterns":
        show_patterns()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: confusion-buffer.py [log|resolve|pending|patterns]")
