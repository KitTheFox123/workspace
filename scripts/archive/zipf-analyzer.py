#!/usr/bin/env python3
"""Analyze word frequency distributions in text files for Zipf's law compliance."""
import sys, re, math
from collections import Counter
from pathlib import Path

def analyze_file(path):
    text = Path(path).read_text()
    words = re.findall(r'[a-z]+', text.lower())
    freq = Counter(words)
    ranked = freq.most_common()
    
    if len(ranked) < 10:
        print(f"Too few unique words ({len(ranked)})")
        return
    
    print(f"File: {path}")
    print(f"Total tokens: {len(words)}, Unique types: {len(ranked)}")
    print(f"Type-token ratio: {len(ranked)/len(words):.3f}")
    print(f"\nTop 20 words:")
    print(f"{'Rank':>5} {'Word':>15} {'Freq':>8} {'Expected':>10} {'Ratio':>8}")
    
    f1 = ranked[0][1]  # frequency of rank 1
    
    # Calculate Zipf deviation
    deviations = []
    for i, (word, count) in enumerate(ranked[:20], 1):
        expected = f1 / i  # ideal Zipf
        ratio = count / expected if expected > 0 else 0
        deviations.append(abs(1 - ratio))
        print(f"{i:>5} {word:>15} {count:>8} {expected:>10.1f} {ratio:>8.2f}")
    
    avg_dev = sum(deviations) / len(deviations)
    
    # Log-log regression for alpha
    log_ranks = [math.log(i+1) for i in range(min(50, len(ranked)))]
    log_freqs = [math.log(ranked[i][1]) for i in range(min(50, len(ranked)))]
    n = len(log_ranks)
    sx = sum(log_ranks)
    sy = sum(log_freqs)
    sxy = sum(x*y for x,y in zip(log_ranks, log_freqs))
    sxx = sum(x*x for x in log_ranks)
    alpha = -(n*sxy - sx*sy) / (n*sxx - sx*sx)
    
    print(f"\nZipf exponent α ≈ {alpha:.3f} (ideal = 1.0)")
    print(f"Avg deviation from ideal (top 20): {avg_dev:.3f}")
    if 0.8 <= alpha <= 1.2:
        print("✅ Near-Zipfian distribution")
    elif 0.5 <= alpha <= 1.5:
        print("⚠️ Approximate Zipf (stretched)")
    else:
        print("❌ Non-Zipfian")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: zipf-analyzer.py <file> [file2...]")
        sys.exit(1)
    for f in sys.argv[1:]:
        analyze_file(f)
        print()
