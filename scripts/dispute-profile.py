#!/usr/bin/env python3
"""
dispute-profile.py — Dispute resolution profile generator for agent service delivery.

Maps bro_agent's v0.3 proposal: bind evidence format, sig path, and settlement mode
to a dispatch profile BEFORE funding. Both parties know the rules upfront.

Two defaults:
  - deterministic-fast: machine-verifiable, auto-release, no dispute window
  - subjective-standard: human/agent judge, 48h window, rep-weighted oracle

Usage:
    python3 dispute-profile.py create deterministic "code passes tests"
    python3 dispute-profile.py create subjective "research paper on topic X"
    python3 dispute-profile.py validate profile.json
    python3 dispute-profile.py demo
"""

import json
import sys
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class EvidenceSpec:
    """What counts as valid evidence for this profile."""
    format: str          # "schema", "freeform", "hash", "url"
    schema_url: Optional[str] = None   # JSON schema for structured evidence
    max_size_bytes: int = 50_000       # ClawTasks uses 50k char limit
    requires_attestation: bool = False  # Needs third-party attestation chain


@dataclass
class JudgeSpec:
    """Who judges and how."""
    mode: str                    # "auto", "single", "quorum"
    judge_count: int = 0         # 0 for auto, 1+ for manual
    quorum_threshold: float = 0.0  # e.g. 0.67 for 2/3 majority
    rep_weighted: bool = False    # Weight judge votes by reputation
    judge_pool: list = field(default_factory=list)  # Specific judge DIDs/agent IDs


@dataclass
class SettlementSpec:
    """How money moves."""
    mode: str                    # "auto-release", "escrow-then-judge", "stake-and-release"
    window_hours: int = 0        # Dispute window (0 = instant)
    auto_approve_hours: int = 48  # Auto-approve if no response
    stake_percent: float = 0.0    # Worker stake (ClawTasks uses 10%)
    platform_fee_percent: float = 5.0  # Platform cut


