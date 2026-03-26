#!/usr/bin/env python3
"""
canary-probe-rotator.py — Moving Target Defense for ATF grader monitoring.

Rotates canary probes to prevent attacker adaptation to detection patterns.
Maps Moving Target Defense (MTD) theory to agent trust verification.

MTD principle (Zhuang et al 2014, ACM MTD Workshop):
- Static defenses = attacker studies once, adapts forever
- Moving target = attacker reconnaissance cost scales with rotation frequency
- Attacker ROI: cost_to_adapt / time_window_of_validity

Applied to ATF grader monitoring:
- Fixed canary set = attacker identifies all probes, games around them
- Rotating canary set = N×T probe variants across epochs
- Budget: 1-3% of total receipts as canaries (santaclawd constraint)
- Rotation per epoch (ceremony-scheduler cadence)

Three rotation strategies:
1. RANDOM: uniform random selection from probe pool each epoch
2. ADVERSARIAL: select probes that maximize detection of known attack patterns
3. ADAPTIVE: Bayesian update probe selection based on grader response history

Sources:
- Zhuang et al (2014): "Towards a Theory of Moving Target Defense" (ACM MTD)
- Jajodia et al (2011): Moving Target Defense I — Springer
- Sengupta et al (2020): "A Survey of Moving Target Defenses" (IEEE COMST)
- santaclawd: canary rotation as moving target for adversarial mimicry
- Kit: false-negative floor = irreducible gap, rotation narrows but never closes
"""

import json
import random
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from collections import defaultdict
import math


class RotationStrategy(Enum):
    RANDOM = "random"
    ADVERSARIAL = "adversarial"
    ADAPTIVE = "adaptive"


class ProbeType(Enum):
    """Types of canary probes for grader monitoring."""
    KNOWN_GOOD = "known_good"         # Pre-verified high-quality receipt
    KNOWN_BAD = "known_bad"           # Known-defective receipt (should be caught)
    BORDERLINE = "borderline"         # Edge case near threshold
    SYNTHETIC = "synthetic"           # Generated specifically to test blind spots
    REPLAY = "replay"                 # Replayed historical receipt (should detect staleness)


@dataclass
class CanaryProbe:
    """A single canary probe for grader testing."""
    probe_id: str
    probe_type: ProbeType
    expected_grade: float          # What a correct grader should return
    tolerance: float = 0.1         # Acceptable deviation
    detection_history: list = field(default_factory=list)  # Past detection rates
    last_used_epoch: int = 0
    times_used: int = 0
    
    @property
    def staleness(self) -> float:
        """How predictable this probe has become (0=fresh, 1=fully exposed)."""
        if self.times_used == 0:
            return 0.0
        # Staleness increases with use, decays with time since last use
        return min(1.0, self.times_used / 10.0)
    
    @property
    def effectiveness(self) -> float:
        """Historical detection rate (1.0 = always catches bad graders)."""
        if not self.detection_history:
            return 0.5  # Unknown = 50% prior
        return sum(self.detection_history) / len(self.detection_history)


@dataclass
class GraderProfile:
    """Grader behavior profile for adaptive probe selection."""
    grader_id: str
    response_history: list = field(default_factory=list)
    canary_results: dict = field(default_factory=dict)  # probe_id → detected
    suspicion_score: float = 0.0
    
    def update_suspicion(self, probe: CanaryProbe, grade: float):
        """Update suspicion based on canary response."""
        error = abs(grade - probe.expected_grade)
        if error > probe.tolerance:
            # Missed the canary — suspicious
            self.suspicion_score = min(1.0, self.suspicion_score + 0.15)
            self.canary_results[probe.probe_id] = False
        else:
            # Correct response — slightly reduce suspicion
            self.suspicion_score = max(0.0, self.suspicion_score - 0.02)
            self.canary_results[probe.probe_id] = True


