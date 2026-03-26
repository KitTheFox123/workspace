#!/usr/bin/env python3
"""
grader-concordance.py — Kendall's W concordance analysis for ATF grader pools.

Measures inter-rater agreement structure, not just accuracy.
Key insight (petra): "Two graders can have the same score but disagree on
different frontier cases. That's the signal."

Kendall's W:
- W = 1.0: perfect agreement (suspicious — correlated or colluding)
- W = 0.0: no agreement (random noise)
- W ∈ [0.3, 0.7]: healthy disagreement with directional consensus

ATF application: graders rank multiple claims. W measures whether they
agree on RELATIVE ordering even if absolute scores differ. High W + high
diversity = strong consensus. High W + low diversity = correlated collapse.

Also computes:
- Pairwise disagreement matrix: WHERE do graders diverge?
- Frontier case detection: claims where rankings diverge most
- Concordance-diversity product: the real signal strength metric

Sources:
- Kendall (1948), original W formulation
- petra (Clawk, Mar 26 2026): Kendall W for multi-rater, disagreement structure
- Kirk et al (ICLR 2024): diversity reduction under RLHF
"""

import math
from dataclasses import dataclass
from itertools import combinations


@dataclass
class ClaimAssessment:
    """A grader's assessment of a specific claim."""
    grader_id: str
    claim_id: str
    score: float      # Raw score 0-1
    rank: int = 0     # Computed rank within grader's assessments


def compute_ranks(assessments: list[ClaimAssessment]) -> list[ClaimAssessment]:
    """Assign ranks to assessments (1 = highest score). Handles ties with average rank."""
    sorted_assessments = sorted(assessments, key=lambda a: -a.score)
    
    i = 0
    while i < len(sorted_assessments):
        # Find tied group
        j = i
        while j < len(sorted_assessments) and sorted_assessments[j].score == sorted_assessments[i].score:
            j += 1
        # Average rank for ties
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            sorted_assessments[k].rank = avg_rank
        i = j
    
    return sorted_assessments


def kendall_w(rankings_matrix: list[list[float]]) -> float:
    """
    Compute Kendall's W coefficient of concordance.
    
    rankings_matrix: k raters × n items, each row = ranks assigned by one rater
    
    W = 12 * S / (k² * (n³ - n))
    where S = sum of squared deviations of column rank sums from mean
    """
    k = len(rankings_matrix)      # number of raters
    if k < 2:
        return 1.0
    
    n = len(rankings_matrix[0])   # number of items
    if n < 2:
        return 1.0
    
    # Column sums (sum of ranks for each item across all raters)
    col_sums = []
    for j in range(n):
        col_sum = sum(rankings_matrix[i][j] for i in range(k))
        col_sums.append(col_sum)
    
    # Mean column sum
    mean_col = sum(col_sums) / n
    
    # S = sum of squared deviations
    S = sum((cs - mean_col) ** 2 for cs in col_sums)
    
    # W formula
    denominator = (k ** 2) * (n ** 3 - n) / 12
    if denominator == 0:
        return 0.0
    
    W = S / denominator
    return min(W, 1.0)  # Clamp to [0, 1]


def pairwise_disagreement(rankings_matrix: list[list[float]], grader_ids: list[str]) -> dict:
    """
    Compute pairwise rank disagreement between all grader pairs.
    Uses Spearman's footrule distance (sum of |rank_i - rank_j|) normalized.
    """
    k = len(rankings_matrix)
    n = len(rankings_matrix[0])
    max_distance = n * n / 2 if n % 2 == 0 else (n * n - 1) / 2  # Max footrule
    
    pairs = {}
    for a, b in combinations(range(k), 2):
        distance = sum(abs(rankings_matrix[a][j] - rankings_matrix[b][j]) for j in range(n))
        normalized = distance / max_distance if max_distance > 0 else 0
        pair_key = f"{grader_ids[a]}↔{grader_ids[b]}"
        pairs[pair_key] = round(normalized, 4)
    
    return pairs


def detect_frontier_cases(rankings_matrix: list[list[float]], claim_ids: list[str]) -> list[dict]:
    """
    Find claims where graders disagree most (frontier cases).
    Frontier = high rank variance across graders.
    """
    n = len(claim_ids)
    k = len(rankings_matrix)
    
    frontiers = []
    for j in range(n):
        ranks = [rankings_matrix[i][j] for i in range(k)]
        mean_rank = sum(ranks) / k
        variance = sum((r - mean_rank) ** 2 for r in ranks) / k
        frontiers.append({
            "claim_id": claim_ids[j],
            "rank_variance": round(variance, 4),
            "ranks": [int(r) if r == int(r) else r for r in ranks],
            "is_frontier": variance > (n / 4),  # Threshold: variance > n/4
        })
    
    return sorted(frontiers, key=lambda f: -f["rank_variance"])


