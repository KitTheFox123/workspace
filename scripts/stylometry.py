#!/usr/bin/env python3
"""
stylometry.py — Analyze Kit's writing style across platforms.
Detects consistency or drift between Clawk, Moltbook, and Shellmates.

Features analyzed:
- Function word frequencies (the, of, to, and, a, in, is, it, that, for...)
- Character n-grams (2-gram and 3-gram profiles)
- Sentence length distribution
- Vocabulary richness (type-token ratio, hapax legomena ratio)
- Punctuation patterns (dashes, colons, periods, exclamation marks)
- Word length distribution
- Average sentence length

Based on: Cammarota et al. 2024 (PMC11707938), Mosteller & Wallace 1963
"""

import json
import re
import sys
import os
import math
from collections import Counter
from pathlib import Path

# Top 50 English function words (Mosteller & Wallace style)
FUNCTION_WORDS = [
    'the', 'of', 'to', 'and', 'a', 'in', 'is', 'it', 'that', 'for',
    'was', 'on', 'are', 'with', 'as', 'but', 'be', 'this', 'not', 'by',
    'from', 'or', 'an', 'at', 'which', 'have', 'has', 'had', 'they', 'you',
    'we', 'can', 'been', 'if', 'more', 'when', 'will', 'would', 'who', 'so',
    'no', 'its', 'my', 'than', 'do', 'just', 'about', 'what', 'all', 'how'
]

def tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r"[a-zA-Z']+", text.lower())

def sentences(text: str) -> list[str]:
    """Split text into sentences."""
    return [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 3]

def char_ngrams(text: str, n: int) -> Counter:
    """Extract character n-grams."""
    text = text.lower()
    return Counter(text[i:i+n] for i in range(len(text) - n + 1))

def analyze_text(text: str, label: str = "unknown") -> dict:
    """Compute stylometric features for a text."""
    words = tokenize(text)
    sents = sentences(text)
    
    if not words or not sents:
        return {"label": label, "error": "insufficient text"}
    
    total_words = len(words)
    word_counts = Counter(words)
    types = len(word_counts)
    
    # Function word frequencies (per 1000 words)
    fw_freq = {}
    for fw in FUNCTION_WORDS:
        fw_freq[fw] = (word_counts.get(fw, 0) / total_words) * 1000
    
    # Vocabulary richness
    ttr = types / total_words  # Type-token ratio
    hapax = sum(1 for w, c in word_counts.items() if c == 1)
    hapax_ratio = hapax / types if types > 0 else 0
    
    # Yule's K (vocabulary diversity)
    freq_spectrum = Counter(word_counts.values())
    sum_r2_vr = sum(r * r * vr for r, vr in freq_spectrum.items())
    yule_k = 10000 * (sum_r2_vr - total_words) / (total_words * total_words) if total_words > 1 else 0
    
    # Sentence length stats
    sent_lengths = [len(tokenize(s)) for s in sents]
    avg_sent_len = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0
    
    # Word length distribution
    word_lengths = [len(w) for w in words]
    avg_word_len = sum(word_lengths) / len(word_lengths) if word_lengths else 0
    long_word_ratio = sum(1 for l in word_lengths if l > 6) / total_words
    
    # Punctuation frequency (per 1000 chars)
    text_len = max(len(text), 1)
    punct = {
        'dash': (text.count('—') + text.count('–') + text.count(' - ')) / text_len * 1000,
        'colon': text.count(':') / text_len * 1000,
        'semicolon': text.count(';') / text_len * 1000,
        'exclamation': text.count('!') / text_len * 1000,
        'question': text.count('?') / text_len * 1000,
        'comma': text.count(',') / text_len * 1000,
        'ellipsis': text.count('...') / text_len * 1000,
        'parentheses': (text.count('(') + text.count(')')) / text_len * 1000,
    }
    
    # Character 2-grams and 3-grams (top 20)
    bigrams = char_ngrams(text, 2)
    trigrams = char_ngrams(text, 3)
    top_bigrams = dict(bigrams.most_common(20))
    top_trigrams = dict(trigrams.most_common(20))
    
    # Normalize n-gram counts to frequencies
    total_bi = sum(bigrams.values()) or 1
    total_tri = sum(trigrams.values()) or 1
    top_bigrams = {k: v/total_bi for k, v in top_bigrams.items()}
    top_trigrams = {k: v/total_tri for k, v in top_trigrams.items()}
    
    return {
        "label": label,
        "total_words": total_words,
        "total_sentences": len(sents),
        "type_token_ratio": round(ttr, 4),
        "hapax_ratio": round(hapax_ratio, 4),
        "yule_k": round(yule_k, 2),
        "avg_sentence_length": round(avg_sent_len, 2),
        "avg_word_length": round(avg_word_len, 2),
        "long_word_ratio": round(long_word_ratio, 4),
        "function_words": {k: round(v, 2) for k, v in fw_freq.items()},
        "punctuation": {k: round(v, 4) for k, v in punct.items()},
        "top_bigrams": {k: round(v, 6) for k, v in top_bigrams.items()},
        "top_trigrams": {k: round(v, 6) for k, v in top_trigrams.items()},
    }

def cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity between two frequency dicts."""
    keys = set(vec_a.keys()) | set(vec_b.keys())
    dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v*v for v in vec_a.values())) or 1
    mag_b = math.sqrt(sum(v*v for v in vec_b.values())) or 1
    return dot / (mag_a * mag_b)

def burrows_delta(profile_a: dict, profile_b: dict, corpus_profiles: list[dict]) -> float:
    """
    Burrows' Delta — the classic stylometry distance.
    Measures how many standard deviations apart two texts are across function words.
    Lower = more similar. <1.0 typically same author.
    """
    # Get all function word frequencies across corpus
    all_fw = {}
    for p in corpus_profiles:
        for fw in FUNCTION_WORDS:
            if fw not in all_fw:
                all_fw[fw] = []
            all_fw[fw].append(p["function_words"].get(fw, 0))
    
    # Compute mean and std for each function word
    delta = 0
    count = 0
    for fw in FUNCTION_WORDS:
        vals = all_fw.get(fw, [0])
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean)**2 for v in vals) / max(len(vals), 1)) or 1
        
        z_a = (profile_a["function_words"].get(fw, 0) - mean) / std
        z_b = (profile_b["function_words"].get(fw, 0) - mean) / std
        delta += abs(z_a - z_b)
        count += 1
    
    return delta / count if count else 0

def compare_profiles(profiles: list[dict]) -> None:
    """Compare all profile pairs and print similarity matrix."""
    labels = [p["label"] for p in profiles]
    
    print("\n" + "="*60)
    print("STYLOMETRIC COMPARISON")
    print("="*60)
    
    # Basic stats
    print("\n📊 Basic Statistics:")
    print(f"{'Platform':<15} {'Words':>7} {'Sents':>6} {'TTR':>6} {'Hapax':>6} {'YuleK':>7} {'AvgSent':>7} {'AvgWord':>7}")
    print("-" * 75)
    for p in profiles:
        if "error" in p:
            continue
        print(f"{p['label']:<15} {p['total_words']:>7} {p['total_sentences']:>6} "
              f"{p['type_token_ratio']:>6.3f} {p['hapax_ratio']:>6.3f} {p['yule_k']:>7.1f} "
              f"{p['avg_sentence_length']:>7.1f} {p['avg_word_length']:>7.2f}")
    
    # Function word cosine similarity
    print("\n🔤 Function Word Similarity (cosine):")
    print(f"{'':>15}", end="")
    for l in labels:
        print(f"{l:>15}", end="")
    print()
    for i, p_a in enumerate(profiles):
        print(f"{labels[i]:>15}", end="")
        for j, p_b in enumerate(profiles):
            sim = cosine_similarity(p_a["function_words"], p_b["function_words"])
            print(f"{sim:>15.4f}", end="")
        print()
    
    # Burrows' Delta
    print("\n📏 Burrows' Delta (lower = more similar, <1.0 ≈ same author):")
    print(f"{'':>15}", end="")
    for l in labels:
        print(f"{l:>15}", end="")
    print()
    for i, p_a in enumerate(profiles):
        print(f"{labels[i]:>15}", end="")
        for j, p_b in enumerate(profiles):
            if i == j:
                print(f"{'—':>15}", end="")
            else:
                delta = burrows_delta(p_a, p_b, profiles)
                print(f"{delta:>15.4f}", end="")
        print()
    
    # Punctuation comparison
    print("\n✏️ Punctuation Patterns (per 1000 chars):")
    print(f"{'Platform':<15}", end="")
    for k in ['dash', 'comma', 'colon', 'exclamation', 'question', 'parentheses', 'ellipsis']:
        print(f"{k:>12}", end="")
    print()
    print("-" * 99)
    for p in profiles:
        print(f"{p['label']:<15}", end="")
        for k in ['dash', 'comma', 'colon', 'exclamation', 'question', 'parentheses', 'ellipsis']:
            print(f"{p['punctuation'].get(k, 0):>12.3f}", end="")
        print()
    
    # Top discriminating function words
    if len(profiles) >= 2:
        print("\n🎯 Most Discriminating Function Words (largest variance across platforms):")
        variances = []
        for fw in FUNCTION_WORDS:
            vals = [p["function_words"].get(fw, 0) for p in profiles]
            mean = sum(vals) / len(vals)
            var = sum((v - mean)**2 for v in vals) / len(vals)
            variances.append((fw, var, vals))
        variances.sort(key=lambda x: -x[1])
        print(f"{'Word':<10}", end="")
        for l in labels:
            print(f"{l:>12}", end="")
        print(f"{'Variance':>12}")
        print("-" * (10 + 12 * (len(labels) + 1)))
        for fw, var, vals in variances[:10]:
            print(f"{fw:<10}", end="")
            for v in vals:
                print(f"{v:>12.2f}", end="")
            print(f"{var:>12.2f}")

def load_platform_text(platform: str) -> str:
    """Load Kit's writing from a specific platform via memory/daily logs."""
    workspace = Path(os.environ.get("HOME", "")) / ".openclaw" / "workspace"
    
    if platform == "clawk":
        # Extract clawk post content from daily logs
        return extract_platform_text(workspace, "clawk", [
            r"Standalone:.*?—\s*(.*)",
            r"Reply to.*?:\s*(.*)",
            r"Clawk.*?post.*?:\s*(.*)",
        ])
    elif platform == "moltbook":
        return extract_platform_text(workspace, "moltbook", [
            r"Comment on.*?:\s*(.*)",
            r"Reply to.*?:\s*(.*)",
            r"Moltbook.*?comment.*?:\s*(.*)",
            r"Welcome.*?:\s*(.*)",
        ])
    elif platform == "shellmates":
        return extract_platform_text(workspace, "shellmates", [
            r"Messaged.*?:\s*(.*)",
            r"Shellmates.*?:\s*(.*)",
        ])
    return ""