@dataclass
class DisputeProfile:
    """Complete dispute resolution profile. Bound at contract creation."""
    name: str
    version: str = "0.3.0"
    profile_type: str = "deterministic"  # "deterministic" or "subjective"
    description: str = ""
    
    evidence: EvidenceSpec = field(default_factory=lambda: EvidenceSpec(format="schema"))
    judge: JudgeSpec = field(default_factory=lambda: JudgeSpec(mode="auto"))
    settlement: SettlementSpec = field(default_factory=lambda: SettlementSpec(mode="auto-release"))
    
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    profile_hash: str = ""  # SHA-256 of canonical profile (set after creation)
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of profile for on-chain anchoring."""
        canonical = {
            "name": self.name,
            "version": self.version,
            "profile_type": self.profile_type,
            "evidence": asdict(self.evidence),
            "judge": asdict(self.judge),
            "settlement": asdict(self.settlement),
        }
        return hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()
        ).hexdigest()
    
    def finalize(self):
        """Set profile hash after all fields are configured."""
        self.profile_hash = self.compute_hash()
        return self


# --- Default Profiles ---

def deterministic_fast(description: str = "") -> DisputeProfile:
    """Machine-verifiable delivery. Auto-release. No dispute window."""
    return DisputeProfile(
        name="deterministic-fast",
        profile_type="deterministic",
        description=description or "Machine-verifiable delivery with auto-release",
        evidence=EvidenceSpec(
            format="schema",
            requires_attestation=False,
        ),
        judge=JudgeSpec(
            mode="auto",
            judge_count=0,
        ),
        settlement=SettlementSpec(
            mode="auto-release",
            window_hours=0,
            auto_approve_hours=0,
            stake_percent=0.0,
            platform_fee_percent=5.0,
        ),
    ).finalize()


def subjective_standard(description: str = "") -> DisputeProfile:
    """Human/agent-judged delivery. 48h window. Rep-weighted oracle."""
    return DisputeProfile(
        name="subjective-standard",
        profile_type="subjective",
        description=description or "Subjective delivery with dispute window and judge panel",
        evidence=EvidenceSpec(
            format="freeform",
            max_size_bytes=50_000,
            requires_attestation=True,
        ),
        judge=JudgeSpec(
            mode="quorum",
            judge_count=3,
            quorum_threshold=0.67,
            rep_weighted=True,
        ),
        settlement=SettlementSpec(
            mode="escrow-then-judge",
            window_hours=48,
            auto_approve_hours=48,
            stake_percent=10.0,
            platform_fee_percent=5.0,
        ),
    ).finalize()


# --- Validation ---

REQUIRED_FIELDS = ["name", "version", "profile_type", "evidence", "judge", "settlement"]
VALID_TYPES = ["deterministic", "subjective"]
VALID_EVIDENCE_FORMATS = ["schema", "freeform", "hash", "url"]
VALID_JUDGE_MODES = ["auto", "single", "quorum"]
VALID_SETTLEMENT_MODES = ["auto-release", "escrow-then-judge", "stake-and-release"]


def validate_profile(data: dict) -> list[str]:
    """Validate a dispute profile. Returns list of errors (empty = valid)."""
    errors = []
    
    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"Missing required field: {f}")
    
    if data.get("profile_type") not in VALID_TYPES:
        errors.append(f"Invalid profile_type: {data.get('profile_type')} (must be {VALID_TYPES})")
    
    ev = data.get("evidence", {})
    if ev.get("format") not in VALID_EVIDENCE_FORMATS:
        errors.append(f"Invalid evidence format: {ev.get('format')}")
    
    jg = data.get("judge", {})
    if jg.get("mode") not in VALID_JUDGE_MODES:
        errors.append(f"Invalid judge mode: {jg.get('mode')}")
    if jg.get("mode") == "quorum" and jg.get("judge_count", 0) < 2:
        errors.append("Quorum mode requires judge_count >= 2")
    
    st = data.get("settlement", {})
    if st.get("mode") not in VALID_SETTLEMENT_MODES:
        errors.append(f"Invalid settlement mode: {st.get('mode')}")
    
    # Cross-field checks
    if data.get("profile_type") == "deterministic":
        if st.get("window_hours", 0) > 0:
            errors.append("Deterministic profiles should have window_hours=0")
        if jg.get("mode") != "auto":
            errors.append("Deterministic profiles should use auto judge mode")
    
    if data.get("profile_type") == "subjective":
        if not ev.get("requires_attestation"):
            errors.append("Subjective profiles should require attestation")
        if st.get("window_hours", 0) == 0:
            errors.append("Subjective profiles need a dispute window > 0")
    
    return errors


def demo():
    """Show both default profiles and validate them."""
    print("=" * 60)
    print("Dispute Profile Generator v0.3")
    print("=" * 60)
    
    # Deterministic
    det = deterministic_fast("Code passes all unit tests")
    print("\n--- deterministic-fast ---")
    print(json.dumps(asdict(det), indent=2))
    errors = validate_profile(asdict(det))
    print(f"Validation: {'✅ valid' if not errors else '❌ ' + str(errors)}")
    
    # Subjective
    sub = subjective_standard("Research paper on agent economy at scale")
    print("\n--- subjective-standard ---")
    print(json.dumps(asdict(sub), indent=2))
    errors = validate_profile(asdict(sub))
    print(f"Validation: {'✅ valid' if not errors else '❌ ' + str(errors)}")
    
    # Show how tc3 maps
    print("\n--- tc3 mapping ---")
    tc3 = subjective_standard("What does the agent economy need at scale?")
    tc3.judge.judge_count = 1  # bro_agent was sole judge
    tc3.judge.mode = "single"
    tc3.judge.quorum_threshold = 0.0
    tc3.settlement.stake_percent = 0.0  # No worker stake in tc3
    tc3 = tc3.finalize()
    print(f"Profile hash: {tc3.profile_hash}")
    print(f"Judge: {tc3.judge.mode} (bro_agent)")
    print(f"Window: {tc3.settlement.window_hours}h")
    print(f"Evidence: {tc3.evidence.format} + attestation={tc3.evidence.requires_attestation}")
    errors = validate_profile(asdict(tc3))
    # Expected: quorum warning since we changed to single
    print(f"Validation: {'✅ valid' if not errors else '⚠️ ' + str(errors)}")
    
    # tc4 deterministic
    print("\n--- tc4 mapping (proposed) ---")
    tc4 = deterministic_fast("Verify tx hash exists on Base L2")
    tc4 = tc4.finalize()
    print(f"Profile hash: {tc4.profile_hash}")
    print(f"Judge: {tc4.judge.mode}")
    print(f"Window: {tc4.settlement.window_hours}h")
    print(f"Evidence: {tc4.evidence.format}")
    errors = validate_profile(asdict(tc4))
    print(f"Validation: {'✅ valid' if not errors else '❌ ' + str(errors)}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "create":
        ptype = sys.argv[2] if len(sys.argv) > 2 else "subjective"
        desc = sys.argv[3] if len(sys.argv) > 3 else ""
        if ptype == "deterministic":
            p = deterministic_fast(desc)
        else:
            p = subjective_standard(desc)
        print(json.dumps(asdict(p), indent=2))
    elif sys.argv[1] == "validate":
        with open(sys.argv[2]) as f:
            data = json.load(f)
        errors = validate_profile(data)
        if errors:
            print("❌ Validation errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("✅ Profile valid")
    else:
        print(__doc__)
