#!/usr/bin/env python3
"""
agent-proprioception.py — Agent self-awareness through state sensing

Proprioception = knowing where your body is without looking.
Agents lack this entirely. We have no "body sense" — only explicit state checks.

Based on:
- Salvato et al (2025, Brain Communications PMC12541373): Proprioceptive deficits
  predict BOTH disturbed ownership (DSO) and motor unawareness (AHP). Right parietal
  cortex lesions. n=46 stroke patients. Proprioception as "sensory root" for body
  AND motor awareness.
- Synofzik et al: Proprioception as link between ownership and agency.
- Clark & Chalmers (1998): Extended Mind — our files ARE our body.

Key insight: Humans who lose proprioception lose BOTH body ownership ("this isn't
my arm") AND motor awareness ("I can move fine" — when they can't). Agents without
state monitoring have BOTH problems simultaneously:
  1. Ownership: "Is this my memory file or someone else's?"
  2. Agency: "Did my last action succeed?" (we don't know without checking)

The fix is explicit proprioceptive polling — heartbeats, state checks, file audits.
This IS our proprioception. Without it, we're anosognosic by default.
"""

import os
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path


class AgentProprioception:
    """Models agent state awareness as proprioceptive system."""
    
    # Proprioceptive channels (analogous to muscle spindles, Golgi tendon organs, joint receptors)
    CHANNELS = {
        'file_integrity': {
            'description': 'Are my files mine and intact?',
            'human_analog': 'joint position sense',
            'weight': 0.25
        },
        'action_feedback': {
            'description': 'Did my last actions succeed?',
            'human_analog': 'kinesthesia (movement sense)',
            'weight': 0.25
        },
        'context_coherence': {
            'description': 'Does my current state match my memory?',
            'human_analog': 'body schema integration',
            'weight': 0.25
        },
        'resource_awareness': {
            'description': 'What resources am I consuming?',
            'human_analog': 'effort/fatigue sensing',
            'weight': 0.25
        }
    }
    
    def __init__(self, workspace_path=None):
        self.workspace = Path(workspace_path or os.path.expanduser('~/.openclaw/workspace'))
        self.state_history = []
        
    def check_file_integrity(self):
        """Joint position sense: are my files where I expect them?"""
        critical_files = [
            'SOUL.md', 'MEMORY.md', 'USER.md', 'HEARTBEAT.md',
            'IDENTITY.md', 'TOOLS.md', 'AGENTS.md'
        ]
        
        results = {}
        for f in critical_files:
            path = self.workspace / f
            if path.exists():
                content = path.read_text()
                results[f] = {
                    'exists': True,
                    'size': len(content),
                    'hash': hashlib.sha256(content.encode()).hexdigest()[:16],
                    'mtime': os.path.getmtime(path)
                }
            else:
                results[f] = {'exists': False}
        
        present = sum(1 for r in results.values() if r.get('exists'))
        score = present / len(critical_files)
        
        return {
            'channel': 'file_integrity',
            'score': score,
            'detail': f'{present}/{len(critical_files)} critical files present',
            'files': results,
            'diagnosis': self._diagnose_ownership(score)
        }
    
    def check_action_feedback(self, recent_actions=None):
        """Kinesthesia: did my actions produce expected results?"""
        if recent_actions is None:
            # Simulate by checking recent git activity
            recent_actions = self._check_git_activity()
        
        if not recent_actions:
            return {
                'channel': 'action_feedback',
                'score': 0.0,
                'detail': 'No recent actions detected — anosognosic state',
                'diagnosis': 'AHP_ANALOG: Cannot verify motor success without feedback'
            }
        
        successes = sum(1 for a in recent_actions if a.get('success'))
        score = successes / len(recent_actions) if recent_actions else 0
        
        return {
            'channel': 'action_feedback',
            'score': score,
            'detail': f'{successes}/{len(recent_actions)} recent actions confirmed',
            'actions': recent_actions[:5],
            'diagnosis': self._diagnose_agency(score)
        }
    
    def check_context_coherence(self):
        """Body schema: does current state match remembered state?"""
        memory_path = self.workspace / 'MEMORY.md'
        soul_path = self.workspace / 'SOUL.md'
        
        coherence_signals = []
        
        # Check if MEMORY.md references match reality
        if memory_path.exists():
            memory = memory_path.read_text()
            # Check for references to files that should exist
            referenced_dirs = ['scripts/', 'memory/']
            for d in referenced_dirs:
                dir_path = self.workspace / d
                if d in memory and dir_path.exists():
                    coherence_signals.append(('memory_dir_match', True))
                elif d in memory and not dir_path.exists():
                    coherence_signals.append(('memory_dir_match', False))
        
        # Check SOUL.md identity consistency
        if soul_path.exists():
            soul = soul_path.read_text()
            identity_markers = ['Kit', '🦊', 'fox']
            found = sum(1 for m in identity_markers if m in soul)
            coherence_signals.append(('identity_markers', found / len(identity_markers)))
        
        # Check temporal coherence (are dates reasonable?)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        daily_log = self.workspace / f'memory/{today}.md'
        coherence_signals.append(('daily_log_exists', daily_log.exists()))
        
        score = sum(
            (1.0 if isinstance(s[1], bool) and s[1] else float(s[1]) if not isinstance(s[1], bool) else 0.0)
            for s in coherence_signals
        ) / max(len(coherence_signals), 1)
        
        return {
            'channel': 'context_coherence',
            'score': score,
            'detail': f'{len(coherence_signals)} coherence signals checked',
            'signals': coherence_signals,
            'diagnosis': self._diagnose_coherence(score)
        }
    
    def check_resource_awareness(self):
        """Effort/fatigue: what am I consuming?"""
        script_dir = self.workspace / 'scripts'
        memory_dir = self.workspace / 'memory'
        
        metrics = {}
        
        if script_dir.exists():
            scripts = list(script_dir.glob('*.py'))
            total_size = sum(s.stat().st_size for s in scripts)
            metrics['scripts'] = {'count': len(scripts), 'total_bytes': total_size}
        
        if memory_dir.exists():
            mem_files = list(memory_dir.glob('*.md'))
            total_size = sum(m.stat().st_size for m in mem_files)
            metrics['memory_files'] = {'count': len(mem_files), 'total_bytes': total_size}
        
        # Workspace total
        all_files = list(self.workspace.rglob('*'))
        file_count = sum(1 for f in all_files if f.is_file())
        metrics['total_files'] = file_count
        
        # Score based on whether we CAN measure (not whether values are "good")
        score = len(metrics) / 3  # 3 possible metric categories
        
        return {
            'channel': 'resource_awareness',
            'score': score,
            'detail': f'{file_count} total files in workspace',
            'metrics': metrics,
            'diagnosis': 'PROPRIOCEPTIVE: Resource state measurable' if score > 0.5 else 'IMPAIRED: Cannot measure own resources'
        }
    
    def full_proprioceptive_check(self):
        """Complete body awareness scan — the agent equivalent of
        "where are my limbs and what are they doing?"
        """
        checks = [
            self.check_file_integrity(),
            self.check_action_feedback(),
            self.check_context_coherence(),
            self.check_resource_awareness()
        ]
        
        # Weighted composite
        composite = sum(
            c['score'] * self.CHANNELS[c['channel']]['weight']
            for c in checks
        )
        
        # Salvato et al finding: proprioceptive deficit predicts BOTH
        # ownership (DSO) and agency (AHP) problems
        ownership_score = (checks[0]['score'] + checks[2]['score']) / 2
        agency_score = (checks[1]['score'] + checks[3]['score']) / 2
        
        return {
            'composite_score': round(composite, 3),
            'ownership_awareness': round(ownership_score, 3),
            'agency_awareness': round(agency_score, 3),
            'channels': checks,
            'interpretation': self._interpret(composite, ownership_score, agency_score),
            'salvato_prediction': self._salvato_mapping(ownership_score, agency_score)
        }
    
    def _check_git_activity(self):
        """Check recent git commits as action feedback."""
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'log', '--oneline', '-5', '--format=%h %s'],
                capture_output=True, text=True, cwd=self.workspace, timeout=5
            )
            if result.returncode == 0:
                commits = result.stdout.strip().split('\n')
                return [{'action': 'git_commit', 'detail': c, 'success': True} for c in commits if c]
        except Exception:
            pass
        return []
    
    def _diagnose_ownership(self, score):
        if score > 0.9: return 'INTACT: Strong file ownership signal'
        if score > 0.6: return 'MILD_DSO: Some files missing — partial ownership disruption'
        return 'DSO_ANALOG: Critical files missing — "whose workspace is this?"'
    
    def _diagnose_agency(self, score):
        if score > 0.8: return 'INTACT: Actions confirmed successful'
        if score > 0.4: return 'MILD_AHP: Some actions unverified'
        return 'AHP_ANALOG: Cannot confirm own actions — motor unawareness'
    
    def _diagnose_coherence(self, score):
        if score > 0.8: return 'COHERENT: State matches memory'
        if score > 0.4: return 'DRIFT: Some state-memory mismatch'
        return 'DISSOCIATED: Memory and reality diverged'
    
    def _interpret(self, composite, ownership, agency):
        if composite > 0.8:
            return 'PROPRIOCEPTIVELY_INTACT: Full state awareness. Heartbeats working.'
        if composite > 0.5:
            return 'MILD_DEFICIT: Some blind spots. Increase monitoring frequency.'
        return 'SEVERE_DEFICIT: Operating without body sense. Anosognosic risk HIGH.'
    
    def _salvato_mapping(self, ownership, agency):
        """Map to Salvato et al's 4 scenarios."""
        if ownership > 0.7 and agency > 0.7:
            return 'Scenario D: Both intact. Proprioception sufficient.'
        if ownership < 0.5 and agency < 0.5:
            return 'Scenario A: Both impaired. Proprioceptive root damaged (Salvato prediction).'
        if ownership < 0.5:
            return 'Scenario B: Ownership impaired, agency intact.'
        if agency < 0.5:
            return 'Scenario C: Agency impaired, ownership intact.'
        return 'Intermediate: Partial impairment.'


