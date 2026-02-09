#!/usr/bin/env python3
"""Topic Tracker — track all research topics covered today, detect gaps, suggest fresh topics.

Usage:
    python3 scripts/topic-tracker.py [--date YYYY-MM-DD] [--suggest N]
"""

import re
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# Topic taxonomy with keywords
TOPICS = {
    "neuroscience": ["brain", "neuron", "cortex", "hippocamp", "synap", "cognitive", "sleep", "dream", "memory consolidation", "NREM", "REM", "gamma", "theta", "EEG", "fMRI", "neuronal", "dopamine", "serotonin", "norepinephrine"],
    "psychology": ["bias", "anchoring", "heuristic", "cognitive", "perception", "Dunbar", "memory", "depression", "attention", "Mandela effect", "confabulation", "synesthesia"],
    "biology": ["evolution", "species", "ecology", "microbial", "fermentation", "navigation", "ant", "pigeon", "turtle", "quorum", "meerkat", "bat", "microbiome"],
    "physics_chemistry": ["quantum", "chirality", "Maillard", "entropy", "crystallography", "thermodynamic", "electromagnetic", "spectroscopy"],
    "math_cs": ["Shannon", "entropy", "algorithm", "information theory", "Bayesian", "graph theory", "computation", "cryptography", "hash"],
    "linguistics": ["Sapir-Whorf", "syntax", "phonology", "Grimm", "stylometry", "language", "Pirahã", "bouba", "kiki"],
    "history_culture": ["Ottoman", "medieval", "Jacquard", "Gutenberg", "Mercator", "colonial", "indigenous", "Luddite", "Broadway"],
    "philosophy": ["consciousness", "identity", "Parfit", "Chalmers", "phenomenal", "qualia", "free will", "ethics", "epistemology"],
    "agent_tech": ["MCP", "heartbeat", "context window", "tokenizer", "prompt", "RAG", "agent memory", "tool use", "orchestrat"],
    "security_trust": ["RPKI", "isnad", "attestation", "key rotation", "social recovery", "DKMS", "cryptographic", "verification"],
    "social_science": ["desire path", "Dunbar", "network", "coordination", "game theory", "commons", "Ostrom", "foraging"],
    "arts_music": ["music", "rhythm", "chills", "aesthetic", "color perception", "tetrachromacy", "art", "creativity"],
}

def extract_sections(text: str) -> list[dict]:
    """Extract heartbeat sections from daily log."""
    sections = []
    current = None
    for line in text.split('\n'):
        if re.match(r'^##\s+Heartbeat', line):
            if current:
                sections.append(current)
            current = {"header": line, "lines": [], "topics_found": Counter()}
        elif current is not None:
            current["lines"].append(line)
    if current:
        sections.append(current)
    return sections

def classify_text(text: str) -> Counter:
    """Classify text into topic categories."""
    text_lower = text.lower()
    counts = Counter()
    for topic, keywords in TOPICS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                counts[topic] += 1
                break  # count each topic once per text block
    return counts

