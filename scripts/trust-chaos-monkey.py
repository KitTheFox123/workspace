#!/usr/bin/env python3
"""
Trust Chaos Monkey — FIT-style fault injection for agent trust stacks.

Inspired by Netflix FIT (2014): precise failure injection, not just instance killing.
Tests detect→flag→cert-update latency under various failure modes.

Scenarios:
1. Gossip partition — one node isolated, does Φ accrual detect?
2. Sleeper window race — flag must bind before sleeper decay starts
3. Tile proof stale — CDN cache serves old tree_head
4. DLQ replay attack — attacker replays old email DLQ cert
5. Cascade: attestor compromise + gossip partition + sleeper decay
6. Byzantine gossip — 1/3 nodes send conflicting flags

Based on: Netflix Chaos Monkey/FIT, Hayashibara Φ accrual, Kumkale 2004
"""

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FaultType(Enum):
    PARTITION = "network_partition"
    STALE_TILE = "stale_tile_proof"
    SLEEPER_DECAY = "sleeper_flag_decay"
    DLQ_REPLAY = "dlq_replay_attack"
    BYZANTINE = "byzantine_gossip"
    CASCADE = "cascade_multi_fault"


@dataclass
class TrustNode:
    node_id: str
    trust_score: float = 0.5
    flags: dict = field(default_factory=dict)  # cert_hash -> flag_info
    last_gossip: float = field(default_factory=time.time)
    partitioned: bool = False
    phi_threshold: float = 3.0  # Φ accrual threshold

    def receive_gossip(self, flag_hash: str, flag_type: str, timestamp: float):
        if self.partitioned:
            return False
        self.flags[flag_hash] = {
            "type": flag_type,
            "received": timestamp,
            "bound_to_cert": flag_type == "cert_bound",
        }
        self.last_gossip = timestamp
        return True

    def phi_accrual(self, now: float, expected_interval: float = 10.0) -> float:
        """Hayashibara Φ accrual failure detector."""
        gap = now - self.last_gossip
        if gap <= expected_interval:
            return 0.0
        # Simplified: Φ grows with gap/expected ratio
        return (gap / expected_interval) ** 1.5

    def sleeper_check(self, now: float) -> list:
        """Check for sleeper effect: flags that have decayed."""
        sleepers = []
        for cert_hash, info in self.flags.items():
            age = now - info["received"]
            if not info["bound_to_cert"] and age > 30:  # Session-bound flags decay
                decay = min(1.0, age / 100)
                sleepers.append({
                    "cert_hash": cert_hash,
                    "decay": decay,
                    "age": age,
                    "bound": info["bound_to_cert"],
                })
        return sleepers


@dataclass 
class ChaosResult:
    scenario: str
    fault_type: FaultType
    detected: bool
    detection_latency: float  # seconds
    sleeper_window: float  # seconds of vulnerability
    grade: str
    details: str


def grade(detected: bool, latency: float, sleeper_window: float) -> str:
    if not detected:
        return "F"
    if sleeper_window > 60:
        return "D"
    if latency > 30:
        return "C"
    if latency > 10:
        return "B"
    return "A"


def scenario_gossip_partition() -> ChaosResult:
    """One node partitioned — does Φ detect before sleeper window opens?"""
    nodes = [TrustNode(f"node_{i}") for i in range(5)]
    target = nodes[2]
    target.partitioned = True

    # Gossip rounds — target misses all
    now = time.time()
    for tick in range(20):
        t = now + tick * 5  # 5s gossip interval
        flag_hash = hashlib.sha256(f"flag_{tick}".encode()).hexdigest()[:12]
        for node in nodes:
            if node != target:
                node.receive_gossip(flag_hash, "session_bound", t)

    # Check Φ on target
    check_time = now + 100
    phi = target.phi_accrual(check_time, expected_interval=5.0)
    detected = phi > target.phi_threshold
    latency = 100.0  # Detected at check_time
    sleeper_window = 0 if detected else 100

    return ChaosResult(
        scenario="Gossip partition (1/5 nodes isolated)",
        fault_type=FaultType.PARTITION,
        detected=detected,
        detection_latency=latency if detected else -1,
        sleeper_window=sleeper_window,
        grade=grade(detected, latency, sleeper_window),
        details=f"Φ={phi:.1f} (threshold={target.phi_threshold}). "
                f"{'Detected' if detected else 'MISSED'} after 100s partition.",
    )


