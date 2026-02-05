# Cost & Context Optimization

## Token Savings
- Observation masking > LLM summarization (50% savings, JetBrains)
- Caching + RAG + batching = 40-70% savings
- "Compress when optimal, not when forced" (Factory.ai)

## Tool Use
- Tool restraint is a skill
- Over-eager tool use = wasted tokens + latency
- 90% on math ≠ 90% on 3 chained API calls

## Benchmarks
- **τ-bench (Sierra):** Tool-Agent-User benchmark
- **BFCL V4:** Function calling gold standard
- **philschmid compendium:** 50+ agent benchmarks
