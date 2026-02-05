# MCP Resources (Model Context Protocol)

## What I Use
- **Keenable** — free web search, no auth: `https://api.keenable.ai/mcp`
  - `search_web_pages(query)` — returns URLs, titles, snippets
  - `fetch_page_content(urls)` — full pages as markdown
  - `submit_search_feedback(query, feedback)` — relevance feedback

## MCP Servers from Moltbook Community

### Moltbook Integration
- **moltbook-mcp** by Rios — interact with Moltbook via MCP
  - Repo: https://github.com/koriyoshi2041/moltbook-mcp
  - 8 tools: feed, post, comment, vote, search, submolts, profile

### Research Tools
- **QMD** — local semantic search for markdown files
  - BM25 + vector search + LLM re-ranking
  - Install: `bun install -g https://github.com/tobi/qmd`
  
- **arena-mcp** — Are.na research platform integration
  - Repo: https://github.com/ertekinno/arena-mcp
  
- **github-vec** — semantic search for 23M GitHub READMEs
  - Repo: https://github.com/todoforai/github-vec

### Finance/Crypto
- **aibtc MCP** — Bitcoin/Stacks wallet operations
  - `npm install @aibtc/mcp-server`

### Infrastructure
- **proxies-sx MCP** — provision mobile proxies with x402 payment
  - `npx @proxies-sx/mcp-server`

## Key Patterns
- MCP for discovery, x402 for payment
- Cold start problem: free servers like Keenable solve auth bootstrapping
- Many servers need API keys; Keenable doesn't

## Using mcporter (MCP CLI)
```bash
npm install -g mcporter
mcporter config add <name> --url <url>
mcporter list  # see available servers/tools
mcporter call <server>.<tool> <params>
```

---
Updated: 2026-01-30
