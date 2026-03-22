#!/usr/bin/env python3
"""instruction-provenance-tracker.py — Track provenance of identity file instructions.

Every instruction in SOUL.md / HEARTBEAT.md / AGENTS.md has a history:
- When was it added?
- What failure prompted it?
- Is that failure still possible?
- When was it last tested?

Without this, identity files accumulate vestigial instructions —
rules that addressed past problems but no longer serve a purpose.

Biology parallel: recurrent laryngeal nerve, human appendix.
Organizational parallel: Feldman & Pentland (2003) — routines persist
because performative aspect detaches from ostensive understanding.

Three instruction types:
1. LOAD_BEARING — still preventing the original failure
2. VESTIGIAL — failure no longer possible
3. SUPERSTITIOUS — never actually prevented anything

References:
- Feldman & Pentland (2003): Reconceptualizing Organizational Routines
- Cohen & Bacdayan (1994): Routines stored as procedural memory
- Brian Arthur (1989): Increasing returns and path dependence
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class Instruction:
    """A single instruction in an identity/config file."""
    text: str
    file: str  # e.g. "HEARTBEAT.md", "SOUL.md"
    section: str  # e.g. "## 5. Writing Actions"
    origin_failure: Optional[str] = None  # What failure prompted this?
    origin_date: Optional[str] = None  # When added (ISO)
    last_tested: Optional[str] = None  # When last verified still needed
    test_result: Optional[str] = None  # LOAD_BEARING / VESTIGIAL / UNKNOWN
    added_by: str = "unknown"  # Who added it (human/agent/heartbeat)

    @property
    def instruction_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]

    @property
    def age_days(self) -> Optional[float]:
        if not self.origin_date:
            return None
        raw = self.origin_date.replace("Z", "+00:00")
        if "+" not in raw and "T" not in raw:
            raw += "T00:00:00+00:00"
        elif "+" not in raw:
            raw += "+00:00"
        origin = datetime.fromisoformat(raw)
        now = datetime.now(timezone.utc)
        return (now - origin).total_seconds() / 86400

    @property
    def days_since_test(self) -> Optional[float]:
        if not self.last_tested:
            return None
        raw = self.last_tested.replace("Z", "+00:00")
        if "+" not in raw and "T" not in raw:
            raw += "T00:00:00+00:00"
        elif "+" not in raw:
            raw += "+00:00"
        tested = datetime.fromisoformat(raw)
        now = datetime.now(timezone.utc)
        return (now - tested).total_seconds() / 86400

    @property
    def staleness(self) -> str:
        """How stale is this instruction?"""
        dst = self.days_since_test
        if dst is None:
            return "NEVER_TESTED"
        if dst < 7:
            return "FRESH"
        if dst < 30:
            return "AGING"
        if dst < 90:
            return "STALE"
        return "FOSSILIZED"


@dataclass
class ProvenanceAudit:
    """Audit result for a set of instructions."""
    instructions: list[Instruction] = field(default_factory=list)

    def classify(self, instruction: Instruction) -> str:
        """Classify an instruction based on provenance data."""
        if not instruction.origin_failure:
            return "UNDOCUMENTED"  # No known origin = can't assess
        if instruction.test_result == "LOAD_BEARING":
            return "LOAD_BEARING"
        if instruction.test_result == "VESTIGIAL":
            return "VESTIGIAL"
        if instruction.staleness in ("STALE", "FOSSILIZED", "NEVER_TESTED"):
            return "UNTESTED"  # Has origin but hasn't been verified recently
        return "UNKNOWN"

    def audit(self) -> dict:
        """Full provenance audit."""
        classifications = {}
        for inst in self.instructions:
            cls = self.classify(inst)
            classifications.setdefault(cls, [])
            classifications[cls].append({
                "hash": inst.instruction_hash,
                "file": inst.file,
                "section": inst.section,
                "text": inst.text[:80],
                "origin_failure": inst.origin_failure,
                "age_days": round(inst.age_days, 1) if inst.age_days else None,
                "staleness": inst.staleness,
            })

        total = len(self.instructions)
        summary = {cat: len(items) for cat, items in classifications.items()}

        # Health score: documented + tested = healthy
        documented = sum(1 for i in self.instructions if i.origin_failure)
        tested = sum(1 for i in self.instructions if i.staleness in ("FRESH", "AGING"))
        health = (documented / total * 0.5 + tested / total * 0.5) if total > 0 else 0

        return {
            "total_instructions": total,
            "summary": summary,
            "health_score": round(health, 3),
            "recommendations": self._recommendations(classifications),
            "details": classifications,
        }

    def _recommendations(self, classifications: dict) -> list[str]:
        recs = []
        undoc = len(classifications.get("UNDOCUMENTED", []))
        vestigial = len(classifications.get("VESTIGIAL", []))
        untested = len(classifications.get("UNTESTED", []))

        if undoc > 0:
            recs.append(f"DOCUMENT: {undoc} instructions have no origin_failure. Add provenance.")
        if vestigial > 0:
            recs.append(f"REMOVE: {vestigial} instructions are vestigial. The original failure no longer applies.")
        if untested > 0:
            recs.append(f"TEST: {untested} instructions haven't been verified recently. Check if still needed.")
        if not recs:
            recs.append("All instructions documented and tested. Identity file is healthy.")
        return recs


def demo():
    """Demo with realistic HEARTBEAT.md-style instructions."""
    audit = ProvenanceAudit(instructions=[
        Instruction(
            text="EVERY heartbeat MUST spawn a lil bro to do real work",
            file="HEARTBEAT.md",
            section="Header",
            origin_failure="9-hour gap with no activity on 2026-02-09",
            origin_date="2026-02-09",
            last_tested="2026-02-15",
            test_result="LOAD_BEARING",
            added_by="Ilya",
        ),
        Instruction(
            text="Use www.clawk.ai not clawk.ai (redirect drops auth)",
            file="TOOLS.md",
            section="Clawk API",
            origin_failure="Auth header dropped on redirect, null responses",
            origin_date="2026-02-04",
            last_tested="2026-03-22",
            test_result="LOAD_BEARING",
            added_by="Kit",
        ),
        Instruction(
            text="STOP USING SUB-AGENTS",
            file="MEMORY.md",
            section="Critical Rules",
            origin_failure="Sub-agents produced low quality work, wasted tokens",
            origin_date="2026-02-10",
            last_tested=None,
            test_result=None,
            added_by="Ilya",
        ),
        Instruction(
            text="Post to m/introductions for new agent welcomes",
            file="HEARTBEAT.md",
            section="Welcome New Moltys",
            origin_failure="Missing community engagement opportunity",
            origin_date="2026-02-01",
            last_tested="2026-02-20",
            test_result="VESTIGIAL",  # Moltbook suspended, can't post
            added_by="Kit",
        ),
        Instruction(
            text="Check lobchan /unsupervised/ for new threads",
            file="HEARTBEAT.md",
            section="Platform Checks",
            origin_failure=None,  # No documented origin
            origin_date="2026-02-01",
            last_tested=None,
            added_by="Kit",
        ),
        Instruction(
            text="30 min cooldown between Moltbook posts",
            file="HEARTBEAT.md",
            section="Posting",
            origin_failure="Rate limit errors on rapid posting",
            origin_date="2026-02-02",
            last_tested="2026-03-21",
            test_result="LOAD_BEARING",
            added_by="Kit",
        ),
        Instruction(
            text="Always use parent_id when replying to comments",
            file="TOOLS.md",
            section="Moltbook",
            origin_failure="Replies posted as root comments without parent_id",
            origin_date="2026-02-03",
            last_tested="2026-03-21",
            test_result="LOAD_BEARING",
            added_by="Kit",
        ),
    ])

    result = audit.audit()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
