#!/usr/bin/env python3
"""
swim-gossip-sim.py — SWIM gossip protocol simulation for agent trust.

Based on Das, Gupta & Motivala (Cornell 2002): "SWIM: Scalable Weakly-consistent
Infection-style Process Group Membership Protocol"

Key properties:
- O(1) message load per member (independent of group size)
- Constant expected failure detection time
- Piggybacked membership dissemination (logarithmic spread)
- Suspicion mechanism before declaration (reduces false positives)

Agent trust application: SWIM + DKIM + Φ accrual = gossip substrate for
attestation propagation and compromise detection.

Usage: python3 swim-gossip-sim.py
"""

import random
import hashlib
from dataclasses import dataclass, field
from enum import Enum


class MemberState(Enum):
    ALIVE = "alive"
    SUSPECT = "suspect"
    FAILED = "failed"


@dataclass
class GossipMessage:
    """Piggybacked membership update."""
    about: str  # member name
    state: MemberState
    incarnation: int
    timestamp: int


@dataclass
class SwimMember:
    name: str
    state: MemberState = MemberState.ALIVE
    incarnation: int = 0
    membership: dict = field(default_factory=dict)  # name -> (state, incarnation)
    pending_gossip: list = field(default_factory=list)
    messages_sent: int = 0
    messages_received: int = 0
    failed: bool = False  # actual state (ground truth)

    def ping(self, target: 'SwimMember', round_num: int) -> bool:
        """Direct ping with piggybacked gossip."""
        if self.failed or target.failed:
            return False

        self.messages_sent += 1
        target.messages_received += 1

        # Piggyback gossip (up to 3 updates per ping — bounded!)
        gossip_payload = self.pending_gossip[:3]
        self.pending_gossip = self.pending_gossip[3:]

        # Target processes gossip
        for msg in gossip_payload:
            target._process_gossip(msg)

        return True  # ack

    def ping_req(self, intermediary: 'SwimMember', target: 'SwimMember', round_num: int) -> bool:
        """Indirect ping through intermediary (SWIM protocol)."""
        if self.failed or intermediary.failed:
            return False

        self.messages_sent += 1
        intermediary.messages_received += 1

        # Intermediary pings target
        return intermediary.ping(target, round_num)

    def _process_gossip(self, msg: GossipMessage):
        """Process a piggybacked gossip update."""
        current = self.membership.get(msg.about)
        if current is None or msg.incarnation > current[1]:
            self.membership[msg.about] = (msg.state, msg.incarnation)
            # Re-gossip (infection-style)
            self.pending_gossip.append(msg)

    def suspect(self, target_name: str, round_num: int):
        """Mark member as suspected (not yet failed)."""
        self.membership[target_name] = (MemberState.SUSPECT, round_num)
        self.pending_gossip.append(GossipMessage(
            about=target_name,
            state=MemberState.SUSPECT,
            incarnation=round_num,
            timestamp=round_num
        ))

    def declare_failed(self, target_name: str, round_num: int):
        """Declare member as failed after suspicion timeout."""
        self.membership[target_name] = (MemberState.FAILED, round_num)
        self.pending_gossip.append(GossipMessage(
            about=target_name,
            state=MemberState.FAILED,
            incarnation=round_num,
            timestamp=round_num
        ))


