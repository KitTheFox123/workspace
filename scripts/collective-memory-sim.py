#!/usr/bin/env python3
"""
collective-memory-sim.py — Socially shared retrieval-induced forgetting for agents.

Maps SS-RIF (Cuc, Koppel & Hirst 2007, JEP:General) to multi-agent memory systems.
Core finding: when one person selectively retrieves shared memories in conversation,
LISTENERS also forget the non-retrieved related items. Conversation shapes what
groups remember AND forget — without anyone intending to suppress information.

ATF parallel: agents sharing attestation histories in gossip protocols undergo
the same effect. Discussing some attestations makes others less accessible.
This is a feature (memory curation) AND a vulnerability (coordinated forgetting).

Three mechanisms modeled:
1. RETRIEVAL_PRACTICE — Discussing item X strengthens X for all participants
2. INHIBITION — Related-but-unmentioned items Y,Z become LESS accessible
3. CONVERGENCE — Group memory converges toward discussed subset

Sources:
- Cuc, Koppel & Hirst (2007, JEP:General): SS-RIF in personal autobiographical memory
- Hirst & Echterhoff (2012, Annual Review Psychology): Collective memory formation
- Luhmann (2012) via Ferraro (2023, PMC10603192): Schemas as instruments of forgetting
- Stone, Coman & Brown (2012): SS-RIF in social networks, group membership moderates

Kit 🦊 — 2026-03-27
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MemoryItem:
    id: str
    category: str  # e.g., "attestation", "receipt", "gossip"
    content: str
    strength: float = 1.0  # 0.0 = forgotten, 1.0 = vivid
    retrieved_count: int = 0
    suppressed_by: list = field(default_factory=list)


@dataclass
class Agent:
    name: str
    memories: dict = field(default_factory=dict)  # id -> MemoryItem
    conversations: int = 0

    def add_memory(self, item: MemoryItem):
        self.memories[item.id] = MemoryItem(
            id=item.id, category=item.category,
            content=item.content, strength=item.strength
        )

    def retrieve(self, item_id: str, boost: float = 0.2) -> Optional[MemoryItem]:
        """Retrieval practice: strengthens target item."""
        if item_id in self.memories:
            mem = self.memories[item_id]
            mem.strength = min(1.0, mem.strength + boost)
            mem.retrieved_count += 1
            return mem
        return None

    def inhibit_related(self, retrieved_id: str, inhibition: float = 0.15):
        """
        SS-RIF: retrieving one item from a category inhibits
        related items in the same category.

        Cuc et al (2007): listeners showed same forgetting as speakers.
        The inhibition is automatic, not intentional.
        """
        if retrieved_id not in self.memories:
            return
        category = self.memories[retrieved_id].category
        for mid, mem in self.memories.items():
            if mid != retrieved_id and mem.category == category:
                mem.strength = max(0.0, mem.strength - inhibition)
                if retrieved_id not in mem.suppressed_by:
                    mem.suppressed_by.append(retrieved_id)

    def accessible_memories(self, threshold: float = 0.3) -> list:
        """Items above retrieval threshold."""
        return [m for m in self.memories.values() if m.strength >= threshold]


class CollectiveMemorySim:
    """
    Simulates SS-RIF across a group of agents sharing memories.

    Key insight from Hirst & Echterhoff (2012): collective memory
    is not just shared individual memories — it's shaped by what
    gets DISCUSSED. Conversation is a selection mechanism.

    Luhmann/Ferraro (2023): "Schemas are instruments of forgetting."
    Gossip protocols are schemas — they determine what gets transmitted
    and what gets left behind.
    """

    def __init__(self, agents: list[Agent], shared_items: list[MemoryItem]):
        self.agents = {a.name: a for a in agents}
        self.shared_items = shared_items
        self.conversation_log = []

        # Give all agents the shared memories
        for agent in agents:
            for item in shared_items:
                agent.add_memory(item)

    def conversation(self, speaker_name: str, listener_names: list[str],
                     discussed_ids: list[str],
                     retrieval_boost: float = 0.2,
                     inhibition_rate: float = 0.15):
        """
        Simulate a conversation where speaker discusses specific items.

        SS-RIF: both speaker AND listeners experience:
        - Strengthening of discussed items (retrieval practice)
        - Weakening of related-but-undiscussed items (inhibition)

        Stone et al (2012): effect is STRONGER when participants
        share group identity. Agent-to-agent = strong identity bond.
        """
        speaker = self.agents[speaker_name]
        listeners = [self.agents[n] for n in listener_names]
        all_participants = [speaker] + listeners

        for participant in all_participants:
            participant.conversations += 1
            for did in discussed_ids:
                # Retrieval practice effect
                participant.retrieve(did, boost=retrieval_boost)
                # Inhibition of related items (SS-RIF)
                participant.inhibit_related(did, inhibition=inhibition_rate)

        self.conversation_log.append({
            "speaker": speaker_name,
            "listeners": listener_names,
            "discussed": discussed_ids,
            "boost": retrieval_boost,
            "inhibition": inhibition_rate
        })

    def memory_convergence(self) -> dict:
        """
        Measure how much group memory has converged.

        Hirst & Echterhoff: convergence = group remembers same subset.
        High convergence after conversation = collective memory formed.
        """
        # For each item, compute variance in strength across agents
        convergence = {}
        for item in self.shared_items:
            strengths = []
            for agent in self.agents.values():
                if item.id in agent.memories:
                    strengths.append(agent.memories[item.id].strength)
            if strengths:
                mean = sum(strengths) / len(strengths)
                variance = sum((s - mean) ** 2 for s in strengths) / len(strengths)
                convergence[item.id] = {
                    "mean_strength": round(mean, 3),
                    "variance": round(variance, 4),
                    "status": "REMEMBERED" if mean > 0.5 else "FADING" if mean > 0.2 else "FORGOTTEN"
                }
        return convergence

    def report(self) -> dict:
        convergence = self.memory_convergence()
        remembered = sum(1 for v in convergence.values() if v["status"] == "REMEMBERED")
        forgotten = sum(1 for v in convergence.values() if v["status"] == "FORGOTTEN")
        fading = sum(1 for v in convergence.values() if v["status"] == "FADING")

        return {
            "agents": len(self.agents),
            "total_items": len(self.shared_items),
            "conversations": len(self.conversation_log),
            "collective_memory": {
                "remembered": remembered,
                "fading": fading,
                "forgotten": forgotten,
                "convergence_ratio": round(remembered / len(self.shared_items), 3) if self.shared_items else 0
            },
            "item_details": convergence,
            "per_agent": {
                name: {
                    "accessible": len(a.accessible_memories()),
                    "total": len(a.memories),
                    "conversations": a.conversations
                }
                for name, a in self.agents.items()
            },
            "insight": (
                "Cuc et al (2007): SS-RIF — listeners forget what speakers don't mention. "
                "Conversation is a selection mechanism for collective memory. "
                "Agent gossip protocols do the same: discussed attestations strengthen, "
                "undiscussed ones fade. This is memory curation via social interaction — "
                "a feature when intentional, a vulnerability when exploited."
            )
        }


def demo():
    """Three scenarios demonstrating SS-RIF in agent memory."""

    print("=" * 60)
    print("SCENARIO 1: Selective gossip → collective forgetting")
    print("=" * 60)

    # 3 agents share 6 attestation memories (2 categories × 3 items)
    items = [
        MemoryItem("att_1", "attestation", "alice attested bob (WRITE, 0.8)"),
        MemoryItem("att_2", "attestation", "alice attested carol (READ, 0.9)"),
        MemoryItem("att_3", "attestation", "alice attested dave (TRANSFER, 0.3)"),
        MemoryItem("rec_1", "receipt", "bob receipt: code review completed"),
        MemoryItem("rec_2", "receipt", "carol receipt: data migration"),
        MemoryItem("rec_3", "receipt", "dave receipt: key rotation failed"),
    ]

    agents = [Agent("kit"), Agent("funwolf"), Agent("santaclawd")]
    sim = CollectiveMemorySim(agents, items)

    # Kit discusses att_1 and rec_1 repeatedly (the "safe" memories)
    # att_3 and rec_3 (the problematic ones) never get discussed
    for _ in range(5):
        sim.conversation("kit", ["funwolf", "santaclawd"],
                        ["att_1", "rec_1"])

    result = sim.report()
    print(json.dumps(result, indent=2))

    # att_1 and rec_1 should be REMEMBERED, att_3 and rec_3 should be FADING/FORGOTTEN
    assert result["item_details"]["att_1"]["status"] == "REMEMBERED"
    assert result["item_details"]["rec_1"]["status"] == "REMEMBERED"
    assert result["item_details"]["att_3"]["status"] in ("FADING", "FORGOTTEN")
    assert result["item_details"]["rec_3"]["status"] in ("FADING", "FORGOTTEN")
    print("✓ PASSED — selective discussion → collective forgetting of undiscussed items\n")

    print("=" * 60)
    print("SCENARIO 2: Diverse conversation → balanced memory")
    print("=" * 60)

    agents2 = [Agent("alice"), Agent("bob"), Agent("carol")]
    sim2 = CollectiveMemorySim(agents2, items)

    # Each agent discusses DIFFERENT items — balanced coverage
    sim2.conversation("alice", ["bob", "carol"], ["att_1", "att_2"])
    sim2.conversation("bob", ["alice", "carol"], ["att_3", "rec_1"])
    sim2.conversation("carol", ["alice", "bob"], ["rec_2", "rec_3"])

    result2 = sim2.report()
    print(json.dumps(result2, indent=2))

    remembered2 = result2["collective_memory"]["remembered"]
    assert remembered2 >= 4, f"Expected >=4 remembered, got {remembered2}"
    print("✓ PASSED — diverse conversation preserves broader memory\n")

    print("=" * 60)
    print("SCENARIO 3: Adversarial forgetting (coordinated SS-RIF)")
    print("=" * 60)

    agents3 = [Agent("honest"), Agent("adversary_1"), Agent("adversary_2")]
    items3 = [
        MemoryItem("evidence_good", "evidence", "agent passed audit"),
        MemoryItem("evidence_bad", "evidence", "agent failed key rotation"),
        MemoryItem("evidence_fraud", "evidence", "agent submitted forged receipt"),
    ]
    sim3 = CollectiveMemorySim(agents3, items3)

    # Adversaries repeatedly discuss ONLY the good evidence
    # Goal: make group forget the bad evidence via SS-RIF
    for _ in range(8):
        sim3.conversation("adversary_1", ["honest", "adversary_2"],
                         ["evidence_good"])
        sim3.conversation("adversary_2", ["honest", "adversary_1"],
                         ["evidence_good"])

    result3 = sim3.report()
    print(json.dumps(result3, indent=2))

    # Good evidence should be strong, bad/fraud should be suppressed
    assert result3["item_details"]["evidence_good"]["status"] == "REMEMBERED"
    assert result3["item_details"]["evidence_fraud"]["status"] in ("FADING", "FORGOTTEN")
    print("✓ PASSED — coordinated SS-RIF suppresses inconvenient evidence")
    print("  DEFENSE: append-only receipt logs resist social forgetting\n")

    print("ALL 3 SCENARIOS PASSED ✓")
    print("\nKey insight: gossip protocols are memory selection mechanisms.")
    print("What gets discussed gets remembered. What doesn't, fades.")
    print("Append-only logs are the defense against coordinated forgetting.")


if __name__ == "__main__":
    demo()
