#!/usr/bin/env python3
"""Find taxicab numbers and cube sum representations. Inspired by Ramanujan's 1729."""
import sys
from collections import defaultdict

def cube_sums(limit):
    """Find all numbers expressible as sum of two cubes in multiple ways."""
    sums = defaultdict(list)
    cbrt = int(limit ** (1/3)) + 1
    for a in range(1, cbrt + 1):
        for b in range(a, cbrt + 1):
            s = a**3 + b**3
            if s <= limit:
                sums[s].append((a, b))
    return {n: pairs for n, pairs in sums.items() if len(pairs) >= 2}

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    ways = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    results = cube_sums(limit)
    taxicabs = sorted((n, p) for n, p in results.items() if len(p) >= ways)
    
    print(f"Taxicab numbers up to {limit} (≥{ways} representations):\n")
    for n, pairs in taxicabs[:20]:
        reps = " = ".join(f"{a}³+{b}³" for a, b in pairs)
        print(f"  {n} = {reps}")
    print(f"\nTotal found: {len(taxicabs)}")
    
    if 1729 in results:
        print(f"\n🦊 Hardy-Ramanujan number 1729:")
        for a, b in results[1729]:
            print(f"  {a}³ + {b}³ = {a**3} + {b**3} = 1729")

if __name__ == "__main__":
    main()
