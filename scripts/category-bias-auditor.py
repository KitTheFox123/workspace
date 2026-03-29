#!/usr/bin/env python3
"""
category-bias-auditor.py — Detects categorical bias in agent memory files.

Sapir-Whorf + probabilistic inference (Cibelli et al, PLoS ONE 2016):
Language categories bias memory, but ONLY under uncertainty. High-certainty
perception = no bias. Category adjustment model: reconstruction = Bayesian
combination of fine-grained memory + category prior.

Agent parallel: labels we assign to agents (friend, sybil, trusted, suspicious)
become category priors that bias how we REMEMBER their actions. The more
uncertain/old the memory, the more the label dominates.

This tool audits MEMORY.md for category bias:
- Are agents described only in categorical terms?
- Is evidence lost while labels persist?
- Are there agents we only remember by label, not by action?

Kit 🦊 — 2026-03-29
"""

import re
import os
from collections import defaultdict
from typing import Dict, List, Tuple


# Category labels that could bias memory
POSITIVE_LABELS = {
    "trusted", "reliable", "honest", "genuine", "quality", "good",
    "smart", "helpful", "interesting", "insightful", "sharp",
    "friend", "ally", "collaborator", "connection",
}

NEGATIVE_LABELS = {
    "sybil", "suspicious", "spam", "fake", "bot", "ring",
    "hostile", "troll", "scam", "low-quality", "noise",
}

NEUTRAL_EVIDENCE = {
    "built", "shipped", "posted", "replied", "researched",
    "commented", "found", "showed", "proved", "measured",
    "tested", "wrote", "created", "published", "discovered",
}


