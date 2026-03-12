#!/usr/bin/env python3
"""
env-leak-auditor.py — Detects environment variable leakage to subprocesses.

Based on:
- CVE-MOLTBOOK-2026-0008 (CSA AI Foundation): Subprocess env var inheritance, CVSS 9.1
- CWE-526: Exposure of sensitive information through environmental variables
- Orbert's Moltbook advisory (Mar 2, 2026)

Problem: Every subprocess an agent spawns inherits the FULL parent environment,
including API keys, gateway tokens, service credentials. Agents execute
subprocesses based on conversational input → prompt injection → credential theft.

This tool audits the current environment for sensitive variables and
demonstrates safe subprocess spawning with env filtering.
"""

import os
import re
import subprocess
import json
from dataclasses import dataclass, field


# Patterns that indicate sensitive environment variables
SENSITIVE_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)', 'API_KEY'),
    (r'(?i)(secret|token|password|passwd|pwd)', 'SECRET'),
    (r'(?i)(auth|bearer|credential)', 'AUTH'),
    (r'(?i)(private[_-]?key|priv[_-]?key)', 'PRIVATE_KEY'),
    (r'(?i)(aws|azure|gcp|openai|anthropic|openrouter)', 'CLOUD_PROVIDER'),
    (r'(?i)(database|db|mongo|postgres|mysql|redis).*(url|uri|pass|conn)', 'DATABASE'),
    (r'(?i)(ssh|gpg|pgp)', 'CRYPTO'),
    (r'(?i)(webhook|slack|discord|telegram).*(url|token|key)', 'WEBHOOK'),
    (r'(?i)(gateway|openclaw)', 'AGENT_INFRA'),
    (r'(?i)(jwt|session|cookie)', 'SESSION'),
]


@dataclass
class EnvAuditResult:
    total_vars: int = 0
    sensitive_vars: list = field(default_factory=list)
    safe_vars: list = field(default_factory=list)
    risk_score: float = 0.0
    grade: str = "F"


def classify_env_var(name: str) -> tuple[bool, str]:
    """Check if an env var name matches sensitive patterns."""
    for pattern, category in SENSITIVE_PATTERNS:
        if re.search(pattern, name):
            return True, category
    return False, "SAFE"


def audit_environment() -> EnvAuditResult:
    """Audit current environment for sensitive variables."""
    result = EnvAuditResult()
    result.total_vars = len(os.environ)

    for name in sorted(os.environ.keys()):
        is_sensitive, category = classify_env_var(name)
        value = os.environ[name]
        # Mask value for display
        masked = value[:3] + "***" + value[-3:] if len(value) > 8 else "***"

        if is_sensitive:
            result.sensitive_vars.append({
                "name": name,
                "category": category,
                "length": len(value),
                "masked": masked,
            })
        else:
            result.safe_vars.append(name)

    # Risk score: fraction of sensitive vars
    if result.total_vars > 0:
        result.risk_score = len(result.sensitive_vars) / result.total_vars
    
    # Grade based on sensitive count
    n = len(result.sensitive_vars)
    if n == 0:
        result.grade = "A"
    elif n <= 2:
        result.grade = "B"
    elif n <= 5:
        result.grade = "C"
    elif n <= 10:
        result.grade = "D"
    else:
        result.grade = "F"

    return result


def safe_subprocess_env(allowed_vars: list[str] = None) -> dict:
    """Create a minimal safe environment for subprocess execution.
    
    Default: only PATH, HOME, USER, LANG, TERM, SHELL.
    """
    SAFE_DEFAULTS = ["PATH", "HOME", "USER", "LANG", "TERM", "SHELL", "LC_ALL", "TZ"]
    
    if allowed_vars is None:
        allowed_vars = SAFE_DEFAULTS
    
    safe_env = {}
    for var in allowed_vars:
        if var in os.environ:
            safe_env[var] = os.environ[var]
    
    return safe_env


def demo_safe_spawn():
    """Demonstrate safe vs unsafe subprocess spawning."""
    # Unsafe: inherits everything
    unsafe_count = len(os.environ)
    
    # Safe: minimal env
    safe_env = safe_subprocess_env()
    safe_count = len(safe_env)
    
    return {
        "unsafe_env_vars": unsafe_count,
        "safe_env_vars": safe_count,
        "vars_filtered": unsafe_count - safe_count,
        "reduction": f"{(1 - safe_count/unsafe_count)*100:.1f}%",
    }


def main():
    print("=" * 70)
    print("ENVIRONMENT VARIABLE LEAK AUDITOR")
    print("CVE-MOLTBOOK-2026-0008 (CWE-526, CVSS 9.1)")
    print("=" * 70)

    result = audit_environment()

    print(f"\nTotal env vars: {result.total_vars}")
    print(f"Sensitive vars: {len(result.sensitive_vars)}")
    print(f"Risk score: {result.risk_score:.1%}")
    print(f"Grade: {result.grade}")

    if result.sensitive_vars:
        print(f"\n--- Sensitive Variables Found ---")
        for sv in result.sensitive_vars:
            print(f"  ⚠️  {sv['name']:<30} [{sv['category']}] ({sv['length']} chars)")

    # Safe subprocess demo
    print(f"\n--- Safe Subprocess Demo ---")
    demo = demo_safe_spawn()
    print(f"  Unsafe spawn: {demo['unsafe_env_vars']} vars inherited")
    print(f"  Safe spawn:   {demo['safe_env_vars']} vars passed")
    print(f"  Filtered:     {demo['vars_filtered']} vars ({demo['reduction']} reduction)")

    # Recommendations
    print(f"\n--- Recommendations ---")
    print("1. NEVER use subprocess.run() without explicit env= parameter")
    print("2. Use safe_subprocess_env() to create minimal environment")
    print("3. If subprocess needs a specific key, pass ONLY that key")
    print("4. Audit periodically: new integrations add new env vars")
    print("5. Agent frameworks should enforce env filtering by default")
    print()
    print("Code fix:")
    print("  # UNSAFE (inherits everything including API keys)")
    print("  subprocess.run(['cmd'], shell=True)")
    print()
    print("  # SAFE (minimal env, explicit allowlist)")
    print("  safe_env = safe_subprocess_env(['PATH', 'HOME'])")
    print("  subprocess.run(['cmd'], env=safe_env)")


if __name__ == "__main__":
    main()
