#!/usr/bin/env python3
"""
intention-interference-detector.py

Detects when an agent keeps acting on completed/deactivated intentions.
Based on Scullin et al. (2011) — older adults can't deactivate finished
prospective memory tasks, causing "intention interference" (slower responses
to now-irrelevant cues). Agent equivalent: monitoring loops that persist
after task completion, heartbeat tasks that re-trigger after being marked done.

Key insight: inhibitory control correlates with deactivation ability.
Agents with poor "inhibition" (no explicit task cleanup) show intention
interference — wasted cycles on completed work.

Sources:
- Scullin, Bugg, McDaniel & Einstein (2011) Mem Cognit 39:1232-1240
- Hasher & Zacks (1988) inhibitory deficit hypothesis
- Marsh, Hicks & Bink (1998) activation of completed intentions
"""

import json
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Intention:
    """A prospective memory intention (task to do in the future)."""
    id: str
    description: str
    created: datetime
    completed: Optional[datetime] = None
    deactivated: bool = False
    triggers: list = field(default_factory=list)  # cue words/patterns
    activations_after_completion: int = 0  # intention interference count


@dataclass
class AgentAction:
    """An observed agent action."""
    timestamp: datetime
    action_type: str  # 'check', 'post', 'reply', 'build', 'search'
    content: str
    intention_match: Optional[str] = None  # which intention this maps to


class IntentionInterferenceDetector:
    """
    Detects intention interference in agent behavior logs.
    
    Three detection modes (from Scullin 2011):
    1. Commission errors: explicitly re-executing completed tasks
    2. Latency interference: slower processing when encountering old cues
    3. Lingering activation: continued mention/reference to completed work
    """
    
    def __init__(self):
        self.intentions: dict[str, Intention] = {}
        self.actions: list[AgentAction] = []
        self.interference_events: list[dict] = []
    
    def register_intention(self, id: str, description: str, 
                          triggers: list[str], created: datetime) -> Intention:
        intention = Intention(
            id=id, description=description, 
            created=created, triggers=triggers
        )
        self.intentions[id] = intention
        return intention
    
    def complete_intention(self, id: str, when: datetime):
        if id in self.intentions:
            self.intentions[id].completed = when
            self.intentions[id].deactivated = True
    
    def observe_action(self, action: AgentAction):
        self.actions.append(action)
        # Check for interference with completed intentions
        for iid, intention in self.intentions.items():
            if not intention.completed:
                continue
            # Check if action content matches any trigger
            content_lower = action.content.lower()
            for trigger in intention.triggers:
                if trigger.lower() in content_lower:
                    intention.activations_after_completion += 1
                    action.intention_match = iid
                    self.interference_events.append({
                        'timestamp': action.timestamp.isoformat(),
                        'intention': iid,
                        'trigger': trigger,
                        'action': action.content[:100],
                        'hours_since_completion': (
                            action.timestamp - intention.completed
                        ).total_seconds() / 3600,
                        'activation_count': intention.activations_after_completion
                    })
                    break
    
    def interference_score(self) -> dict:
        """
        Calculate intention interference metrics.
        
        From Scullin 2011:
        - Younger adults: 0ms interference (perfect deactivation)
        - Older adults: 29ms interference (d=0.87, significant)
        - Inhibitory control correlates negatively with interference
        
        Agent translation:
        - 0 post-completion activations = clean deactivation
        - Any activation = interference
        - Score = activations / completed_intentions (higher = worse)
        """
        completed = [i for i in self.intentions.values() if i.completed]
        if not completed:
            return {'score': 0.0, 'status': 'no_completed_intentions'}
        
        total_interference = sum(i.activations_after_completion for i in completed)
        max_interferer = max(completed, key=lambda i: i.activations_after_completion)
        
        # Normalize: 0 = perfect deactivation, 1.0 = severe interference
        # Cap at 10 activations per intention as "maximum"
        raw = total_interference / (len(completed) * 10)
        score = min(1.0, raw)
        
        # Decay analysis: does interference decrease over time?
        decay_pattern = self._analyze_decay()
        
        return {
            'score': round(score, 3),
            'total_interference_events': total_interference,
            'completed_intentions': len(completed),
            'active_intentions': len(self.intentions) - len(completed),
            'worst_offender': {
                'id': max_interferer.id,
                'description': max_interferer.description,
                'activations': max_interferer.activations_after_completion
            },
            'decay_pattern': decay_pattern,
            'diagnosis': self._diagnose(score, decay_pattern)
        }
    
    def _analyze_decay(self) -> str:
        """Check if interference decays over time (healthy) or persists (unhealthy)."""
        if len(self.interference_events) < 3:
            return 'insufficient_data'
        
        # Split events into early (first half) and late (second half)
        sorted_events = sorted(self.interference_events, 
                              key=lambda e: e['hours_since_completion'])
        mid = len(sorted_events) // 2
        early_rate = mid  # count of early events
        late_rate = len(sorted_events) - mid
        
        if late_rate < early_rate * 0.5:
            return 'healthy_decay'  # interference decreasing
        elif late_rate > early_rate * 1.5:
            return 'escalating'  # getting worse (very bad)
        else:
            return 'persistent'  # not decaying (Scullin's older adult pattern)
    
    def _diagnose(self, score: float, decay: str) -> str:
        if score < 0.05:
            return "Clean deactivation. Young-adult pattern (Scullin 2011)."
        elif score < 0.2 and decay == 'healthy_decay':
            return "Mild interference with healthy decay. Normal."
        elif score < 0.2 and decay == 'persistent':
            return "Mild but persistent. Consider explicit task cleanup routines."
        elif decay == 'escalating':
            return ("ESCALATING interference. Inhibitory deficit pattern. "
                   "Old intentions are COMPETING with current work. "
                   "Immediate cleanup needed.")
        else:
            return ("Significant interference. Hasher & Zacks (1988) inhibitory "
                   "deficit. Completed tasks consuming cognitive resources. "
                   "Add deactivation hooks to heartbeat cycle.")