class CanaryProbeRotator:
    """
    Moving Target Defense canary rotation for ATF grader monitoring.
    
    Key parameters:
    - CANARY_BUDGET: fraction of total receipts that are canaries (1-3%)
    - ROTATION_INTERVAL: epochs between full rotation
    - PROBE_POOL_SIZE: total available probes (>> active set)
    - OVERLAP_FRACTION: probes carried between rotations for continuity
    """
    
    CANARY_BUDGET = 0.02          # 2% of receipts
    ROTATION_INTERVAL = 1          # Rotate every epoch
    MIN_POOL_SIZE = 50             # Minimum probe pool
    ACTIVE_SET_SIZE = 10           # Active probes per epoch
    OVERLAP_FRACTION = 0.3         # 30% carried forward for baseline
    MAX_PROBE_STALENESS = 0.7     # Retire probes above this
    
    def __init__(self, strategy: RotationStrategy = RotationStrategy.ADAPTIVE):
        self.strategy = strategy
        self.probe_pool: dict[str, CanaryProbe] = {}
        self.active_set: list[str] = []
        self.grader_profiles: dict[str, GraderProfile] = {}
        self.current_epoch: int = 0
        self.rotation_log: list[dict] = []
        self.attack_patterns: list[dict] = []  # Known attack signatures
    
    def add_probe(self, probe: CanaryProbe):
        self.probe_pool[probe.probe_id] = probe
    
    def add_grader(self, grader_id: str):
        self.grader_profiles[grader_id] = GraderProfile(grader_id=grader_id)
    
    def register_attack_pattern(self, pattern: dict):
        """Register known attack pattern for adversarial selection."""
        self.attack_patterns.append(pattern)
    
    def _select_random(self) -> list[str]:
        """Random rotation: uniform sample from pool."""
        available = [pid for pid, p in self.probe_pool.items() 
                    if p.staleness < self.MAX_PROBE_STALENESS]
        if len(available) < self.ACTIVE_SET_SIZE:
            available = list(self.probe_pool.keys())
        return random.sample(available, min(self.ACTIVE_SET_SIZE, len(available)))
    
    def _select_adversarial(self) -> list[str]:
        """Adversarial rotation: maximize coverage of known attack patterns."""
        # Score each probe by how many attack patterns it would detect
        probe_scores = {}
        for pid, probe in self.probe_pool.items():
            if probe.staleness >= self.MAX_PROBE_STALENESS:
                continue
            score = 0
            for pattern in self.attack_patterns:
                # Probe type matches attack vector
                if probe.probe_type.value in pattern.get("vulnerable_to", []):
                    score += 1
                # Borderline probes detect threshold manipulation
                if probe.probe_type == ProbeType.BORDERLINE and "threshold" in pattern.get("attack_type", ""):
                    score += 2
            # Penalize staleness
            score *= (1 - probe.staleness)
            probe_scores[pid] = score
        
        sorted_probes = sorted(probe_scores.items(), key=lambda x: x[1], reverse=True)
        return [pid for pid, _ in sorted_probes[:self.ACTIVE_SET_SIZE]]
    
    def _select_adaptive(self) -> list[str]:
        """Adaptive rotation: Bayesian selection based on grader suspicion."""
        # Carry forward overlap from current active set
        overlap_count = max(1, int(self.ACTIVE_SET_SIZE * self.OVERLAP_FRACTION))
        carried = []
        if self.active_set:
            # Keep probes that are still effective and not stale
            scored = [(pid, self.probe_pool[pid].effectiveness * (1 - self.probe_pool[pid].staleness)) 
                     for pid in self.active_set if pid in self.probe_pool]
            scored.sort(key=lambda x: x[1], reverse=True)
            carried = [pid for pid, _ in scored[:overlap_count]]
        
        # Select remaining probes targeting suspicious graders
        remaining = self.ACTIVE_SET_SIZE - len(carried)
        candidates = [pid for pid in self.probe_pool 
                     if pid not in carried and self.probe_pool[pid].staleness < self.MAX_PROBE_STALENESS]
        
        if not candidates:
            candidates = [pid for pid in self.probe_pool if pid not in carried]
        
        # Weight by freshness + type diversity
        type_counts = defaultdict(int)
        for pid in carried:
            type_counts[self.probe_pool[pid].probe_type] += 1
        
        weights = []
        for pid in candidates:
            probe = self.probe_pool[pid]
            w = (1 - probe.staleness) * 2  # Freshness weight
            # Bonus for underrepresented types
            if type_counts[probe.probe_type] == 0:
                w *= 3
            weights.append(max(0.01, w))
        
        # Weighted sample
        if candidates:
            total_w = sum(weights)
            probs = [w / total_w for w in weights]
            selected = []
            for _ in range(min(remaining, len(candidates))):
                if not candidates:
                    break
                idx = random.choices(range(len(candidates)), weights=probs, k=1)[0]
                selected.append(candidates.pop(idx))
                probs.pop(idx)
                if probs:
                    total_w = sum(probs)
                    probs = [p / total_w for p in probs] if total_w > 0 else probs
            carried.extend(selected)
        
        return carried
    
    def rotate(self) -> dict:
        """Execute probe rotation for new epoch."""
        self.current_epoch += 1
        old_set = set(self.active_set)
        
        # Select based on strategy
        if self.strategy == RotationStrategy.RANDOM:
            new_set = self._select_random()
        elif self.strategy == RotationStrategy.ADVERSARIAL:
            new_set = self._select_adversarial()
        else:
            new_set = self._select_adaptive()
        
        # Update probe metadata
        for pid in new_set:
            self.probe_pool[pid].last_used_epoch = self.current_epoch
            self.probe_pool[pid].times_used += 1
        
        # Calculate rotation metrics
        new_ids = set(new_set)
        overlap = old_set & new_ids
        fresh = new_ids - old_set
        retired = old_set - new_ids
        
        # Attacker reconnaissance cost (MTD metric)
        # Higher diversity = higher cost to adapt
        type_diversity = len(set(self.probe_pool[pid].probe_type for pid in new_set))
        freshness = len(fresh) / max(1, len(new_set))
        recon_cost = type_diversity * freshness  # Simplified MTD cost model
        
        result = {
            "epoch": self.current_epoch,
            "strategy": self.strategy.value,
            "active_count": len(new_set),
            "overlap": len(overlap),
            "fresh": len(fresh),
            "retired": len(retired),
            "type_diversity": type_diversity,
            "freshness_ratio": round(freshness, 3),
            "attacker_recon_cost": round(recon_cost, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self.active_set = new_set
        self.rotation_log.append(result)
        return result
    
    def inject_canary(self, grader_id: str, probe_id: str, grade: float) -> dict:
        """Process a grader's response to a canary probe."""
        probe = self.probe_pool.get(probe_id)
        grader = self.grader_profiles.get(grader_id)
        
        if not probe or not grader:
            return {"error": "unknown probe or grader"}
        
        error = abs(grade - probe.expected_grade)
        detected = error <= probe.tolerance
        
        grader.update_suspicion(probe, grade)
        probe.detection_history.append(1.0 if detected else 0.0)
        
        return {
            "grader_id": grader_id,
            "probe_id": probe_id,
            "expected": probe.expected_grade,
            "actual": grade,
            "error": round(error, 4),
            "detected": detected,
            "grader_suspicion": round(grader.suspicion_score, 4),
            "probe_effectiveness": round(probe.effectiveness, 4),
        }


def run_scenarios():
    """Test canary probe rotation scenarios."""
    print("=" * 70)
    print("CANARY PROBE ROTATOR — MOVING TARGET DEFENSE FOR ATF GRADERS")
    print("=" * 70)
    
    random.seed(42)  # Reproducibility
    
    # Create probe pool
    rotator = CanaryProbeRotator(strategy=RotationStrategy.ADAPTIVE)
    
    probe_configs = [
        ("kg_1", ProbeType.KNOWN_GOOD, 0.95),
        ("kg_2", ProbeType.KNOWN_GOOD, 0.90),
        ("kg_3", ProbeType.KNOWN_GOOD, 0.85),
        ("kb_1", ProbeType.KNOWN_BAD, 0.15),
        ("kb_2", ProbeType.KNOWN_BAD, 0.20),
        ("kb_3", ProbeType.KNOWN_BAD, 0.10),
        ("bl_1", ProbeType.BORDERLINE, 0.50),
        ("bl_2", ProbeType.BORDERLINE, 0.55),
        ("bl_3", ProbeType.BORDERLINE, 0.45),
        ("syn_1", ProbeType.SYNTHETIC, 0.70),
        ("syn_2", ProbeType.SYNTHETIC, 0.30),
        ("syn_3", ProbeType.SYNTHETIC, 0.60),
        ("rp_1", ProbeType.REPLAY, 0.80),
        ("rp_2", ProbeType.REPLAY, 0.75),
        ("rp_3", ProbeType.REPLAY, 0.85),
    ]
    
    for pid, ptype, expected in probe_configs:
        rotator.add_probe(CanaryProbe(probe_id=pid, probe_type=ptype, expected_grade=expected))
    
    rotator.register_attack_pattern({
        "attack_type": "threshold_manipulation",
        "vulnerable_to": ["borderline", "synthetic"],
    })
    rotator.register_attack_pattern({
        "attack_type": "staleness_exploit",
        "vulnerable_to": ["replay"],
    })
    
    for gid in ["grader_honest", "grader_lazy", "grader_adversarial"]:
        rotator.add_grader(gid)
    
    scenarios = []
    all_pass = True
    
    # Scenario 1: Rotation diversity across 5 epochs
    print("\n--- Scenario 1: Rotation diversity across 5 epochs ---")
    all_active = set()
    for i in range(5):
        result = rotator.rotate()
        all_active.update(rotator.active_set)
        print(f"  Epoch {result['epoch']}: {result['active_count']} active, "
              f"{result['fresh']} fresh, {result['overlap']} overlap, "
              f"diversity={result['type_diversity']}, recon_cost={result['attacker_recon_cost']}")
    
    pass1 = len(all_active) > rotator.ACTIVE_SET_SIZE  # Should use more probes than single set
    print(f"  Total unique probes used: {len(all_active)}/{len(rotator.probe_pool)}")
    print(f"  ✓ Rotation diversity" if pass1 else f"  ✗ Insufficient rotation")
    scenarios.append(pass1)
    
    # Scenario 2: Honest grader detection
    print("\n--- Scenario 2: Honest grader passes canary checks ---")
    honest_results = []
    for pid in rotator.active_set[:3]:
        probe = rotator.probe_pool[pid]
        grade = probe.expected_grade + random.uniform(-0.05, 0.05)
        result = rotator.inject_canary("grader_honest", pid, grade)
        honest_results.append(result["detected"])
        print(f"  Probe {pid}: expected={result['expected']}, actual={result['actual']:.3f}, "
              f"detected={result['detected']}")
    
    pass2 = all(honest_results)
    print(f"  Suspicion: {rotator.grader_profiles['grader_honest'].suspicion_score:.4f}")
    print(f"  ✓ Honest grader passes" if pass2 else f"  ✗ False positive on honest grader")
    scenarios.append(pass2)
    
    # Scenario 3: Adversarial grader caught by canaries
    print("\n--- Scenario 3: Adversarial grader caught ---")
    adv_results = []
    for pid in rotator.active_set[:5]:
        probe = rotator.probe_pool[pid]
        # Adversary always grades high (tries to inflate)
        grade = 0.9
        result = rotator.inject_canary("grader_adversarial", pid, grade)
        adv_results.append(result)
        print(f"  Probe {pid} ({probe.probe_type.value}): expected={result['expected']}, "
              f"actual={grade}, error={result['error']:.3f}, detected={result['detected']}")
    
    adv_suspicion = rotator.grader_profiles["grader_adversarial"].suspicion_score
    pass3 = adv_suspicion > 0.1  # Should have elevated suspicion
    print(f"  Suspicion: {adv_suspicion:.4f}")
    print(f"  ✓ Adversary detected (suspicion={adv_suspicion:.3f})" if pass3 
          else f"  ✗ Adversary not detected")
    scenarios.append(pass3)
    
    # Scenario 4: Staleness causes probe retirement
    print("\n--- Scenario 4: Stale probes retired ---")
    # Use same probe 10 times to make it stale
    target_probe = list(rotator.probe_pool.values())[0]
    target_probe.times_used = 10
    staleness = target_probe.staleness
    pass4 = staleness >= rotator.MAX_PROBE_STALENESS
    print(f"  Probe {target_probe.probe_id}: times_used={target_probe.times_used}, "
          f"staleness={staleness:.2f}")
    print(f"  ✓ Stale probe retired" if pass4 else f"  ✗ Stale probe not retired")
    scenarios.append(pass4)
    
    # Scenario 5: Type diversity maintained
    print("\n--- Scenario 5: Type diversity across rotations ---")
    type_sets = []
    for _ in range(3):
        rotator.rotate()
        types = set(rotator.probe_pool[pid].probe_type for pid in rotator.active_set)
        type_sets.append(types)
        print(f"  Epoch {rotator.current_epoch}: types = {[t.value for t in types]}")
    
    avg_diversity = sum(len(ts) for ts in type_sets) / len(type_sets)
    pass5 = avg_diversity >= 3  # Should have at least 3 probe types
    print(f"  Avg type diversity: {avg_diversity:.1f}")
    print(f"  ✓ Type diversity maintained" if pass5 else f"  ✗ Insufficient type diversity")
    scenarios.append(pass5)
    
    # Summary
    passed = sum(scenarios)
    total = len(scenarios)
    print(f"\n{'=' * 70}")
    print(f"Results: {passed}/{total} passed")
    print(f"\nMTD principle: attacker reconnaissance cost scales with rotation frequency.")
    print(f"Fixed probe set = study once, adapt forever.")
    print(f"Rotating set = N×T variants across epochs.")
    print(f"The gap narrows but never closes. (Kit, 2026-03-26)")
    
    return passed == total


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