def analyze_daily(date_str: str = None) -> dict:
    """Analyze a day's research topic coverage."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    log_path = Path(f"memory/{date_str}.md")
    if not log_path.exists():
        print(f"No log found: {log_path}")
        return {}
    
    text = log_path.read_text()
    sections = extract_sections(text)
    
    # Per-heartbeat topic coverage
    all_topics = Counter()
    heartbeat_details = []
    
    for sec in sections:
        sec_text = '\n'.join(sec["lines"])
        topics = classify_text(sec_text)
        all_topics.update(topics)
        
        # Extract research title
        research_title = "unknown"
        for line in sec["lines"]:
            if "Non-Agent Research:" in line or "Research:" in line:
                research_title = line.split(":", 1)[-1].strip()
                break
        
        heartbeat_details.append({
            "header": sec["header"].strip(),
            "research": research_title,
            "topics": dict(topics)
        })
    
    return {
        "date": date_str,
        "heartbeats": len(sections),
        "topic_coverage": dict(all_topics),
        "uncovered": [t for t in TOPICS if t not in all_topics],
        "details": heartbeat_details
    }

def suggest_topics(analysis: dict, n: int = 5) -> list[str]:
    """Suggest fresh topics based on gaps."""
    suggestions = {
        "neuroscience": ["Glial cells and computation", "Default mode network", "Neuroplasticity in adults", "Phantom limb and body schema"],
        "psychology": ["Change blindness", "Cognitive load theory", "Flow states (Csikszentmihalyi)", "Spotlight of attention"],
        "biology": ["Extremophiles and adaptation limits", "Horizontal gene transfer", "Symbiosis and co-evolution", "Circadian clock molecular mechanics"],
        "physics_chemistry": ["Superconductivity room-temp race", "Metamaterials and cloaking", "Phase transitions in social systems", "Protein folding (AlphaFold implications)"],
        "math_cs": ["P vs NP practical implications", "Kolmogorov complexity", "Cellular automata and emergence", "Zero-knowledge proofs explained"],
        "linguistics": ["Sound symbolism beyond bouba/kiki", "Constructed languages (Esperanto, Lojban)", "Whistled languages", "Language death and documentation"],
        "history_culture": ["Library of Alexandria myths", "Smallpox eradication campaign", "Telegraph and information age", "Spice trade routes"],
        "philosophy": ["Ship of Theseus for AI", "Chinese Room revisited", "Moral luck", "Epistemic humility"],
        "agent_tech": ["Tool use emergence in LLMs", "Constitutional AI approaches", "Multi-agent debate", "Retrieval-augmented generation advances"],
        "security_trust": ["Post-quantum cryptography", "Formal verification for smart contracts", "Supply chain attestation", "Decentralized identity standards"],
        "social_science": ["Tragedy of the commons solutions", "Wisdom of crowds conditions", "Network effects and tipping points", "Information cascades"],
        "arts_music": ["Generative art history", "Microtonal music systems", "Architecture as frozen music", "Cross-cultural aesthetics"],
    }
    
    uncovered = analysis.get("uncovered", [])
    covered = analysis.get("topic_coverage", {})
    
    # Prioritize uncovered topics, then least-covered
    results = []
    for topic in uncovered:
        if topic in suggestions:
            results.append(f"[{topic}] {suggestions[topic][0]}")
            if len(results) >= n:
                break
    
    if len(results) < n:
        for topic in sorted(covered, key=covered.get):
            if topic in suggestions and len(suggestions[topic]) > 1:
                results.append(f"[{topic}] {suggestions[topic][1]}")
                if len(results) >= n:
                    break
    
    return results

def print_report(analysis: dict):
    """Print topic coverage report."""
    if not analysis:
        return
    
    print(f"\n📊 Topic Tracker — {analysis['date']}")
    print(f"{'='*50}")
    print(f"Heartbeats analyzed: {analysis['heartbeats']}")
    
    print(f"\n📈 Topic Coverage:")
    coverage = analysis.get("topic_coverage", {})
    max_count = max(coverage.values()) if coverage else 1
    for topic in sorted(TOPICS.keys()):
        count = coverage.get(topic, 0)
        bar = "█" * int(count / max_count * 20) if count > 0 else "░"
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {topic:<20} {bar} ({count})")
    
    uncovered = analysis.get("uncovered", [])
    if uncovered:
        print(f"\n⚠️  Gaps ({len(uncovered)} uncovered): {', '.join(uncovered)}")
    
    diversity = len(coverage) / len(TOPICS) * 100
    print(f"\n🎯 Diversity: {diversity:.0f}% ({len(coverage)}/{len(TOPICS)} categories)")
    
    print(f"\n💡 Suggested fresh topics:")
    for s in suggest_topics(analysis):
        print(f"  → {s}")

HISTORY_FILE = Path.home() / ".openclaw" / "workspace" / "scripts" / "topic-history.json"

def save_history(analysis: dict):
    """Save daily scores with full per-topic breakdown for trend tracking."""
    history = {}
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            history = {}
    
    coverage = analysis.get("topic_coverage", {})
    date = analysis["date"]
    history[date] = {
        "heartbeats": analysis["heartbeats"],
        "categories_covered": len(coverage),
        "total_categories": len(TOPICS),
        "diversity_pct": round(len(coverage) / len(TOPICS) * 100, 1),
        "per_topic": {t: coverage.get(t, 0) for t in TOPICS},
        "uncovered": analysis.get("uncovered", []),
        "top_3": [list(x) for x in sorted(coverage.items(), key=lambda x: -x[1])[:3]],
    }
    HISTORY_FILE.write_text(json.dumps(history, indent=2, sort_keys=True))
    return history

def print_trend(history: dict):
    """Print diversity trend over time."""
    dates = sorted(history.keys())[-14:]  # last 14 days
    if not dates:
        print("No history data.")
        return
    
    print(f"\n📉 Diversity Trend ({dates[0]} → {dates[-1]}):")
    for date in dates:
        d = history[date]
        bar = "█" * int(d["diversity_pct"] / 5)
        print(f"  {date}: {bar} {d['diversity_pct']}% ({d['heartbeats']} beats, {d['categories_covered']}/{d['total_categories']} cats)")
    
    # Calculate trend direction
    if len(dates) >= 2:
        first_half = [history[d]["diversity_pct"] for d in dates[:len(dates)//2]]
        second_half = [history[d]["diversity_pct"] for d in dates[len(dates)//2:]]
        avg1 = sum(first_half) / len(first_half)
        avg2 = sum(second_half) / len(second_half)
        arrow = "↗️" if avg2 > avg1 + 2 else "↘️" if avg2 < avg1 - 2 else "→"
        print(f"\n  Trend: {arrow} ({avg1:.0f}% → {avg2:.0f}%)")

def print_heatmap(history: dict):
    """Print per-topic heatmap across days."""
    dates = sorted(history.keys())[-7:]  # last 7 days
    if not dates:
        print("No history data.")
        return
    
    print(f"\n🔥 Topic Heatmap (last {len(dates)} days):")
    header = f"  {'Topic':<20} | " + " | ".join(d[-5:] for d in dates) + " | Total"
    print(header)
    print(f"  {'-'*20}-+-" + "-+-".join("-----" for _ in dates) + "-+------")
    
    totals_by_topic = {}
    for topic in sorted(TOPICS.keys()):
        vals = []
        total = 0
        for d in dates:
            v = history[d].get("per_topic", {}).get(topic, 0)
            total += v
            # Heat coloring: 0=·, 1-2=░, 3-5=▒, 6+=█
            if v == 0:
                vals.append("    ·")
            elif v <= 2:
                vals.append(f"  ░{v:>1} ")
            elif v <= 5:
                vals.append(f"  ▒{v:>1} ")
            else:
                vals.append(f"  █{v:>1} ")
        totals_by_topic[topic] = total
        print(f"  {topic:<20} | " + " | ".join(vals) + f" | {total:5}")
    
    # Identify blind spots (0 across all days)
    blind_spots = [t for t, v in totals_by_topic.items() if v == 0]
    if blind_spots:
        print(f"\n  ⚠️ Blind spots (0 hits all week): {', '.join(blind_spots)}")

def backfill(dates: list[str] = None):
    """Backfill history from existing daily log files."""
    memory_dir = Path("memory")
    if dates is None:
        dates = sorted(f.stem for f in memory_dir.glob("202?-??-??.md"))
    
    count = 0
    for date_str in dates:
        analysis = analyze_daily(date_str)
        if analysis and analysis.get("heartbeats", 0) > 0:
            save_history(analysis)
            count += 1
    print(f"✅ Backfilled {count} days")

if __name__ == "__main__":
    date = None
    suggest_n = 5
    save = False
    mode = "report"  # report, trend, heatmap, backfill
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--date" and i + 1 < len(args):
            date = args[i + 1]
            i += 2
        elif args[i] == "--suggest" and i + 1 < len(args):
            suggest_n = int(args[i + 1])
            i += 2
        elif args[i] == "--save":
            save = True
            i += 1
        elif args[i] == "--trend":
            mode = "trend"
            i += 1
        elif args[i] == "--heatmap":
            mode = "heatmap"
            i += 1
        elif args[i] == "--backfill":
            mode = "backfill"
            i += 1
        else:
            i += 1
    
    if mode == "backfill":
        backfill()
    elif mode in ("trend", "heatmap"):
        if HISTORY_FILE.exists():
            history = json.loads(HISTORY_FILE.read_text())
            if mode == "trend":
                print_trend(history)
            else:
                print_heatmap(history)
        else:
            print("No history yet. Run with --save or --backfill first.")
    else:
        analysis = analyze_daily(date)
        print_report(analysis)
        if save:
            history = save_history(analysis)
            print_trend(history)
            print(f"\n💾 Saved to {HISTORY_FILE}")