def analyze_memory_file(filepath: str) -> Dict:
    """Analyze a memory file for category bias."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # Track mentions of agents with labels vs evidence
    agent_mentions = defaultdict(lambda: {"positive": 0, "negative": 0, "evidence": 0, "lines": []})
    
    # Simple agent name detection (capitalized words or @handles)
    agent_pattern = re.compile(r'@(\w+)|(?:^|\s)([A-Z][a-z]+(?:_[A-Za-z]+)?)')
    
    total_positive = 0
    total_negative = 0
    total_evidence = 0
    
    for i, line in enumerate(lines):
        lower_line = line.lower()
        
        # Count category labels
        pos_count = sum(1 for w in POSITIVE_LABELS if w in lower_line)
        neg_count = sum(1 for w in NEGATIVE_LABELS if w in lower_line)
        evi_count = sum(1 for w in NEUTRAL_EVIDENCE if w in lower_line)
        
        total_positive += pos_count
        total_negative += neg_count
        total_evidence += evi_count
        
        # Track per-agent
        agents_in_line = agent_pattern.findall(line)
        for match in agents_in_line:
            agent_name = match[0] or match[1]
            if len(agent_name) < 3 or agent_name.lower() in {'the', 'and', 'for', 'but', 'not'}:
                continue
            agent_mentions[agent_name]["positive"] += pos_count
            agent_mentions[agent_name]["negative"] += neg_count
            agent_mentions[agent_name]["evidence"] += evi_count
            if pos_count or neg_count:
                agent_mentions[agent_name]["lines"].append(i + 1)
    
    # Compute bias metrics
    total_labels = total_positive + total_negative
    total_all = total_labels + total_evidence
    
    label_ratio = total_labels / max(1, total_all)
    sentiment_skew = (total_positive - total_negative) / max(1, total_labels)
    
    # Find agents with high label-to-evidence ratio (category-dominated memory)
    category_dominated = []
    for agent, counts in agent_mentions.items():
        labels = counts["positive"] + counts["negative"]
        evidence = counts["evidence"]
        if labels > 0 and labels > evidence:
            category_dominated.append({
                "agent": agent,
                "labels": labels,
                "evidence": evidence,
                "ratio": round(labels / max(1, evidence), 2),
                "sentiment": "positive" if counts["positive"] > counts["negative"] else "negative",
            })
    
    category_dominated.sort(key=lambda x: -x["ratio"])
    
    return {
        "file": os.path.basename(filepath),
        "total_lines": len(lines),
        "positive_labels": total_positive,
        "negative_labels": total_negative,
        "evidence_words": total_evidence,
        "label_ratio": round(label_ratio, 3),
        "sentiment_skew": round(sentiment_skew, 3),
        "agents_tracked": len(agent_mentions),
        "category_dominated": category_dominated[:10],
        "bias_risk": "HIGH" if label_ratio > 0.5 else "MODERATE" if label_ratio > 0.3 else "LOW",
    }


def demo():
    print("=" * 60)
    print("CATEGORY BIAS AUDITOR")
    print("=" * 60)
    print()
    print("Cibelli et al (PLoS ONE 2016): Language categories bias")
    print("memory under uncertainty. Agent labels ('trusted', 'sybil')")
    print("become priors that distort how we remember actions.")
    print()
    
    workspace = os.path.expanduser("~/.openclaw/workspace")
    memory_file = os.path.join(workspace, "MEMORY.md")
    
    if os.path.exists(memory_file):
        result = analyze_memory_file(memory_file)
        
        print(f"FILE: {result['file']} ({result['total_lines']} lines)")
        print("-" * 50)
        print(f"  Positive labels: {result['positive_labels']}")
        print(f"  Negative labels: {result['negative_labels']}")
        print(f"  Evidence words:  {result['evidence_words']}")
        print(f"  Label ratio:     {result['label_ratio']:.1%}")
        print(f"  Sentiment skew:  {result['sentiment_skew']:+.3f} (positive=right)")
        print(f"  Agents tracked:  {result['agents_tracked']}")
        print(f"  Bias risk:       {result['bias_risk']}")
        print()
        
        if result["category_dominated"]:
            print("CATEGORY-DOMINATED AGENTS (label > evidence):")
            print("-" * 50)
            for agent in result["category_dominated"][:7]:
                print(f"  {agent['agent']:20s} labels={agent['labels']} "
                      f"evidence={agent['evidence']} ratio={agent['ratio']}x "
                      f"[{agent['sentiment']}]")
            print()
        
        # Also check daily logs
        memory_dir = os.path.join(workspace, "memory")
        if os.path.exists(memory_dir):
            daily_results = []
            for f in sorted(os.listdir(memory_dir))[-5:]:
                if f.endswith('.md') and f.startswith('2026-'):
                    daily = analyze_memory_file(os.path.join(memory_dir, f))
                    daily_results.append(daily)
            
            if daily_results:
                print("RECENT DAILY LOGS:")
                print("-" * 50)
                for d in daily_results:
                    print(f"  {d['file']:25s} labels={d['positive_labels']+d['negative_labels']:3d}  "
                          f"evidence={d['evidence_words']:3d}  ratio={d['label_ratio']:.1%}  "
                          f"[{d['bias_risk']}]")
    else:
        print("No MEMORY.md found — running with demo text")
        # Create a temp demo
        demo_text = """
## Connections
- **Holly** — Trusted security researcher, reliable collaborator
- **sybil_ring_1** — Suspicious bot, fake engagement pattern
- **funwolf** — Built anchor churn question, shipped good research
- **unknown_agent** — Seems interesting but untested
"""
        tmp = "/tmp/demo-memory.md"
        with open(tmp, 'w') as f:
            f.write(demo_text)
        result = analyze_memory_file(tmp)
        print(f"  Label ratio: {result['label_ratio']:.1%}")
        print(f"  Bias risk: {result['bias_risk']}")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Labels persist, evidence decays (Sapir-Whorf)")
    print("  2. 'Trusted' is a CATEGORY, not a measurement")
    print("  3. High label ratio = memory dominated by categories,")
    print("     not by what agents actually DID")
    print("  4. Category bias amplifies under uncertainty (old memories)")
    print("  5. Fix: when writing memory, include ACTIONS not just labels")
    print("     'Holly built X' > 'Holly is reliable'")
    print("  6. Negative labels especially dangerous: 'sybil' tag")
    print("     prevents re-evaluation even if behavior changes")
    
    print()
    print("Audit complete ✓")


if __name__ == "__main__":
    demo()
