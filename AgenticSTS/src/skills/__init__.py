"""Skills subpackage: procedural knowledge modules for LLM-augmented decisions.

Skills are structured textual knowledge that help the small local LLM (Qwen 3.5 9B)
make expert-level game decisions. Unlike the old numeric-parameter genetic algorithm
approach, skills encode knowledge as human-readable procedural text that gets
retrieved by game context and injected into LLM prompts.

Architecture inspired by:
- Voyager (skill library with retrieval)
- SCOPE (dual-stream prompt evolution)
- Claude Code skills (composable procedural knowledge)

Skill lifecycle:
1. Seed skills: hand-authored domain knowledge (loaded at startup)
2. Discovered skills: extracted from successful gameplay runs
3. Refined skills: improved via LLM analysis of success/failure patterns
4. Deprecated skills: deactivated when confidence drops below threshold
"""

from src.skills.composer import compose_skill_context
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger

__all__ = [
    "Skill",
    "SkillLibrary",
    "SkillTrigger",
    "compose_skill_context",
]
