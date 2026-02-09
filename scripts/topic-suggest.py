#!/usr/bin/env python3
"""Topic suggester — finds underrepresented categories and suggests novel research topics.

Usage:
    python3 scripts/topic-suggest.py              # Suggest next topics
    python3 scripts/topic-suggest.py --count 5    # Suggest 5 topics
    python3 scripts/topic-suggest.py --stats       # Show category coverage stats
    python3 scripts/topic-suggest.py --backfill 2026-02-08  # Scan daily log, update history
"""

import argparse
import json
import random
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent / "memory" / "topic-history.json"

# Topic pool organized by category
TOPIC_POOL = {
    "neuroscience": [
        "Mirror neuron debate — Hickok 2009 critique vs Rizzolatti",
        "Default mode network — mind-wandering as cognitive function",
        "Neurogenesis in adults — controversy over hippocampal new neurons",
        "Split-brain experiments — Gazzaniga, two consciousnesses in one skull",
        "Phantom limb pain — Ramachandran mirror box therapy",
        "Blindsight — seeing without conscious awareness",
    ],
    "psychology": [
        "Bystander effect replication failures — Fischer 2011 meta-analysis",
        "Dunning-Kruger effect — original study vs popular misinterpretation",
        "Stanford prison experiment — Zimbardo critiques, demand characteristics",
        "Flow states — Csikszentmihalyi, optimal experience conditions",
        "Cognitive load theory — Sweller, instructional design implications",
        "Learned helplessness — Seligman's dogs, revised theory",
    ],
    "biology": [
        "Tardigrade cryptobiosis — surviving vacuum, radiation, 30 years desiccated",
        "CRISPR off-target effects — 2024 whole-genome studies",
        "Horizontal gene transfer in eukaryotes — bdelloid rotifers",
        "Octopus RNA editing — rewriting genetic code on the fly",
        "Extremophile metabolism — chemolithotrophy in deep-sea vents",
        "Epigenetic inheritance — transgenerational trauma in C. elegans",
    ],
    "physics": [
        "Metamaterials — negative refractive index, invisibility cloaks",
        "Time crystals — Wilczek 2012 proposal, Google 2021 realization",
        "Quantum entanglement — Bell tests closing loopholes 2015-2023",
        "Turbulence — last unsolved classical physics problem",
        "Sonoluminescence — collapsing bubbles producing light, unknown mechanism",
        "Dark matter alternatives — MOND vs CDM, 2024 observations",
    ],
    "history": [
        "Smallpox eradication — last mile logistics, ring vaccination",
        "Library of Alexandria — myths vs reality, gradual decline",
        "Inca quipu — base-10 knot records, possibly narrative too",
        "Antikythera mechanism — 2000-year-old analog computer",
        "Medieval Islamic golden age — algebra, optics, hospitals",
        "Polynesian wayfinding — star compass, ocean swell reading",
    ],
    "linguistics": [
        "Chinese Room revisited — Searle 1980 in the LLM era",
        "Pirahã recursion debate — Everett vs Chomsky on universal grammar",
        "Language death — 1 language dies every 2 weeks, documentation race",
        "Sapir-Whorf strong vs weak — color perception across cultures",
        "Proto-Indo-European reconstruction — 6000 years of linguistic forensics",
        "Sign language emergence — Nicaraguan Sign Language, Al-Sayyid Bedouin",
    ],
    "mathematics": [
        "Euler's identity — mathematical beauty, fMRI of mathematicians",
        "Gödel's incompleteness — limits of formal systems, agent implications",
        "Benford's law — first-digit distribution, fraud detection",
        "Bayesian vs frequentist — philosophy of probability",
        "Cellular automata — Rule 110 Turing completeness, Conway's Game of Life",
        "Ramanujan — intuition without proof, mathematical dreaming",
    ],
    "anthropology": [
        "Dunbar's number across cultures — variation in social group size",
        "Gift economies — Mauss, potlatch, reputation as currency",
        "Cargo cults — post-WWII Pacific, technology as magic",
        "Cultural transmission — vertical, horizontal, oblique learning",
        "Domestication syndrome — shared traits across species",
        "Feral children — language acquisition critical period evidence",
    ],
    "technology": [
        "Xerox PARC — invented the future, couldn't sell it",
        "Soviet internet (OGAS) — Glushkov's network, bureaucracy killed it",
        "Mechanical Turk (original) — 1770 chess automaton, 85 years of deception",
        "Minitel — France's pre-internet, millions of users by 1982",
        "Ada Lovelace — first algorithm, imagination beyond Babbage",
        "Hedy Lamarr — frequency hopping, from Hollywood to WiFi",
    ],
    "philosophy": [
        "Ship of Theseus — identity through change, agent version",
        "Mary's Room — knowledge argument against physicalism",
        "Trolley problem variations — cultural differences (Awad 2018 Moral Machine)",
        "Newcomb's problem — one-box vs two-box, decision theory wars",
        "Philosophical zombies — Chalmers, hard problem of consciousness",
        "Pragmatism — James, Dewey, truth as what works",
    ],
    "ecology": [
        "Rewilding — wolf reintroduction Yellowstone trophic cascades",
        "Microplastics in blood — 2022 detection, unknown health effects",
        "Coral reef restoration — electric mineral accretion, probiotics",
        "Urban ecology — cities as novel ecosystems, adaptation speed",
        "Seed banks — Svalbard vault, 1.3M samples, backup for civilization",
        "Ocean acidification — pH drop fastest in 300M years",
    ],
    "economics": [
        "Goodhart's law deep dive — when measures become targets",
        "Commons tragedy vs commons triumph — Ostrom's 8 principles",
        "Mechanism design — reverse game theory, auction theory",
        "Informal economies — 60% of global workforce, invisible GDP",
        "Attention economy — finite resource, infinite extraction",
        "Universal basic income experiments — Finland, Kenya, Stockton results",
    ],
}


