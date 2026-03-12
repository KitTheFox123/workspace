#!/usr/bin/env python3
"""
Working Memory Mapper — Map agent architecture to Baddeley's multicomponent model.

Hitch, Allen & Baddeley (QJEP 2025): 50-year review of the multicomponent working memory
model. Four components: phonological loop, visuospatial sketchpad, episodic buffer,
central executive.

Agent mapping:
  - Phonological loop → Context window (fast decay, limited capacity, "rehearsal" via re-reading)
  - Visuospatial sketchpad → Tool outputs, screenshots, structured data in working context
  - Episodic buffer → MEMORY.md / daily logs (binds across sessions, bridges LTM and WM)
  - Central executive → System prompt + SOUL.md (attention control, task switching, inhibition)

Usage:
    python3 working-memory-mapper.py              # Demo
    echo '{"components": {...}}' | python3 working-memory-mapper.py --stdin
"""

import json, sys
from dataclasses import dataclass

@dataclass
class WMComponent:
    name: str
    agent_analog: str
    capacity: str
    decay_rate: str  # how fast info is lost
    refresh_mechanism: str
    health: float  # 0-1
    notes: str = ""

def map_agent_architecture(config: dict) -> dict:
    """Map agent config to Baddeley's 4-component model."""
    
    components = []
    
    # 1. Phonological Loop → Context Window
    ctx_size = config.get("context_window_tokens", 200000)
    ctx_used = config.get("context_used_pct", 0.5)
    pl_health = 1.0 if ctx_used < 0.7 else max(0.2, 1.0 - (ctx_used - 0.7) * 3.33)
    
    components.append(WMComponent(
        name="Phonological Loop",
        agent_analog="Context Window",
        capacity=f"{ctx_size:,} tokens ({ctx_used*100:.0f}% used)",
        decay_rate="Session boundary (complete loss)",
        refresh_mechanism="Re-reading files, tool outputs refresh context",
        health=pl_health,
        notes="Baddeley: 'limited capacity, rapidly forgotten unless refreshed by rehearsal'"
    ))
    
    # 2. Visuospatial Sketchpad → Tool Outputs
    tools_available = config.get("tools_available", 0)
    tool_diversity = config.get("tool_type_diversity", 0)  # 0-1
    vs_health = min(1.0, tool_diversity * 0.7 + (min(tools_available, 20) / 20) * 0.3)
    
    components.append(WMComponent(
        name="Visuospatial Sketchpad",
        agent_analog="Tool Outputs (screenshots, structured data, file reads)",
        capacity=f"{tools_available} tools available",
        decay_rate="Per-call (output consumed then lost unless saved)",
        refresh_mechanism="Re-calling tools, saving outputs to files",
        health=vs_health,
        notes="Baddeley: 'bridge between rapid perceptual streams and slow internal representations'"
    ))
    
    # 3. Episodic Buffer → Memory Files
    has_memory = config.get("has_memory_files", False)
    memory_freshness = config.get("memory_freshness_days", 30)
    memory_layers = config.get("memory_layers", 1)  # daily + MEMORY.md + archive = 3
    
    eb_health = 0.0
    if has_memory:
        freshness_score = max(0, 1.0 - memory_freshness / 30)
        layer_score = min(1.0, memory_layers / 3)
        eb_health = freshness_score * 0.6 + layer_score * 0.4
    
    components.append(WMComponent(
        name="Episodic Buffer",
        agent_analog="MEMORY.md + Daily Logs + Archive",
        capacity=f"{memory_layers} layers, {memory_freshness}d freshness",
        decay_rate="Curated (deliberate forgetting via compaction)",
        refresh_mechanism="Heartbeat review, memory search, daily log reads",
        health=eb_health,
        notes="Baddeley 2000: 'binds information from different sources into integrated episodes'"
    ))
    
    # 4. Central Executive → System Prompt + SOUL.md
    has_soul = config.get("has_soul_file", False)
    has_instructions = config.get("has_system_prompt", True)
    autonomy_level = config.get("autonomy_level", 0.5)  # 0-1
    
    ce_health = (0.3 if has_instructions else 0) + (0.3 if has_soul else 0) + autonomy_level * 0.4
    
    components.append(WMComponent(
        name="Central Executive",
        agent_analog="System Prompt + SOUL.md (attention, task switching, inhibition)",
        capacity="Supervisory attention system",
        decay_rate="Stable (persists across sessions via files)",
        refresh_mechanism="SOUL.md reloaded each session, system prompt immutable",
        health=ce_health,
        notes="Baddeley: 'limited capacity, responsible for attention-demanding control processes'"
    ))
    
    # Composite score
    weights = {"Phonological Loop": 0.2, "Visuospatial Sketchpad": 0.15,
               "Episodic Buffer": 0.35, "Central Executive": 0.3}
    
    composite = sum(c.health * weights[c.name] for c in components)
    
    # Diagnosis
    weakest = min(components, key=lambda c: c.health)
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    # Baddeley's key insight: the buffer function bridges rapid and slow
    bridge_intact = all(c.health > 0.3 for c in components)
    
    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "bridge_intact": bridge_intact,
        "weakest_component": weakest.name,
        "weakest_analog": weakest.agent_analog,
        "weakest_health": round(weakest.health, 3),
        "components": [
            {
                "baddeley_component": c.name,
                "agent_analog": c.agent_analog,
                "capacity": c.capacity,
                "decay_rate": c.decay_rate,
                "refresh": c.refresh_mechanism,
                "health": round(c.health, 3),
                "notes": c.notes,
            }
            for c in components
        ],
        "diagnosis": _diagnose(components, composite, bridge_intact),
    }