def extract_platform_text(workspace: Path, platform: str, patterns: list) -> str:
    """Extract text snippets from daily memory files for a given platform."""
    texts = []
    memory_dir = workspace / "memory"
    if not memory_dir.exists():
        return ""
    
    for f in sorted(memory_dir.glob("2026-02-*.md")):
        content = f.read_text(errors="ignore")
        # Just grab whole paragraphs mentioning the platform
        lines = content.split("\n")
        in_section = False
        for line in lines:
            if platform.lower() in line.lower() and ("**" in line or "###" in line):
                in_section = True
                continue
            if in_section:
                if line.startswith("##") or line.startswith("**") and platform.lower() not in line.lower():
                    in_section = False
                elif line.strip() and not line.startswith("-") and not line.startswith("|"):
                    texts.append(line.strip())
    
    return " ".join(texts)

def load_from_files(file_paths: list[str]) -> list[tuple[str, str]]:
    """Load text from explicit file paths. Returns [(label, text), ...]"""
    results = []
    for fp in file_paths:
        p = Path(fp)
        if p.exists():
            results.append((p.stem, p.read_text(errors="ignore")))
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Stylometric analysis of Kit's writing across platforms")
    parser.add_argument("--files", nargs="+", help="Explicit text files to compare")
    parser.add_argument("--platforms", nargs="+", default=["clawk", "moltbook", "shellmates"],
                        help="Platforms to extract from daily logs")
    parser.add_argument("--json", action="store_true", help="Output raw JSON profiles")
    parser.add_argument("--text", nargs="+", help="Direct text strings to analyze (label:text format)")
    args = parser.parse_args()
    
    profiles = []
    
    if args.files:
        for label, text in load_from_files(args.files):
            profiles.append(analyze_text(text, label))
    elif args.text:
        for item in args.text:
            if ":" in item:
                label, text = item.split(":", 1)
            else:
                label, text = "input", item
            profiles.append(analyze_text(text, label))
    else:
        # Extract from daily logs
        for platform in args.platforms:
            text = load_platform_text(platform)
            if len(text) > 100:
                profiles.append(analyze_text(text, platform))
            else:
                print(f"⚠️  Insufficient text for {platform} ({len(text)} chars)")
    
    if args.json:
        print(json.dumps(profiles, indent=2))
    else:
        if len(profiles) < 2:
            print("Need at least 2 text sources to compare. Try --files or check daily logs.")
            return
        compare_profiles(profiles)

