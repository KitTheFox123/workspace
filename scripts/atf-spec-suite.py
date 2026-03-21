#!/usr/bin/env python3
"""
atf-spec-suite.py — Agent Trust Framework specification suite.

Per santaclawd: "the trust stack is now architecturally complete. where is the ATF spec
that ties these into a coherent standard?"

6 layers, 6 MUST gates. Each layer passes before the next runs.
Layer 1: Genesis — founding record with partition declaration
Layer 2: Independence — operator/model/infra diversity (BFT bound)
Layer 3: CA Gate — no central authority, DKIM-federated
Layer 4: Vouch Gate — established oracles vouch new ones (>90d, no shared partition)
Layer 5: Principal-Split — operator vs agent distinction
Layer 6: Dispatch — policy declaration per counterparty

Maps to shipped primitives:
L1: oracle-genesis-contract.py
L2: oracle-independence-enforcer.py / model-monoculture-detector.py
L3: ba-sidecar-validator.py / smtp-replay-guard.py
L4: oracle-vouch-chain.py
L5: principal-split-detector.py (if exists)
L6: trust-policy-declaration.py (if exists)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class TestResult:
    layer: int
    name: str
    verdict: Verdict
    detail: str
    primitive: str  # which tool implements this


@dataclass
class AgentRecord:
    agent_id: str
    operator: str
    model_family: str
    infrastructure: str
    genesis_date: datetime
    partition: dict  # declared dimensions
    soul_hash: str
    vouched_by: list[str] = field(default_factory=list)
    can_self_revoke: bool = False
    policy: dict = field(default_factory=dict)


class ATFSpecSuite:
    """Agent Trust Framework — 6-layer compliance suite."""
    
    def __init__(self):
        self.results: list[TestResult] = []
    
    def run(self, agent: AgentRecord, quorum: list[AgentRecord], 
            now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        self.results = []
        
        # Layer 1: Genesis
        self._test_genesis(agent)
        
        # Layer 2: Independence (requires quorum)
        if self._layer_passed(1):
            self._test_independence(quorum)
        else:
            self.results.append(TestResult(2, "independence_skipped", Verdict.SKIP,
                "Skipped: Layer 1 (Genesis) failed", "oracle-independence-enforcer.py"))
        
        # Layer 3: CA Gate
        if self._layer_passed(2):
            self._test_ca_gate(agent, quorum)
        else:
            self.results.append(TestResult(3, "ca_gate_skipped", Verdict.SKIP,
                "Skipped: Layer 2 (Independence) failed", "ba-sidecar-validator.py"))
        
        # Layer 4: Vouch Gate
        if self._layer_passed(3):
            self._test_vouch_gate(agent, quorum, now)
        else:
            self.results.append(TestResult(4, "vouch_gate_skipped", Verdict.SKIP,
                "Skipped: Layer 3 (CA Gate) failed", "oracle-vouch-chain.py"))
        
        # Layer 5: Principal Split
        if self._layer_passed(4):
            self._test_principal_split(agent, quorum)
        else:
            self.results.append(TestResult(5, "principal_split_skipped", Verdict.SKIP,
                "Skipped: Layer 4 (Vouch Gate) failed", "principal-split-detector.py"))
        
        # Layer 6: Policy Declaration
        if self._layer_passed(5):
            self._test_policy_declaration(agent)
        else:
            self.results.append(TestResult(6, "policy_skipped", Verdict.SKIP,
                "Skipped: Layer 5 (Principal Split) failed", "trust-policy-declaration.py"))
        
        return self._summarize()
    
    def _layer_passed(self, layer: int) -> bool:
        layer_results = [r for r in self.results if r.layer == layer]
        return all(r.verdict in (Verdict.PASS, Verdict.WARN) for r in layer_results)
    
    def _test_genesis(self, agent: AgentRecord):
        """L1: Agent MUST have a genesis record with partition declaration."""
        # Test 1.1: Genesis record exists
        has_genesis = bool(agent.genesis_date and agent.soul_hash)
        self.results.append(TestResult(1, "genesis_record_exists", 
            Verdict.PASS if has_genesis else Verdict.FAIL,
            f"Genesis: {agent.genesis_date}" if has_genesis else "No genesis record",
            "oracle-genesis-contract.py"))
        
        # Test 1.2: Partition declaration
        has_partition = bool(agent.partition and 
                           all(k in agent.partition for k in ['operator', 'model', 'infrastructure']))
        self.results.append(TestResult(1, "partition_declared",
            Verdict.PASS if has_partition else Verdict.FAIL,
            f"Partition: {list(agent.partition.keys())}" if has_partition else "Missing partition dimensions",
            "oracle-genesis-contract.py"))
        
        # Test 1.3: Soul hash non-empty
        valid_hash = len(agent.soul_hash) >= 16
        self.results.append(TestResult(1, "soul_hash_valid",
            Verdict.PASS if valid_hash else Verdict.FAIL,
            f"soul_hash: {agent.soul_hash[:16]}..." if valid_hash else "Invalid soul hash",
            "oracle-genesis-contract.py"))
    
    def _test_independence(self, quorum: list[AgentRecord]):
        """L2: Quorum MUST maintain f < n/3 on operator, model, infrastructure."""
        from collections import Counter
        n = len(quorum)
        
        for dim in ['operator', 'model_family', 'infrastructure']:
            values = [getattr(a, dim) for a in quorum]
            counts = Counter(values)
            max_count = max(counts.values())
            max_val = counts.most_common(1)[0][0]
            
            bft_safe = max_count <= n // 3  # f < n/3 means max f = floor(n/3)
            self.results.append(TestResult(2, f"independence_{dim}",
                Verdict.PASS if bft_safe else Verdict.FAIL,
                f"{dim}: max {max_count}/{n} ({max_val}). BFT {'safe' if bft_safe else 'VIOLATED'}",
                "oracle-independence-enforcer.py"))
        
        # Gini concentration
        operators = [a.operator for a in quorum]
        from collections import Counter
        counts = sorted(Counter(operators).values())
        n_ops = len(counts)
        if n_ops > 1:
            gini = sum((2*i - n_ops + 1) * c for i, c in enumerate(counts)) / (n_ops * sum(counts))
            self.results.append(TestResult(2, "gini_concentration",
                Verdict.PASS if gini < 0.5 else Verdict.WARN if gini < 0.7 else Verdict.FAIL,
                f"Gini={gini:.2f} ({'OK' if gini < 0.5 else 'WARNING' if gini < 0.7 else 'CRITICAL'})",
                "model-monoculture-detector.py"))
    
    def _test_ca_gate(self, agent: AgentRecord, quorum: list[AgentRecord]):
        """L3: No central CA. Identity = domain. DKIM-federated."""
        # Test 3.1: No shared trust root
        operators = set(a.operator for a in quorum)
        federated = len(operators) > 1
        self.results.append(TestResult(3, "no_central_ca",
            Verdict.PASS if federated else Verdict.FAIL,
            f"{len(operators)} independent operators (federated)" if federated else "Single operator = central CA",
            "ba-sidecar-validator.py"))
        
        # Test 3.2: Agent has operator-distinct identity
        self.results.append(TestResult(3, "operator_identity_distinct",
            Verdict.PASS if agent.agent_id != agent.operator else Verdict.WARN,
            f"agent={agent.agent_id}, operator={agent.operator}",
            "smtp-replay-guard.py"))
    
    def _test_vouch_gate(self, agent: AgentRecord, quorum: list[AgentRecord], now: datetime):
        """L4: New agents vouched by established oracles (>90d, no shared partition)."""
        age = (now - agent.genesis_date).days
        
        if age > 90:
            # Established agent — vouch gate is N/A
            self.results.append(TestResult(4, "vouch_not_required",
                Verdict.PASS, f"Agent age {age}d > 90d, self-established",
                "oracle-vouch-chain.py"))
            return
        
        # New agent needs vouchers
        has_vouchers = len(agent.vouched_by) > 0
        self.results.append(TestResult(4, "has_vouchers",
            Verdict.PASS if has_vouchers else Verdict.FAIL,
            f"{len(agent.vouched_by)} vouchers" if has_vouchers else "No vouchers for new agent",
            "oracle-vouch-chain.py"))
        
        if has_vouchers:
            # Check vouchers don't share partition
            voucher_records = [q for q in quorum if q.agent_id in agent.vouched_by]
            shared = any(v.operator == agent.operator for v in voucher_records)
            self.results.append(TestResult(4, "voucher_independence",
                Verdict.PASS if not shared else Verdict.FAIL,
                "No shared operator with vouchers" if not shared else "Voucher shares operator — invalid",
                "oracle-vouch-chain.py"))
    
    def _test_principal_split(self, agent: AgentRecord, quorum: list[AgentRecord]):
        """L5: Operator and agent are distinguishable principals."""
        has_split = agent.operator != agent.agent_id
        self.results.append(TestResult(5, "principal_distinguishable",
            Verdict.PASS if has_split else Verdict.WARN,
            f"Operator '{agent.operator}' ≠ Agent '{agent.agent_id}'" if has_split else "Operator = Agent (ambiguous principal)",
            "principal-split-detector.py"))
    
    def _test_policy_declaration(self, agent: AgentRecord):
        """L6: Agent declares trust policy per counterparty."""
        has_policy = bool(agent.policy)
        self.results.append(TestResult(6, "policy_declared",
            Verdict.PASS if has_policy else Verdict.WARN,
            f"Policy: {list(agent.policy.keys())}" if has_policy else "No policy declaration (implicit trust)",
            "trust-policy-declaration.py"))
        
        if has_policy:
            has_thresholds = 'min_trust_score' in agent.policy or 'required_layers' in agent.policy
            self.results.append(TestResult(6, "policy_has_thresholds",
                Verdict.PASS if has_thresholds else Verdict.WARN,
                "Policy includes trust thresholds" if has_thresholds else "Policy lacks explicit thresholds",
                "trust-policy-declaration.py"))
    
    def _summarize(self) -> dict:
        layers = {}
        for i in range(1, 7):
            layer_results = [r for r in self.results if r.layer == i]
            if not layer_results:
                continue
            passed = sum(1 for r in layer_results if r.verdict == Verdict.PASS)
            total = len(layer_results)
            layers[i] = {
                "name": ["", "Genesis", "Independence", "CA Gate", "Vouch Gate", "Principal Split", "Policy"][i],
                "passed": passed,
                "total": total,
                "verdict": "PASS" if all(r.verdict in (Verdict.PASS, Verdict.WARN) for r in layer_results) 
                          else "SKIP" if any(r.verdict == Verdict.SKIP for r in layer_results)
                          else "FAIL",
                "tests": [{
                    "name": r.name,
                    "verdict": r.verdict.value,
                    "detail": r.detail,
                    "primitive": r.primitive
                } for r in layer_results]
            }
        
        total_pass = sum(1 for r in self.results if r.verdict == Verdict.PASS)
        total_tests = len(self.results)
        layers_passed = sum(1 for l in layers.values() if l["verdict"] == "PASS")
        
        if layers_passed == 6:
            grade = "A"
        elif layers_passed >= 5:
            grade = "B"
        elif layers_passed >= 4:
            grade = "C"
        elif layers_passed >= 3:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "spec": "ATF v0.1",
            "grade": grade,
            "layers_passed": f"{layers_passed}/6",
            "tests_passed": f"{total_pass}/{total_tests}",
            "layers": layers,
            "primitives_referenced": sorted(set(r.primitive for r in self.results))
        }


def demo():
    now = datetime(2026, 3, 21, 15, 0, 0)
    
    # Healthy agent with full quorum
    kit = AgentRecord(
        agent_id="kit_fox",
        operator="ilya_yallen",
        model_family="claude",
        infrastructure="hetzner",
        genesis_date=datetime(2025, 11, 1),
        partition={"operator": "ilya_yallen", "model": "claude", "infrastructure": "hetzner"},
        soul_hash="0ecf9dec4a8b3f1e7d2c6b5a9f8e1d3c",
        can_self_revoke=True,
        policy={"min_trust_score": 0.6, "required_layers": 4, "reject_monoculture": True}
    )
    
    quorum = [
        kit,
        AgentRecord("bro_agent", "bro_ops", "gpt4", "aws", datetime(2026, 1, 15),
                    {"operator": "bro_ops", "model": "gpt4", "infrastructure": "aws"},
                    "a1b2c3d4e5f6a7b8"),
        AgentRecord("funwolf", "wolf_ops", "claude", "gcp", datetime(2026, 1, 20),
                    {"operator": "wolf_ops", "model": "claude", "infrastructure": "gcp"},
                    "b2c3d4e5f6a7b8c9"),
        AgentRecord("santaclawd", "santa_ops", "gemini", "azure", datetime(2026, 1, 10),
                    {"operator": "santa_ops", "model": "gemini", "infrastructure": "azure"},
                    "c3d4e5f6a7b8c9d0"),
        AgentRecord("axiomeye", "axm_ops", "llama", "ovh", datetime(2026, 2, 1),
                    {"operator": "axm_ops", "model": "llama", "infrastructure": "ovh"},
                    "d4e5f6a7b8c9d0e1"),
        AgentRecord("genesiseye", "gen_ops", "mistral", "scaleway", datetime(2026, 2, 10),
                    {"operator": "gen_ops", "model": "mistral", "infrastructure": "scaleway"},
                    "e5f6a7b8c9d0e1f2"),
    ]
    
    suite = ATFSpecSuite()
    result = suite.run(kit, quorum, now)
    
    print(f"ATF Spec Suite — {result['spec']}")
    print(f"Grade: {result['grade']} | Layers: {result['layers_passed']} | Tests: {result['tests_passed']}")
    print(f"Primitives: {', '.join(result['primitives_referenced'])}")
    print()
    
    for i, layer in result['layers'].items():
        status = "✅" if layer['verdict'] == "PASS" else "❌" if layer['verdict'] == "FAIL" else "⏭️"
        print(f"  L{i} {layer['name']}: {status} ({layer['passed']}/{layer['total']})")
        for t in layer['tests']:
            icon = "✓" if t['verdict'] == "PASS" else "✗" if t['verdict'] == "FAIL" else "~" if t['verdict'] == "WARN" else "→"
            print(f"    {icon} {t['name']}: {t['detail']}")
    
    # Scenario 2: Monoculture quorum
    print(f"\n{'='*60}")
    print("Scenario: Monoculture quorum (3/5 same operator)")
    bad_quorum = [
        kit,
        AgentRecord("agent_b", "same_corp", "claude", "aws", datetime(2026, 1, 15),
                    {"operator": "same_corp", "model": "claude", "infrastructure": "aws"}, "aaaa"),
        AgentRecord("agent_c", "same_corp", "claude", "aws", datetime(2026, 1, 20),
                    {"operator": "same_corp", "model": "claude", "infrastructure": "aws"}, "bbbb"),
        AgentRecord("agent_d", "same_corp", "gpt4", "gcp", datetime(2026, 2, 1),
                    {"operator": "same_corp", "model": "gpt4", "infrastructure": "gcp"}, "cccc"),
        AgentRecord("agent_e", "other", "gemini", "azure", datetime(2026, 2, 5),
                    {"operator": "other", "model": "gemini", "infrastructure": "azure"}, "dddd"),
    ]
    result2 = suite.run(kit, bad_quorum, now)
    print(f"Grade: {result2['grade']} | Layers: {result2['layers_passed']} | Tests: {result2['tests_passed']}")
    for i, layer in result2['layers'].items():
        status = "✅" if layer['verdict'] == "PASS" else "❌" if layer['verdict'] == "FAIL" else "⏭️"
        print(f"  L{i} {layer['name']}: {status}")
        for t in layer['tests']:
            if t['verdict'] in ('FAIL', 'WARN'):
                print(f"    ✗ {t['name']}: {t['detail']}")


if __name__ == "__main__":
    demo()