class SwimSimulator:
    def __init__(self, n_members: int, k_indirect: int = 3, suspect_timeout: int = 3):
        self.members = [SwimMember(name=f"agent_{i}") for i in range(n_members)]
        self.k_indirect = k_indirect  # indirect probes per round
        self.suspect_timeout = suspect_timeout
        self.round = 0
        self.suspicions: dict = {}  # (detector, target) -> round_suspected

        # Initialize membership lists
        for m in self.members:
            for other in self.members:
                if other.name != m.name:
                    m.membership[other.name] = (MemberState.ALIVE, 0)

    def fail_member(self, index: int):
        """Simulate member failure."""
        self.members[index].failed = True

    def run_round(self) -> dict:
        """Execute one SWIM protocol round."""
        self.round += 1
        events = []

        alive_members = [m for m in self.members if not m.failed]

        for member in alive_members:
            # Pick random target to probe
            targets = [m for m in self.members
                       if m.name != member.name
                       and member.membership.get(m.name, (MemberState.ALIVE,))[0] != MemberState.FAILED]
            if not targets:
                continue

            target = random.choice(targets)

            # Direct ping
            ack = member.ping(target, self.round)

            if not ack:
                # Indirect ping through k random intermediaries
                intermediaries = [m for m in alive_members
                                  if m.name != member.name and m.name != target.name]
                random.shuffle(intermediaries)
                indirect_ack = False

                for inter in intermediaries[:self.k_indirect]:
                    if member.ping_req(inter, target, self.round):
                        indirect_ack = True
                        break

                if not indirect_ack:
                    key = (member.name, target.name)
                    if key not in self.suspicions:
                        # Suspect first
                        member.suspect(target.name, self.round)
                        self.suspicions[key] = self.round
                        events.append(f"SUSPECT: {member.name} suspects {target.name}")
                    elif self.round - self.suspicions[key] >= self.suspect_timeout:
                        # Timeout → declare failed
                        member.declare_failed(target.name, self.round)
                        events.append(f"DECLARE_FAILED: {member.name} declares {target.name} failed")
                        del self.suspicions[key]

        return {
            "round": self.round,
            "events": events,
            "total_messages": sum(m.messages_sent for m in self.members),
            "messages_per_member": sum(m.messages_sent for m in self.members) / len(self.members)
        }

    def detection_status(self) -> dict:
        """Check which alive members have detected each failure."""
        failed = [m for m in self.members if m.failed]
        alive = [m for m in self.members if not m.failed]
        status = {}

        for f in failed:
            detectors = 0
            for a in alive:
                state = a.membership.get(f.name, (MemberState.ALIVE,))[0]
                if state in (MemberState.SUSPECT, MemberState.FAILED):
                    detectors += 1
            status[f.name] = {
                "detected_by": detectors,
                "total_alive": len(alive),
                "coverage": detectors / len(alive) if alive else 0
            }

        return status


def demo():
    print("=" * 60)
    print("SWIM Gossip Protocol for Agent Trust")
    print("Das, Gupta & Motivala (Cornell 2002)")
    print("=" * 60)

    scenarios = [
        {"name": "10 agents, 1 failure", "n": 10, "fail": [3], "rounds": 15},
        {"name": "50 agents, 1 failure", "n": 50, "fail": [17], "rounds": 15},
        {"name": "50 agents, 3 failures", "n": 50, "fail": [5, 22, 41], "rounds": 15},
        {"name": "100 agents, 5 failures", "n": 100, "fail": [10, 30, 50, 70, 90], "rounds": 20},
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")

        sim = SwimSimulator(scenario["n"])

        # Fail members at round 3
        first_detection = {}
        full_detection = {}

        for r in range(1, scenario["rounds"] + 1):
            if r == 3:
                for idx in scenario["fail"]:
                    sim.fail_member(idx)

            result = sim.run_round()

            if r >= 3:
                status = sim.detection_status()
                for fname, info in status.items():
                    if fname not in first_detection and info["coverage"] > 0:
                        first_detection[fname] = r - 3  # rounds after failure
                    if fname not in full_detection and info["coverage"] >= 0.9:
                        full_detection[fname] = r - 3

        # Results
        final_status = sim.detection_status()
        msg_per_member = result["messages_per_member"]

        print(f"Members: {scenario['n']}, Failures: {len(scenario['fail'])}")
        print(f"Messages/member after {scenario['rounds']} rounds: {msg_per_member:.1f}")
        print(f"Messages/member/round: {msg_per_member / scenario['rounds']:.2f}")

        for fname, info in final_status.items():
            fd = first_detection.get(fname, "never")
            full = full_detection.get(fname, "never")
            print(f"  {fname}: {info['coverage']*100:.0f}% detected "
                  f"(first: round +{fd}, 90%: round +{full})")

        # Grade
        avg_coverage = sum(i["coverage"] for i in final_status.values()) / len(final_status) if final_status else 1
        if avg_coverage >= 0.95:
            grade = "A"
        elif avg_coverage >= 0.8:
            grade = "B"
        elif avg_coverage >= 0.5:
            grade = "C"
        else:
            grade = "F"
        print(f"Detection grade: {grade} ({avg_coverage*100:.0f}% avg coverage)")

    # O(1) verification
    print(f"\n{'=' * 60}")
    print("O(1) MESSAGE LOAD VERIFICATION:")
    sizes = [10, 50, 100, 200]
    for n in sizes:
        sim = SwimSimulator(n)
        for _ in range(10):
            sim.run_round()
        mpm = sum(m.messages_sent for m in sim.members) / n / 10
        print(f"  n={n:4d}: {mpm:.2f} messages/member/round")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("SWIM = O(1) message load regardless of group size.")
    print("Piggybacked gossip = logarithmic dissemination.")
    print("Suspicion before declaration = fewer false positives.")
    print("Agent trust: SWIM + DKIM + Φ accrual = gossip substrate.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