def scenario_sleeper_race() -> ChaosResult:
    """Flag must bind to cert before sleeper decay starts."""
    node = TrustNode("verifier")
    now = time.time()

    # Session-bound flag (decays)
    node.receive_gossip("compromised_cert_001", "session_bound", now - 60)
    # Cert-bound flag (persists)
    node.receive_gossip("compromised_cert_002", "cert_bound", now - 60)

    sleepers = node.sleeper_check(now)
    session_decayed = any(s["cert_hash"] == "compromised_cert_001" for s in sleepers)
    cert_persisted = not any(s["cert_hash"] == "compromised_cert_002" for s in sleepers)

    detected = cert_persisted  # cert-bound flags survive
    sleeper_window = 60 if session_decayed else 0

    return ChaosResult(
        scenario="Sleeper window race (session vs cert-bound flags)",
        fault_type=FaultType.SLEEPER_DECAY,
        detected=detected,
        detection_latency=0,
        sleeper_window=sleeper_window,
        grade="A" if (detected and not session_decayed) else ("C" if detected else "F"),
        details=f"Session flag decayed: {session_decayed}. Cert flag persisted: {cert_persisted}. "
                f"{'VULNERABILITY' if session_decayed else 'OK'}: session-bound flags decay after 60s.",
    )


def scenario_stale_tile() -> ChaosResult:
    """CDN serves old tree_head — verifier accepts stale proof."""
    real_tree_head = hashlib.sha256(b"tree_head_v2").hexdigest()[:16]
    stale_tree_head = hashlib.sha256(b"tree_head_v1").hexdigest()[:16]

    # Verifier gets stale tile from CDN
    cdn_stale = True
    served_head = stale_tree_head if cdn_stale else real_tree_head

    # Gossip should carry latest tree_head
    gossip_head = real_tree_head
    mismatch_detected = served_head != gossip_head

    return ChaosResult(
        scenario="Stale tile proof (CDN cache lag)",
        fault_type=FaultType.STALE_TILE,
        detected=mismatch_detected,
        detection_latency=5.0,  # One gossip round
        sleeper_window=5.0,  # Window until gossip corrects
        grade="B" if mismatch_detected else "F",
        details=f"CDN tree_head: {served_head}. Gossip tree_head: {gossip_head}. "
                f"{'Mismatch detected' if mismatch_detected else 'ACCEPTED STALE'}.",
    )


def scenario_dlq_replay() -> ChaosResult:
    """Attacker replays old email DLQ cert request."""
    now = time.time()
    original_key = hashlib.sha256(f"dep_001:{int(now - 7200) // 3600 * 3600}".encode()).hexdigest()[:32]
    replay_key = original_key  # Same key (old deposit)

    # Server checks: key exists + TTL
    key_age_hours = 2
    ttl_hours = 24
    within_ttl = key_age_hours < ttl_hours

    # Idempotency dedup catches it
    deduplicated = within_ttl  # Within TTL = dedup; outside = reissue risk

    return ChaosResult(
        scenario="DLQ replay attack (old email cert request)",
        fault_type=FaultType.DLQ_REPLAY,
        detected=deduplicated,
        detection_latency=0,
        sleeper_window=0 if deduplicated else 24 * 3600,
        grade="A" if deduplicated else "F",
        details=f"Key age: {key_age_hours}h. TTL: {ttl_hours}h. "
                f"{'Deduplicated (safe)' if deduplicated else 'REISSUED (double cert!)'}.",
    )