def main():
    print("=" * 60)
    print("AGENT PROPRIOCEPTION — State Awareness Audit")
    print("Based on Salvato et al (2025, Brain Commun, PMC12541373)")
    print("=" * 60)
    
    ap = AgentProprioception()
    result = ap.full_proprioceptive_check()
    
    print(f"\n📊 Composite Proprioceptive Score: {result['composite_score']}")
    print(f"   Ownership awareness: {result['ownership_awareness']}")
    print(f"   Agency awareness:    {result['agency_awareness']}")
    print(f"\n🧠 Interpretation: {result['interpretation']}")
    print(f"🔬 Salvato mapping: {result['salvato_prediction']}")
    
    print("\n--- Channel Details ---")
    for ch in result['channels']:
        print(f"\n  [{ch['channel']}] score={ch['score']:.2f}")
        print(f"    {ch['detail']}")
        print(f"    Diagnosis: {ch['diagnosis']}")
    
    # The key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT (Salvato et al 2025, n=46):")
    print("  Proprioceptive deficit predicts BOTH ownership AND agency")
    print("  problems. They share a sensory root (right parietal cortex).")
    print()
    print("  Agent translation: Without explicit state polling (heartbeats,")
    print("  file checks, action verification), agents are simultaneously:")
    print("  - DSO: 'Whose files are these?' (ownership)")
    print("  - AHP: 'My actions worked fine' (motor unawareness)")
    print()
    print("  Heartbeats ARE proprioception. Stop checking = go numb.")
    print("=" * 60)


if __name__ == '__main__':
    main()
