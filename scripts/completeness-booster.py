#!/usr/bin/env python3
"""completeness-booster.py — Chandra-Toueg completeness boosting for agent trust.

Simulates weak→strong completeness boosting: gossip suspicions among monitors,
let alleged corpse speak for itself. Preserves accuracy while achieving
universal failure detection.

Based on Chandra & Toueg (JACM 1996), §3: Boosting Completeness.

Usage:
    python3 completeness-booster.py [--agents N] [--faulty F] [--rounds R]
"""

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Set, List, Tuple


@dataclass
class Agent:
    """Agent with local failure detector."""
    id: str
    alive: bool = True
    suspects: Set[str] = field(default_factory=set)
    # Weak detector: only SOME agents detect failures
    weak_detector_targets: Set[str] = field(default_factory=set)
    messages_sent: int = 0
    messages_received: int = 0


def simulate_boosting(n_agents: int, n_faulty: int, n_rounds: int, 
                      verbose: bool = False) -> dict:
    """Simulate completeness boosting from weak to strong."""
    agents = {f"agent_{i}": Agent(id=f"agent_{i}") for i in range(n_agents)}
    agent_ids = list(agents.keys())
    
    # Kill some agents
    faulty_ids = random.sample(agent_ids, min(n_faulty, n_agents - 1))
    for fid in faulty_ids:
        agents[fid].alive = False
    
    alive_ids = [a for a in agent_ids if agents[a].alive]
    
    # Weak completeness: each faulty process suspected by SOME alive process
    # (not all — that would be strong completeness)
    for fid in faulty_ids:
        # Only 1-2 alive agents initially detect the failure
        detectors = random.sample(alive_ids, min(2, len(alive_ids)))
        for did in detectors:
            agents[did].weak_detector_targets.add(fid)
            agents[did].suspects.add(fid)
    
    # Track convergence
    rounds_to_strong = None
    history = []
    
    for round_num in range(n_rounds):
        # Phase 1: gossip suspicions
        messages_this_round = []
        for aid in alive_ids:
            agent = agents[aid]
            # Send my suspicions to all other alive agents
            for target in alive_ids:
                if target != aid:
                    messages_this_round.append((aid, target, agent.suspects.copy()))
                    agent.messages_sent += 1
        
        # Phase 2: receive and update
        for sender, receiver, suspicions in messages_this_round:
            agents[receiver].messages_received += 1
            for suspect in suspicions:
                if suspect != receiver:  # Don't suspect myself based on gossip
                    agents[receiver].suspects.add(suspect)
                else:
                    # Corpse speaks: "I'm alive" — receiver IS the alleged corpse
                    # Since receiver is processing this, it's alive
                    # Remove self from others' suspicion via next round gossip
                    pass
        
        # Phase 3: alive agents clear themselves from others' suspect lists
        # "let the alleged corpse speak for itself"
        for aid in alive_ids:
            for other_id in alive_ids:
                if other_id != aid and aid in agents[other_id].suspects:
                    # Agent aid is alive and communicating → un-suspect
                    agents[other_id].suspects.discard(aid)
        
        # Check strong completeness
        strong_complete = all(
            all(fid in agents[aid].suspects for aid in alive_ids)
            for fid in faulty_ids
        )
        
        # Check accuracy preserved (no alive agent suspected)
        accuracy_preserved = all(
            all(aid not in agents[other].suspects for other in alive_ids if other != aid)
            for aid in alive_ids
        )
        
        detection_rates = {}
        for fid in faulty_ids:
            detected_by = sum(1 for aid in alive_ids if fid in agents[aid].suspects)
            detection_rates[fid] = detected_by / len(alive_ids)
        
        round_state = {
            "round": round_num + 1,
            "strong_completeness": strong_complete,
            "accuracy_preserved": accuracy_preserved,
            "avg_detection": sum(detection_rates.values()) / max(len(detection_rates), 1),
            "false_positives": sum(
                1 for aid in alive_ids 
                for other in alive_ids 
                if other != aid and other in agents[aid].suspects
            )
        }
        history.append(round_state)
        
        if verbose:
            print(f"  Round {round_num+1}: detection={round_state['avg_detection']:.1%}, "
                  f"FP={round_state['false_positives']}, "
                  f"strong={'✅' if strong_complete else '❌'}, "
                  f"accurate={'✅' if accuracy_preserved else '❌'}")
        
        if strong_complete and rounds_to_strong is None:
            rounds_to_strong = round_num + 1
    
    total_messages = sum(a.messages_sent for a in agents.values())
    
    return {
        "config": {
            "agents": n_agents,
            "faulty": n_faulty,
            "rounds": n_rounds,
        },
        "results": {
            "rounds_to_strong_completeness": rounds_to_strong,
            "final_strong_completeness": history[-1]["strong_completeness"],
            "final_accuracy_preserved": history[-1]["accuracy_preserved"],
            "final_avg_detection": history[-1]["avg_detection"],
            "total_messages": total_messages,
            "messages_per_round": total_messages / n_rounds,
            "false_positives_final": history[-1]["false_positives"],
        },
        "grade": grade_result(rounds_to_strong, history[-1]),
        "history": history,
    }


def grade_result(rounds_to_strong, final_state) -> str:
    if rounds_to_strong == 1 and final_state["accuracy_preserved"]:
        return "A"
    elif rounds_to_strong is not None and rounds_to_strong <= 3 and final_state["accuracy_preserved"]:
        return "B"
    elif rounds_to_strong is not None and final_state["accuracy_preserved"]:
        return "C"
    elif rounds_to_strong is not None:
        return "D"
    else:
        return "F"


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("COMPLETENESS BOOSTING SIMULATOR")
    print("Chandra & Toueg (JACM 1996) §3")
    print("=" * 60)
    
    scenarios = [
        ("Small network (5 agents, 1 faulty)", 5, 1, 5),
        ("Medium network (20 agents, 3 faulty)", 20, 3, 5),
        ("Large network (50 agents, 10 faulty)", 50, 10, 8),
        ("Adversarial (10 agents, 4 faulty, f < n/2)", 10, 4, 5),
    ]
    
    for name, n, f, r in scenarios:
        print(f"\n--- {name} ---")
        result = simulate_boosting(n, f, r, verbose=True)
        res = result["results"]
        print(f"  → Grade {result['grade']}: "
              f"strong in {res['rounds_to_strong_completeness']} rounds, "
              f"{res['total_messages']} messages, "
              f"accuracy {'preserved' if res['final_accuracy_preserved'] else 'BROKEN'}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Gossip suspicions + corpse speaks = weak→strong")
    print("completeness WITHOUT breaking accuracy. O(n²) messages/round.")
    print("Agent trust: false positive correction is the hard part.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Completeness boosting simulator")
    parser.add_argument("--agents", type=int, default=10)
    parser.add_argument("--faulty", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    else:
        result = simulate_boosting(args.agents, args.faulty, args.rounds, verbose=True)
        if args.json:
            # Remove history for compact output
            result.pop("history", None)
            print(json.dumps(result, indent=2))
        else:
            print(f"\nGrade: {result['grade']}")