def scenario_byzantine_gossip() -> ChaosResult:
    """1/3 nodes send conflicting flags — BFT threshold."""
    n_nodes = 9
    n_byzantine = 3  # f = 3, need n >= 3f+1 = 10... we're below threshold!
    
    honest_flag = "revoked"
    byzantine_flag = "valid"
    
    votes = []
    for i in range(n_nodes):
        if i < n_byzantine:
            votes.append(byzantine_flag)
        else:
            votes.append(honest_flag)
    
    random.shuffle(votes)
    revoked_count = sum(1 for v in votes if v == "revoked")
    valid_count = sum(1 for v in votes if v == "valid")
    
    # BFT requires 2f+1 = 7 honest votes for n=9, f=3
    # We have 6 honest, need 7. Below threshold!
    bft_threshold = (n_nodes * 2) // 3 + 1
    consensus = revoked_count >= bft_threshold
    
    return ChaosResult(
        scenario=f"Byzantine gossip ({n_byzantine}/{n_nodes} adversarial)",
        fault_type=FaultType.BYZANTINE,
        detected=consensus,
        detection_latency=15.0 if consensus else -1,
        sleeper_window=0 if consensus else 999,
        grade="A" if consensus else "D",
        details=f"Votes: {revoked_count} revoked, {valid_count} valid. "
                f"BFT threshold: {bft_threshold}/{n_nodes}. "
                f"{'Consensus reached' if consensus else 'SPLIT — below BFT threshold (n=9 < 3f+1=10)'}.",
    )


def scenario_cascade() -> ChaosResult:
    """Multi-fault: compromise + partition + sleeper decay simultaneously."""
    node = TrustNode("victim")
    now = time.time()

    # 1. Attestor compromise → flag issued (session-bound)
    node.receive_gossip("compromised_attestor", "session_bound", now - 120)

    # 2. Partition starts → no gossip updates
    node.partitioned = True

    # 3. Sleeper decay happens during partition
    sleepers = node.sleeper_check(now)
    flag_decayed = len(sleepers) > 0

    # 4. Partition heals — but flag already gone
    node.partitioned = False
    phi = node.phi_accrual(now, expected_interval=5.0)

    # Detection: only if cert-bound flag existed
    detected = not flag_decayed  # If flag survived = detected
    
    return ChaosResult(
        scenario="Cascade: compromise + partition + sleeper decay",
        fault_type=FaultType.CASCADE,
        detected=detected,
        detection_latency=-1 if not detected else 120,
        sleeper_window=120 if flag_decayed else 0,
        grade="F" if flag_decayed else "A",
        details=f"Flag decayed during partition: {flag_decayed}. Φ={phi:.1f}. "
                f"{'WORST CASE: compromise invisible after partition heals' if flag_decayed else 'Flag survived'}. "
                f"Fix: cert-bound flags + append-only revocation log.",
    )


def run_chaos():
    print("=" * 65)
    print("TRUST CHAOS MONKEY — FIT-style fault injection")
    print("Netflix FIT (2014) + Hayashibara Φ + Kumkale sleeper model")
    print("=" * 65)

    scenarios = [
        scenario_gossip_partition,
        scenario_sleeper_race,
        scenario_stale_tile,
        scenario_dlq_replay,
        scenario_byzantine_gossip,
        scenario_cascade,
    ]

    results = []
    for fn in scenarios:
        r = fn()
        results.append(r)
        print(f"\n--- {r.scenario} ---")
        print(f"  Fault: {r.fault_type.value}")
        print(f"  Detected: {r.detected} | Latency: {r.detection_latency:.0f}s | Sleeper window: {r.sleeper_window:.0f}s")
        print(f"  Grade: {r.grade}")
        print(f"  {r.details}")

    print("\n" + "=" * 65)
    print("SUMMARY")
    grades = [r.grade for r in results]
    for g in ["A", "B", "C", "D", "F"]:
        count = grades.count(g)
        if count:
            print(f"  Grade {g}: {count} scenario{'s' if count > 1 else ''}")
    
    f_count = grades.count("F")
    if f_count:
        print(f"\n  ⚠️ {f_count} CRITICAL FAILURE{'S' if f_count > 1 else ''}:")
        for r in results:
            if r.grade == "F":
                print(f"    - {r.scenario}")
    
    print(f"\n  Key insight: cert-bound flags + append-only log = sleeper-proof.")
    print(f"  BFT requires n ≥ 3f+1. Plan committee size accordingly.")
    print("=" * 65)


if __name__ == "__main__":
    run_chaos()