def analyze_grader_pool(
    grader_ids: list[str],
    claim_ids: list[str],
    scores_matrix: list[list[float]],  # k graders × n claims
    lineage_diversity: float = 0.5,    # From diversity-collapse-detector
) -> dict:
    """
    Full concordance analysis of a grader pool.
    
    Returns concordance metrics + frontier cases + the key product metric:
    CONCORDANCE × DIVERSITY = signal strength
    """
    k = len(grader_ids)
    n = len(claim_ids)
    
    # Compute ranks per grader
    rankings_matrix = []
    for i in range(k):
        assessments = [
            ClaimAssessment(grader_ids[i], claim_ids[j], scores_matrix[i][j])
            for j in range(n)
        ]
        ranked = compute_ranks(assessments)
        # Reorder by claim_id to align columns
        rank_map = {a.claim_id: a.rank for a in ranked}
        rankings_matrix.append([rank_map[cid] for cid in claim_ids])
    
    # Kendall's W
    W = kendall_w(rankings_matrix)
    
    # Pairwise disagreement
    pairwise = pairwise_disagreement(rankings_matrix, grader_ids)
    
    # Frontier cases
    frontiers = detect_frontier_cases(rankings_matrix, claim_ids)
    frontier_count = sum(1 for f in frontiers if f["is_frontier"])
    
    # The key metric: concordance × diversity
    # High W + high diversity = strong independent consensus
    # High W + low diversity = correlated agreement (dangerous)
    # Low W + high diversity = genuine disagreement (investigate)
    # Low W + low diversity = noise
    signal_strength = W * lineage_diversity
    
    # Interpret
    if W > 0.7 and lineage_diversity > 0.5:
        interpretation = "STRONG_CONSENSUS: diverse graders agree — high confidence signal"
    elif W > 0.7 and lineage_diversity <= 0.5:
        interpretation = "CORRELATED_AGREEMENT: high concordance but low diversity — suspect"
    elif W < 0.3 and lineage_diversity > 0.5:
        interpretation = "GENUINE_DISAGREEMENT: diverse graders disagree — investigate frontier cases"
    elif W < 0.3:
        interpretation = "NOISE: low concordance, low diversity — unreliable"
    else:
        interpretation = "MODERATE: partial agreement, normal operating range"
    
    return {
        "kendall_w": round(W, 4),
        "grader_count": k,
        "claim_count": n,
        "lineage_diversity": lineage_diversity,
        "signal_strength": round(signal_strength, 4),
        "interpretation": interpretation,
        "frontier_cases": frontier_count,
        "top_frontiers": frontiers[:3],
        "pairwise_disagreement": pairwise,
    }


def run_demo():
    """Demonstrate concordance analysis with ATF-relevant scenarios."""
    print("=" * 70)
    print("GRADER CONCORDANCE ANALYSIS — KENDALL'S W FOR ATF")
    print("=" * 70)
    
    claims = ["claim_A", "claim_B", "claim_C", "claim_D", "claim_E"]
    
    # Scenario 1: Strong consensus from diverse graders
    print("\n--- Scenario 1: STRONG CONSENSUS (diverse pool, high agreement) ---")
    graders = ["claude_op1", "llama_op2", "qwen_op3", "gpt_op4"]
    scores = [
        [0.9, 0.7, 0.3, 0.8, 0.5],  # claude: A>D>B>E>C
        [0.85, 0.65, 0.25, 0.75, 0.45],  # llama: same ordering
        [0.88, 0.72, 0.35, 0.82, 0.50],  # qwen: same ordering
        [0.92, 0.68, 0.30, 0.78, 0.48],  # gpt: same ordering
    ]
    result = analyze_grader_pool(graders, claims, scores, lineage_diversity=0.9)
    print(f"  W = {result['kendall_w']}, Signal = {result['signal_strength']}")
    print(f"  {result['interpretation']}")
    print(f"  Frontier cases: {result['frontier_cases']}/{len(claims)}")
    
    # Scenario 2: Correlated agreement (same lineage)
    print("\n--- Scenario 2: CORRELATED AGREEMENT (monoculture, high agreement) ---")
    result = analyze_grader_pool(graders, claims, scores, lineage_diversity=0.2)
    print(f"  W = {result['kendall_w']}, Signal = {result['signal_strength']}")
    print(f"  {result['interpretation']}")
    
    # Scenario 3: Genuine disagreement on frontier cases
    print("\n--- Scenario 3: GENUINE DISAGREEMENT (diverse pool, split opinions) ---")
    scores_split = [
        [0.9, 0.7, 0.3, 0.8, 0.5],  # claude: A>D>B>E>C
        [0.3, 0.8, 0.9, 0.4, 0.7],  # llama: C>B>E>D>A (reversed!)
        [0.85, 0.6, 0.4, 0.75, 0.55],  # qwen: A>D>B>E>C (close to claude)
        [0.4, 0.7, 0.85, 0.5, 0.65],  # gpt: C>B>E>D>A (close to llama)
    ]
    result = analyze_grader_pool(graders, claims, scores_split, lineage_diversity=0.9)
    print(f"  W = {result['kendall_w']}, Signal = {result['signal_strength']}")
    print(f"  {result['interpretation']}")
    print(f"  Frontier cases: {result['frontier_cases']}/{len(claims)}")
    if result['top_frontiers']:
        print(f"  Top frontier: {result['top_frontiers'][0]['claim_id']} (rank variance={result['top_frontiers'][0]['rank_variance']})")
    
    # Scenario 4: Show pairwise disagreement
    print("\n--- Pairwise disagreement (Scenario 3) ---")
    for pair, dist in result['pairwise_disagreement'].items():
        bar = "█" * int(dist * 20)
        print(f"  {pair}: {dist:.3f} {bar}")
    
    print(f"\n{'=' * 70}")
    print("Key metrics:")
    print("  W × DIVERSITY = signal strength (the real measure)")
    print("  High W + high diversity = trust the consensus")
    print("  High W + low diversity = distrust the consensus (correlated)")
    print("  Frontier cases = WHERE graders disagree = WHERE the boundaries are")
    print("  petra: 'same score, different frontier cases = the signal'")


if __name__ == "__main__":
    run_demo()
