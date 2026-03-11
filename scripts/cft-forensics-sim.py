#!/usr/bin/env python3
"""
cft-forensics-sim.py — CFT-Forensics simulation for agent accountability.

Inspired by Tang et al (AFT 2024): Byzantine accountability for crash-fault-tolerant
protocols. Most agent systems are CFT (trusted components), not BFT. Add accountability
without 3f+1 overhead via signed message transcripts.

Key insight: if a node breaks protocol and affects safety, the signed transcript
identifies the culprit with cryptographic integrity.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(Enum):
    CLEAN = "clean"
    EQUIVOCATION = "equivocation"      # signed contradictory messages
    OMISSION = "omission"              # failed to forward required message
    FABRICATION = "fabrication"         # sent message not matching protocol


@dataclass
class SignedMessage:
    sender: str
    receiver: str
    round_num: int
    content: str
    timestamp: float
    signature: str = ""
    
    def __post_init__(self):
        payload = f"{self.sender}:{self.receiver}:{self.round_num}:{self.content}:{self.timestamp}"
        self.signature = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Transcript:
    """Per-node signed transcript of all messages sent/received."""
    node_id: str
    sent: list = field(default_factory=list)
    received: list = field(default_factory=list)
    
    def add_sent(self, msg: SignedMessage):
        self.sent.append(msg)
    
    def add_received(self, msg: SignedMessage):
        self.received.append(msg)


class ForensicsAnalyzer:
    """Analyze transcripts to detect Byzantine behavior in CFT setting."""
    
    def __init__(self):
        self.transcripts: dict[str, Transcript] = {}
    
    def add_transcript(self, transcript: Transcript):
        self.transcripts[transcript.node_id] = transcript
    
    def check_equivocation(self) -> list[dict]:
        """Detect if a node sent contradictory messages in the same round."""
        violations = []
        for node_id, transcript in self.transcripts.items():
            by_round = {}
            for msg in transcript.sent:
                key = (msg.round_num, msg.receiver)
                if key not in by_round:
                    by_round[key] = []
                by_round[key].append(msg)
            
            for (rnd, recv), msgs in by_round.items():
                contents = set(m.content for m in msgs)
                if len(contents) > 1:
                    violations.append({
                        "type": "equivocation",
                        "node": node_id,
                        "round": rnd,
                        "receiver": recv,
                        "contradictions": list(contents),
                        "evidence": [m.signature for m in msgs]
                    })
        return violations
    
    def check_omission(self) -> list[dict]:
        """Detect if a node claims to have sent a message that receiver never got."""
        violations = []
        for node_id, transcript in self.transcripts.items():
            for msg in transcript.sent:
                if msg.receiver in self.transcripts:
                    recv_t = self.transcripts[msg.receiver]
                    received_sigs = {m.signature for m in recv_t.received}
                    if msg.signature not in received_sigs:
                        violations.append({
                            "type": "omission",
                            "sender": node_id,
                            "receiver": msg.receiver,
                            "round": msg.round_num,
                            "evidence": msg.signature
                        })
        return violations
    
    def check_fabrication(self, protocol_rules: dict) -> list[dict]:
        """Detect messages that violate protocol rules."""
        violations = []
        for node_id, transcript in self.transcripts.items():
            for msg in transcript.sent:
                if msg.round_num in protocol_rules:
                    allowed = protocol_rules[msg.round_num]
                    if msg.content not in allowed:
                        violations.append({
                            "type": "fabrication",
                            "node": node_id,
                            "round": msg.round_num,
                            "content": msg.content,
                            "allowed": allowed,
                            "evidence": msg.signature
                        })
        return violations
    
    def full_audit(self, protocol_rules: dict = None) -> dict:
        """Run all forensic checks and produce accountability report."""
        equivocations = self.check_equivocation()
        omissions = self.check_omission()
        fabrications = self.check_fabrication(protocol_rules or {})
        
        all_violations = equivocations + omissions + fabrications
        
        # Per-node verdict
        verdicts = {}
        for node_id in self.transcripts:
            node_violations = [v for v in all_violations 
                             if v.get("node") == node_id or v.get("sender") == node_id]
            if not node_violations:
                verdicts[node_id] = Verdict.CLEAN
            else:
                # Most severe violation
                types = {v["type"] for v in node_violations}
                if "equivocation" in types:
                    verdicts[node_id] = Verdict.EQUIVOCATION
                elif "fabrication" in types:
                    verdicts[node_id] = Verdict.FABRICATION
                else:
                    verdicts[node_id] = Verdict.OMISSION
        
        clean = sum(1 for v in verdicts.values() if v == Verdict.CLEAN)
        total = len(verdicts)
        
        return {
            "total_nodes": total,
            "clean_nodes": clean,
            "violations": len(all_violations),
            "equivocations": len(equivocations),
            "omissions": len(omissions),
            "fabrications": len(fabrications),
            "verdicts": {k: v.value for k, v in verdicts.items()},
            "accountability_grade": "A" if clean == total else "B" if clean >= total * 0.8 else "C" if clean >= total * 0.5 else "F",
            "details": all_violations[:5]  # first 5 for readability
        }


def demo():
    analyzer = ForensicsAnalyzer()
    base_t = 1000000.0
    
    # Node A: honest leader
    t_a = Transcript("agent_A")
    t_a.add_sent(SignedMessage("agent_A", "agent_B", 1, "propose:block_42", base_t))
    t_a.add_sent(SignedMessage("agent_A", "agent_C", 1, "propose:block_42", base_t))
    t_a.add_sent(SignedMessage("agent_A", "agent_D", 1, "propose:block_42", base_t))
    
    # Node B: honest follower
    t_b = Transcript("agent_B")
    t_b.add_received(SignedMessage("agent_A", "agent_B", 1, "propose:block_42", base_t))
    t_b.add_sent(SignedMessage("agent_B", "agent_A", 1, "ack:block_42", base_t + 1))
    
    # Node C: EQUIVOCATING — sends different acks to different nodes
    t_c = Transcript("agent_C")
    t_c.add_received(SignedMessage("agent_A", "agent_C", 1, "propose:block_42", base_t))
    t_c.add_sent(SignedMessage("agent_C", "agent_A", 1, "ack:block_42", base_t + 1))
    t_c.add_sent(SignedMessage("agent_C", "agent_A", 1, "ack:block_99", base_t + 1.5))  # equivocation!
    
    # Node D: OMITTING — claims to send but receiver never got it
    t_d = Transcript("agent_D")
    t_d.add_received(SignedMessage("agent_A", "agent_D", 1, "propose:block_42", base_t))
    # Claims to send ack but with wrong signature (simulating omission)
    fake_msg = SignedMessage("agent_D", "agent_A", 1, "ack:block_42", base_t + 2)
    t_d.add_sent(fake_msg)
    # agent_A never received it — omission detected by cross-referencing
    
    # Agent A received B's ack but not D's
    t_a.add_received(SignedMessage("agent_B", "agent_A", 1, "ack:block_42", base_t + 1))
    t_a.add_received(SignedMessage("agent_C", "agent_A", 1, "ack:block_42", base_t + 1))
    # Note: agent_A received C's first ack but not D's
    
    for t in [t_a, t_b, t_c, t_d]:
        analyzer.add_transcript(t)
    
    # Protocol rules: round 1 must be propose or ack
    rules = {1: ["propose:block_42", "ack:block_42"]}
    
    report = analyzer.full_audit(rules)
    
    print("=" * 60)
    print("CFT-FORENSICS — Byzantine Accountability for Agent Protocols")
    print("=" * 60)
    print(f"\nNodes: {report['total_nodes']} | Clean: {report['clean_nodes']} | Violations: {report['violations']}")
    print(f"  Equivocations: {report['equivocations']}")
    print(f"  Omissions: {report['omissions']}")
    print(f"  Fabrications: {report['fabrications']}")
    print(f"\nPer-node verdicts:")
    for node, verdict in report['verdicts'].items():
        marker = "✓" if verdict == "clean" else "✗"
        print(f"  {marker} {node}: {verdict}")
    print(f"\nAccountability Grade: {report['accountability_grade']}")
    
    if report['details']:
        print(f"\nViolation details (first {len(report['details'])}):")
        for v in report['details']:
            print(f"  [{v['type']}] {json.dumps({k: v for k, v in v.items() if k != 'type'}, default=str)[:120]}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Tang et al, AFT 2024):")
    print("  CFT + signed transcripts = accountability at 87.8% throughput.")
    print("  Most agent systems are CFT, not BFT. Don't pay for 3f+1")
    print("  when you can add forensics to f+1.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