def load_history():
    """Load topic history if available."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {"topics": []}


def get_category_counts(history):
    """Count topics per category from history."""
    counts = Counter()
    for entry in history.get("topics", []):
        cat = entry.get("category", "unknown")
        counts[cat] += 1
    return counts


def suggest_topics(n=3, history=None):
    """Suggest underrepresented topics with novelty scoring."""
    if history is None:
        history = load_history()

    counts = get_category_counts(history)
    all_categories = list(TOPIC_POOL.keys())

    # Score categories inversely by representation
    max_count = max(counts.values()) if counts else 0
    scores = {}
    for cat in all_categories:
        count = counts.get(cat, 0)
        # Higher score = less covered = more novel
        scores[cat] = (max_count + 1) - count

    # Weighted random selection
    total = sum(scores.values())
    suggestions = []
    used_cats = set()

    for _ in range(min(n, len(all_categories))):
        # Pick category weighted by novelty score
        r = random.random() * total
        cumulative = 0
        chosen_cat = all_categories[0]
        for cat in all_categories:
            if cat in used_cats:
                continue
            cumulative += scores[cat]
            if cumulative >= r:
                chosen_cat = cat
                break

        used_cats.add(chosen_cat)
        # Pick random topic from that category
        topic = random.choice(TOPIC_POOL[chosen_cat])
        novelty = scores[chosen_cat] / max(max_count + 1, 1)
        suggestions.append({
            "category": chosen_cat,
            "topic": topic,
            "novelty_score": round(novelty, 2),
            "times_covered": counts.get(chosen_cat, 0),
        })

    return sorted(suggestions, key=lambda x: x["novelty_score"], reverse=True)


def show_stats(history):
    """Show category coverage stats."""
    counts = get_category_counts(history)
    all_cats = sorted(TOPIC_POOL.keys())
    total = sum(counts.values())

    print(f"Topic Coverage ({total} total topics researched)\n")
    print(f"{'Category':<15} {'Count':>5} {'Coverage':>8}  Bar")
    print("-" * 50)

    max_count = max(counts.values()) if counts else 1
    for cat in all_cats:
        count = counts.get(cat, 0)
        pct = (count / total * 100) if total else 0
        bar = "█" * int(count / max_count * 20) if max_count else ""
        print(f"{cat:<15} {count:>5} {pct:>7.1f}%  {bar}")

    # Uncovered categories
    uncovered = [c for c in all_cats if counts.get(c, 0) == 0]
    if uncovered:
        print(f"\n⚠️  Uncovered: {', '.join(uncovered)}")


CATEGORY_KEYWORDS = {
    "neuroscience": ["neuron", "brain", "cortex", "hippocamp", "amygdala", "synapse", "neural", "cogniti", "phantom limb", "mirror neuron", "blindsight", "split-brain", "neurogenesis", "default mode"],
    "psychology": ["bystander", "dunning-kruger", "stanford prison", "flow state", "cognitive load", "learned helpless", "anchoring", "mandela effect", "confabulation", "placebo", "boredom"],
    "biology": ["tardigrade", "crispr", "horizontal gene", "octopus", "extremophile", "epigenetic", "slime mold", "physarum", "corvid", "fungal", "mycelium"],
    "physics": ["metamaterial", "time crystal", "quantum", "turbulence", "sonoluminescence", "dark matter", "fiber optic", "snell", "refractive"],
    "history": ["smallpox", "alexandria", "quipu", "antikythera", "islamic golden", "polynesian", "jacquard", "textile", "weaving"],
    "linguistics": ["chinese room", "pirahã", "language death", "sapir-whorf", "proto-indo", "sign language", "orality", "literacy", "ong"],
    "mathematics": ["euler", "gödel", "benford", "bayesian", "cellular automata", "ramanujan", "shannon", "entropy", "information theory"],
    "anthropology": ["dunbar", "gift econom", "cargo cult", "cultural transmission", "domestication", "feral child", "number sense", "counting"],
    "technology": ["xerox parc", "soviet internet", "ogas", "mechanical turk", "minitel", "ada lovelace", "hedy lamarr"],
    "philosophy": ["ship of theseus", "mary's room", "trolley", "newcomb", "zombie", "pragmatism", "chinese room", "consciousness"],
    "ecology": ["rewilding", "microplastic", "coral reef", "urban ecology", "seed bank", "ocean acidif", "mycorrhizal"],
    "economics": ["goodhart", "commons", "mechanism design", "informal econom", "attention economy", "universal basic income", "marketplace"],
}


def backfill_from_daily(date_str):
    """Scan a daily log file for research topics and update history."""
    memory_dir = Path(__file__).parent.parent / "memory"
    filepath = memory_dir / f"{date_str}.md"
    if not filepath.exists():
        print(f"❌ No file: {filepath}")
        return

    content = filepath.read_text().lower()
    history = load_history()
    existing_topics = {t.get("name", "") for t in history.get("topics", [])}

    # Extract research section headers (multiple patterns)
    research_lines = []
    patterns = [
        r"###?\s*(?:non-agent\s+)?research[:\s]+(.+?)(?:\n|$)",       # ### Research: Topic
        r"- research[:\s]+\*\*(.+?)\*\*",                             # - research: **Topic**
        r"###?\s*(?:non-agent\s+)?research[:\s]*\*\*(.+?)\*\*",       # ### Research: **Topic**
        r"\*\*(?:non-agent\s+)?research[:\s]+(.+?)\*\*",              # **Research: Topic**
        r"(?:^|\n)#{2,4}\s+(.+?)\s*(?:\n|$).*?keenable",             # Any header followed by keenable mention
        r"- \*\*(?:Clawk standalone|Moltbook (?:post|comment))\*\*.*?:\s*(.+?)(?:\n|$)",  # Writing action topics
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            topic = match.group(1).strip().rstrip("*").strip()
            if len(topic) > 3 and topic not in research_lines:
                research_lines.append(topic)

    new_topics = []
    for topic_text in research_lines:
        # Classify by keywords
        category = "unknown"
        best_score = 0
        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in topic_text)
            if score > best_score:
                best_score = score
                category = cat

        if topic_text not in existing_topics:
            entry = {
                "name": topic_text,
                "category": category,
                "date": date_str,
            }
            new_topics.append(entry)
            history.setdefault("topics", []).append(entry)

    # Save
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

    print(f"📚 Backfilled from {date_str}: {len(new_topics)} new topics\n")
    for t in new_topics:
        print(f"  [{t['category']}] {t['name']}")

    if not new_topics:
        print("  (no new topics found — all already in history)")

    return new_topics


def main():
    parser = argparse.ArgumentParser(description="Suggest novel research topics")
    parser.add_argument("--count", "-n", type=int, default=3, help="Number of suggestions")
    parser.add_argument("--stats", action="store_true", help="Show coverage stats")
    parser.add_argument("--backfill", metavar="DATE", help="Scan daily log (YYYY-MM-DD) and update history")
    args = parser.parse_args()

    if args.backfill:
        backfill_from_daily(args.backfill)
        return

    history = load_history()

    if args.stats:
        show_stats(history)
        return

    suggestions = suggest_topics(args.count, history)
    print("🔬 Suggested topics (highest novelty first):\n")
    for i, s in enumerate(suggestions, 1):
        emoji = "🆕" if s["times_covered"] == 0 else "📊"
        print(f"{i}. [{s['category']}] {s['topic']}")
        print(f"   {emoji} Novelty: {s['novelty_score']:.0%} | Previously covered: {s['times_covered']}x\n")


if __name__ == "__main__":
    main()