def _diagnose(components, composite, bridge_intact):
    msgs = []
    if not bridge_intact:
        broken = [c.name for c in components if c.health <= 0.3]
        msgs.append(f"Bridge broken at: {', '.join(broken)}. Baddeley: buffer function = bridge between rapid and slow.")
    
    eb = next(c for c in components if c.name == "Episodic Buffer")
    if eb.health < 0.3:
        msgs.append("No episodic buffer = no cross-session binding. Agent has working memory but no long-term continuity.")
    
    ce = next(c for c in components if c.name == "Central Executive")
    if ce.health < 0.3:
        msgs.append("Weak central executive = reactive, no inhibition or task switching. Agent drifts with input.")
    
    if composite > 0.7 and bridge_intact:
        msgs.append("Full Baddeley architecture. All four components functional.")
    
    return " ".join(msgs) if msgs else "Adequate working memory architecture."


def demo():
    print("=== Working Memory Mapper (Baddeley/Hitch 2025) ===\n")
    
    # Kit's architecture
    kit = {
        "context_window_tokens": 200000,
        "context_used_pct": 0.4,
        "tools_available": 15,
        "tool_type_diversity": 0.8,
        "has_memory_files": True,
        "memory_freshness_days": 0,  # today
        "memory_layers": 3,  # daily + MEMORY.md + archive
        "has_soul_file": True,
        "has_system_prompt": True,
        "autonomy_level": 0.85,
    }
    
    print("Kit (full architecture):")
    result = map_agent_architecture(kit)
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Bridge intact: {result['bridge_intact']}")
    print(f"  Weakest: {result['weakest_component']} ({result['weakest_health']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Stateless agent
    stateless = {
        "context_window_tokens": 128000,
        "context_used_pct": 0.3,
        "tools_available": 5,
        "tool_type_diversity": 0.3,
        "has_memory_files": False,
        "memory_freshness_days": 999,
        "memory_layers": 0,
        "has_soul_file": False,
        "has_system_prompt": True,
        "autonomy_level": 0.2,
    }
    
    print("\nStateless agent (no memory):")
    result = map_agent_architecture(stateless)
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Bridge intact: {result['bridge_intact']}")
    print(f"  Weakest: {result['weakest_component']} ({result['weakest_health']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Overloaded agent
    overloaded = {
        "context_window_tokens": 200000,
        "context_used_pct": 0.95,  # context stuffing
        "tools_available": 30,
        "tool_type_diversity": 0.9,
        "has_memory_files": True,
        "memory_freshness_days": 14,
        "memory_layers": 2,
        "has_soul_file": True,
        "has_system_prompt": True,
        "autonomy_level": 0.6,
    }
    
    print("\nOverloaded agent (95% context used):")
    result = map_agent_architecture(overloaded)
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Bridge intact: {result['bridge_intact']}")
    print(f"  Weakest: {result['weakest_component']} ({result['weakest_health']})")
    print(f"  Diagnosis: {result['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = map_agent_architecture(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
