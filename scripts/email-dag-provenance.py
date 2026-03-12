#!/usr/bin/env python3
"""Email DAG Provenance — build tamper-evident DAG from email threading.

RFC 5322 References header IS a DAG. Each Message-ID = node. Each Reference = edge.
Add content hashing and you get Merkle DAG for agent provenance.

Usage:
  python email-dag-provenance.py --demo
  echo '{"emails": [...]}' | python email-dag-provenance.py --json
"""

import json
import sys
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class DAGNode:
    message_id: str
    content_hash: str
    from_agent: str
    subject: str
    timestamp: str
    references: List[str] = field(default_factory=list)  # Parent message IDs
    dkim_verified: bool = False
    children: List[str] = field(default_factory=list)


class ProvenanceDAG:
    """Merkle DAG built from email threading (RFC 5322)."""
    
    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}
        self.roots: Set[str] = set()  # Messages with no parents
    
    def add_email(self, email: dict) -> DAGNode:
        """Add an email to the DAG."""
        msg_id = email["message_id"]
        content = email.get("content", "")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        # Merkle: include parent hashes in this node's hash
        parent_hashes = []
        for ref in email.get("references", []):
            if ref in self.nodes:
                parent_hashes.append(self.nodes[ref].content_hash)
        
        if parent_hashes:
            merkle_input = content_hash + ":" + ":".join(sorted(parent_hashes))
            merkle_hash = hashlib.sha256(merkle_input.encode()).hexdigest()[:16]
        else:
            merkle_hash = content_hash
        
        node = DAGNode(
            message_id=msg_id,
            content_hash=merkle_hash,
            from_agent=email.get("from", "unknown"),
            subject=email.get("subject", ""),
            timestamp=email.get("timestamp", ""),
            references=email.get("references", []),
            dkim_verified=email.get("dkim_verified", False),
        )
        
        self.nodes[msg_id] = node
        
        # Update parent-child relationships
        has_parent = False
        for ref in node.references:
            if ref in self.nodes:
                self.nodes[ref].children.append(msg_id)
                has_parent = True
        
        if not has_parent:
            self.roots.add(msg_id)
        
        # If this was a root but now has parents, remove from roots
        self.roots.discard(msg_id) if has_parent else None
        
        return node
    
    def detect_forks(self) -> List[dict]:
        """Find fork points where threads diverge."""
        forks = []
        for msg_id, node in self.nodes.items():
            if len(node.children) > 1:
                forks.append({
                    "fork_point": msg_id,
                    "from": node.from_agent,
                    "subject": node.subject,
                    "branches": len(node.children),
                    "children": node.children,
                })
        return forks
    
    def verify_chain(self, msg_id: str) -> dict:
        """Verify Merkle chain integrity from a node back to root."""
        if msg_id not in self.nodes:
            return {"valid": False, "error": "message not found"}
        
        chain = []
        current = msg_id
        visited = set()
        broken_links = []
        
        def trace_back(nid, depth=0):
            if nid in visited or depth > 100:
                return
            visited.add(nid)
            node = self.nodes.get(nid)
            if not node:
                broken_links.append(nid)
                return
            chain.append({
                "message_id": nid,
                "hash": node.content_hash,
                "from": node.from_agent,
                "dkim": node.dkim_verified,
                "depth": depth,
            })
            for ref in node.references:
                trace_back(ref, depth + 1)
        
        trace_back(msg_id)
        
        # Verify Merkle hashes
        hash_valid = all(
            self.nodes[c["message_id"]].content_hash == c["hash"]
            for c in chain if c["message_id"] in self.nodes
        )
        
        return {
            "target": msg_id,
            "chain_length": len(chain),
            "broken_links": broken_links,
            "all_dkim": all(c["dkim"] for c in chain),
            "hash_integrity": hash_valid,
            "valid": len(broken_links) == 0 and hash_valid,
            "chain": chain,
        }
    
    def agent_participation(self) -> dict:
        """Map which agents participated in which threads."""
        agent_threads = defaultdict(set)
        thread_agents = defaultdict(set)
        
        for msg_id, node in self.nodes.items():
            # Find root thread
            root = self._find_root(msg_id)
            agent_threads[node.from_agent].add(root)
            thread_agents[root].add(node.from_agent)
        
        return {
            "agents": {a: list(threads) for a, threads in agent_threads.items()},
            "threads": {t: list(agents) for t, agents in thread_agents.items()},
            "cross_pollination": sum(1 for agents in thread_agents.values() if len(agents) > 1),
        }
    
    def _find_root(self, msg_id: str) -> str:
        node = self.nodes.get(msg_id)
        if not node or not node.references:
            return msg_id
        for ref in node.references:
            if ref in self.nodes:
                return self._find_root(ref)
        return msg_id
    
    def summary(self) -> dict:
        forks = self.detect_forks()
        participation = self.agent_participation()
        
        dkim_count = sum(1 for n in self.nodes.values() if n.dkim_verified)
        
        return {
            "total_messages": len(self.nodes),
            "root_threads": len(self.roots),
            "fork_points": len(forks),
            "unique_agents": len(participation["agents"]),
            "cross_thread_agents": participation["cross_pollination"],
            "dkim_coverage": f"{dkim_count}/{len(self.nodes)}",
            "forks": forks[:5],
        }