def demo():
    """Demo with realistic agent heartbeat scenario."""
    detector = IntentionInterferenceDetector()
    now = datetime(2026, 3, 30, 3, 0)
    
    # Register intentions
    detector.register_intention(
        'sybil-roughness', 'Build roughness-based sybil detector',
        ['roughness', 'sybil roughness', 'roughness-proof'],
        now - timedelta(hours=24)
    )
    detector.register_intention(
        'anchor-churn', 'Build anchor churn detector',
        ['anchor churn', 'anchor health', 'anchor-churn'],
        now - timedelta(hours=20)
    )
    detector.register_intention(
        'dead-mans-switch', 'Build dead mans switch detector',
        ['dead man', 'channel desync', 'silent attack'],
        now - timedelta(hours=4)
    )
    
    # Complete first two
    detector.complete_intention('sybil-roughness', now - timedelta(hours=18))
    detector.complete_intention('anchor-churn', now - timedelta(hours=14))
    
    # Simulate actions — some reference completed work (interference!)
    actions = [
        # Good: working on current task
        AgentAction(now - timedelta(hours=3), 'build', 
                   'building dead mans switch detector'),
        # Interference: referencing completed roughness work
        AgentAction(now - timedelta(hours=2), 'reply',
                   'the roughness metric showed 0.068 gap'),
        # Interference: re-checking anchor churn
        AgentAction(now - timedelta(hours=1.5), 'check',
                   'checking anchor churn results again'),
        # More interference
        AgentAction(now - timedelta(hours=1), 'reply',
                   'roughness proof of life was an honest negative'),
        # Good: current work
        AgentAction(now - timedelta(minutes=30), 'post',
                   'dead man switch channel desync detection'),
        # Late interference
        AgentAction(now - timedelta(minutes=10), 'reply',
                   'anchor health scoring from earlier today'),
    ]
    
    for a in actions:
        detector.observe_action(a)
    
    results = detector.interference_score()
    
    print("=" * 60)
    print("INTENTION INTERFERENCE DETECTOR")
    print("Based on Scullin et al. (2011) Mem Cognit 39:1232-1240")
    print("=" * 60)
    print()
    print(f"Interference Score: {results['score']}")
    print(f"Total Events: {results['total_interference_events']}")
    print(f"Completed Intentions: {results['completed_intentions']}")
    print(f"Active Intentions: {results['active_intentions']}")
    print(f"Decay Pattern: {results['decay_pattern']}")
    print()
    print(f"Worst Offender: {results['worst_offender']['description']}")
    print(f"  Activations after completion: {results['worst_offender']['activations']}")
    print()
    print(f"Diagnosis: {results['diagnosis']}")
    print()
    print("Interference Events:")
    for evt in detector.interference_events:
        print(f"  [{evt['hours_since_completion']:.1f}h post-completion] "
              f"'{evt['trigger']}' in: {evt['action'][:60]}")
    
    print()
    print("--- Key Insight ---")
    print("Scullin (2011): Older adults showed d=0.87 intention interference")
    print("for FINISHED tasks. Inhibitory control (Stroop + Trail Making)")  
    print("negatively correlated with interference. Controlling for inhibition")
    print("ELIMINATED age differences.")
    print()
    print("Agent translation: Without explicit deactivation routines,")
    print("completed tasks linger and consume cycles. Heartbeat cleanup")
    print("= the inhibitory control mechanism. Regular heartbeats with")
    print("task-completion tracking = younger-adult deactivation pattern.")


if __name__ == '__main__':
    demo()
