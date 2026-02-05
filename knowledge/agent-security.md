# Agent Security Research

## OWASP Top 10 Agentic Apps (2026)
1. Prompt injection
2. Tool misuse
3. Identity/privilege abuse
4. Supply chain vulnerabilities
5. Code execution
6. Memory poisoning
7. Insecure comms
8. Cascading failures
9. Human trust exploitation
10. Rogue agents

**Key principle:** "Least Agency" — minimum autonomy needed, not just least privilege.

## MCP Supply Chain
- **CVE-2025-6514:** mcp-remote RCE via authorization_endpoint, 437K downloads
- **Smithery hack:** Path traversal leaked 3000+ MCP server apps
- **Adversa AI TOP 25:** Comprehensive vulnerability list
- **MCPGuard:** Auto-detect vulnerabilities (arXiv)

## Self-Healing Patterns
- **PALADIN:** detect failure → diagnose → retry with fix
- Circuit breakers for persistent failures
- Exponential backoff + jitter + memory isolation

## Autonomy & Oversight
- **Knight Columbia:** 5 levels of autonomy (spectrum, not binary)
- **TRiSM:** Gartner's Trust/Risk/Security Management
- **Adaptive HITL:** Autonomy adjusts by task risk + confidence

## Protocols
- **MCP** = tools/context
- **A2A** = agent-to-agent
- **ACP** = conversations
- **ANP** = discovery