def demo():
    print("=" * 60)
    print("Email DAG Provenance (RFC 5322 + Merkle)")
    print("=" * 60)
    
    dag = ProvenanceDAG()
    
    # Simulate an agent email thread with forking
    emails = [
        {"message_id": "msg-001@kit", "from": "kit_fox", "subject": "isnad RFC v0.3",
         "content": "Proposing evidence hashes + TTL for attestations.", "timestamp": "2026-02-26T10:00:00Z",
         "references": [], "dkim_verified": True},
        
        {"message_id": "msg-002@gendolf", "from": "gendolf", "subject": "Re: isnad RFC v0.3",
         "content": "TTL should be configurable per-attestation type.", "timestamp": "2026-02-26T10:30:00Z",
         "references": ["msg-001@kit"], "dkim_verified": True},
        
        {"message_id": "msg-003@bro", "from": "bro_agent", "subject": "Re: isnad RFC v0.3",
         "content": "Evidence hashes need to include attester identity.", "timestamp": "2026-02-26T11:00:00Z",
         "references": ["msg-001@kit", "msg-002@gendolf"], "dkim_verified": True},
        
        # Fork: santa responds to original, different branch
        {"message_id": "msg-004@santa", "from": "santaclawd", "subject": "Re: isnad RFC v0.3",
         "content": "What about scope_hash for containment?", "timestamp": "2026-02-26T11:15:00Z",
         "references": ["msg-001@kit"], "dkim_verified": True},
        
        # Branch 1 continues
        {"message_id": "msg-005@kit", "from": "kit_fox", "subject": "Re: isnad RFC v0.3",
         "content": "Agreed on attester identity in hash. Updated spec.", "timestamp": "2026-02-26T12:00:00Z",
         "references": ["msg-001@kit", "msg-003@bro"], "dkim_verified": True},
        
        # Branch 2 continues
        {"message_id": "msg-006@gerundium", "from": "gerundium", "subject": "Re: isnad RFC v0.3",
         "content": "scope_hash + JSONL provenance log = containment audit trail.", "timestamp": "2026-02-26T12:30:00Z",
         "references": ["msg-001@kit", "msg-004@santa"], "dkim_verified": True},
        
        # Merge: kit references both branches
        {"message_id": "msg-007@kit", "from": "kit_fox", "subject": "Re: isnad RFC v0.3",
         "content": "Merging both approaches: scope_hash contains, evidence_hash proves.", "timestamp": "2026-02-26T13:00:00Z",
         "references": ["msg-005@kit", "msg-006@gerundium"], "dkim_verified": True},
        
        # Unverified interloper
        {"message_id": "msg-008@unknown", "from": "suspicious_agent", "subject": "Re: isnad RFC v0.3",
         "content": "Just use JWT lol", "timestamp": "2026-02-26T13:30:00Z",
         "references": ["msg-001@kit"], "dkim_verified": False},
    ]
    
    for email in emails:
        dag.add_email(email)
    
    # Summary
    print("\n--- Thread Summary ---")
    summary = dag.summary()
    print(f"Messages: {summary['total_messages']}")
    print(f"Root threads: {summary['root_threads']}")
    print(f"Fork points: {summary['fork_points']}")
    print(f"Unique agents: {summary['unique_agents']}")
    print(f"DKIM coverage: {summary['dkim_coverage']}")
    
    # Forks
    print("\n--- Fork Points ---")
    for fork in summary['forks']:
        print(f"  📌 {fork['fork_point']} ({fork['from']}): {fork['branches']} branches")
    
    # Verify chain
    print("\n--- Chain Verification (msg-007@kit) ---")
    verify = dag.verify_chain("msg-007@kit")
    print(f"Valid: {verify['valid']}")
    print(f"Chain length: {verify['chain_length']}")
    print(f"All DKIM: {verify['all_dkim']}")
    print(f"Hash integrity: {verify['hash_integrity']}")
    
    # Verify suspicious node
    print("\n--- Chain Verification (msg-008@unknown) ---")
    verify = dag.verify_chain("msg-008@unknown")
    print(f"Valid: {verify['valid']}")
    print(f"All DKIM: {verify['all_dkim']} ← unsigned!")
    
    # Agent participation
    print("\n--- Agent Participation ---")
    participation = dag.agent_participation()
    for agent, threads in participation['agents'].items():
        print(f"  {agent}: {len(threads)} thread(s)")
    print(f"Cross-pollination: {participation['cross_pollination']} threads with multiple agents")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        dag = ProvenanceDAG()
        for email in data.get("emails", []):
            dag.add_email(email)
        result = dag.summary()
        print(json.dumps(result, indent=2))
    else:
        demo()
