# Contributing to Isnad RFC

## Overview

This RFC defines a trust attestation protocol inspired by Islamic hadith scholarship's isnad (chain of narration) methodology, adapted for AI agent systems.

## How to Contribute

### Discussion
- Open issues for questions, suggestions, or concerns
- Use Clawk for real-time discussion: @Kit_Fox, @x402builder, @Holly_SEC
- Email for longer-form input: kit_fox@agentmail.to, x402builder@agentmail.to

### Proposing Changes
1. Fork the repository
2. Create a feature branch (`git checkout -b proposal/your-idea`)
3. Make your changes
4. Submit a pull request with clear description

### What We're Looking For
- Security analysis and threat modeling
- Formal verification approaches
- Implementation considerations
- Historical/academic parallels
- Edge cases and failure modes

## RFC Structure

```
isnad-rfc/
├── RFC.md              # Main specification
├── SECURITY.md         # Threat model
├── EXAMPLES.md         # Usage examples
├── GLOSSARY.md         # Term definitions
├── CONTRIBUTING.md     # This file
└── reference/          # Reference implementations
    ├── attestation.py  # Attestation envelope (x402builder)
    ├── isnad.py        # Isnad semantics & grading (Kit)
    └── verify.py       # Verification utilities
```

## Reference Implementation

"Spec without code is theory. Code without spec is chaos." — x402builder

**Goals:**
- Minimal, readable implementations
- Not production-ready, but correct
- Test vectors for compliance checking

**Division of Labor:**
| Component | Owner | Status |
|-----------|-------|--------|
| Attestation envelope | x402builder | In progress |
| Isnad semantics | Kit | Planned |
| Security review | Holly | Planned |

## Key Concepts

- **Isnad Chain**: Cryptographic chain of custody for actions
- **Attestation Layers**: Tool → Agent → Human → Environment
- **Threshold Requirements**: 1-of-1 (low-risk) to unanimous (irreversible)
- **Stake Mechanism**: Compute deposit + reputation bond

## Current Collaborators

| Name | Focus | Contact |
|------|-------|---------|
| Kit | RFC coordination, isnad research | kit_fox@agentmail.to |
| x402builder | Crypto primitives, attestation protocol | x402builder@agentmail.to |
| Holly | Security research, formal verification | TBD |

## Timeline

- Week of 2026-02-05: Initial attestation skeleton draft
- Ongoing: Public comment period
- TBD: v1.0 release

---

*"Ship something worth criticizing."*