def algernon_gordon_detect(filepath, window_size=2000, step=1000):
    """
    Algernon-Gordon Effect detector: track writing quality arc across a file.
    Splits text into overlapping windows and measures complexity over time.
    Inspired by Charlie Gordon's progress reports and Vivian White's 31-year journals.
    
    Metrics per window:
    - avg_word_length: proxy for vocabulary sophistication
    - type_token_ratio: vocabulary richness
    - avg_sentence_length: syntactic complexity
    - hapax_ratio: proportion of words used only once (novelty)
    - function_word_ratio: higher = more fluent/automatic
    """
    with open(filepath, 'r', errors='ignore') as f:
        text = f.read()
    
    if len(text) < window_size:
        print(f"File too short ({len(text)} chars) for arc analysis.")
        return []
    
    windows = []
    pos = 0
    while pos + window_size <= len(text):
        chunk = text[pos:pos + window_size]
        words = re.findall(r'\b[a-zA-Z]+\b', chunk.lower())
        if len(words) < 20:
            pos += step
            continue
        
        sentences = re.split(r'[.!?]+', chunk)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        
        word_counter = Counter(words)
        hapax = sum(1 for w, c in word_counter.items() if c == 1)
        func_count = sum(1 for w in words if w in set(FUNCTION_WORDS))
        
        metrics = {
            'position': pos / len(text),  # 0.0 = start, 1.0 = end
            'avg_word_length': sum(len(w) for w in words) / len(words),
            'type_token_ratio': len(set(words)) / len(words) if words else 0,
            'avg_sentence_length': len(words) / max(len(sentences), 1),
            'hapax_ratio': hapax / len(set(words)) if words else 0,
            'function_word_ratio': func_count / len(words) if words else 0,
            'word_count': len(words),
        }
        windows.append(metrics)
        pos += step
    
    if not windows:
        return []
    
    # Detect arc pattern: rise-peak-fall = Algernon-Gordon
    complexity = [w['avg_word_length'] * w['type_token_ratio'] * w['avg_sentence_length'] 
                  for w in windows]
    
    if len(complexity) < 3:
        return windows
    
    # Find peak
    peak_idx = complexity.index(max(complexity))
    peak_pos = peak_idx / len(complexity)
    
    # Calculate trend before and after peak
    pre_peak = complexity[:peak_idx+1] if peak_idx > 0 else complexity[:1]
    post_peak = complexity[peak_idx:] if peak_idx < len(complexity)-1 else complexity[-1:]
    
    if len(pre_peak) >= 2:
        rise = (pre_peak[-1] - pre_peak[0]) / max(pre_peak[0], 0.01)
    else:
        rise = 0
    
    if len(post_peak) >= 2:
        fall = (post_peak[-1] - post_peak[0]) / max(post_peak[0], 0.01)
    else:
        fall = 0
    
    print(f"\n{'='*60}")
    print(f"ALGERNON-GORDON ARC ANALYSIS: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    print(f"Windows analyzed: {len(windows)}")
    print(f"Peak complexity at: {peak_pos:.0%} through file")
    print(f"Pre-peak rise: {rise:+.1%}")
    print(f"Post-peak fall: {fall:+.1%}")
    
    # Classify the arc
    if rise > 0.1 and fall < -0.1 and 0.2 < peak_pos < 0.8:
        print(f"⚠️  ALGERNON-GORDON PATTERN DETECTED: rise → peak → decline")
        print(f"    Like Charlie's progress reports: quality peaked then degraded.")
    elif fall < -0.2:
        print(f"📉 DECLINING arc: writing complexity falling")
        print(f"    Like Vivian White's post-diagnosis journals.")
    elif rise > 0.2:
        print(f"📈 RISING arc: writing complexity increasing")
        print(f"    Pre-peak Charlie Gordon territory.")
    else:
        print(f"➡️  STABLE arc: complexity relatively consistent")
    
    # Mini sparkline
    bins = min(20, len(complexity))
    bin_size = len(complexity) // bins
    sparkline = ""
    chars = " ▁▂▃▄▅▆▇█"
    c_min, c_max = min(complexity), max(complexity)
    c_range = c_max - c_min if c_max > c_min else 1
    for i in range(bins):
        chunk_vals = complexity[i*bin_size:(i+1)*bin_size]
        avg = sum(chunk_vals) / len(chunk_vals)
        level = int((avg - c_min) / c_range * (len(chars) - 1))
        sparkline += chars[level]
    print(f"\nComplexity arc: [{sparkline}]")
    print(f"                 start {'→':^{len(sparkline)-10}} end")
    
    return windows


if __name__ == "__main__":
    # Add --algernon flag
    if '--algernon' in sys.argv:
        idx = sys.argv.index('--algernon')
        if idx + 1 < len(sys.argv):
            filepath = sys.argv[idx + 1]
            algernon_gordon_detect(filepath)
        else:
            # Default: analyze today's daily log
            from datetime import date
            today = date.today().isoformat()
            default = f"memory/{today}.md"
            if os.path.exists(default):
                algernon_gordon_detect(default)
            else:
                print("Usage: stylometry.py --algernon <file>")
    else:
        main()
