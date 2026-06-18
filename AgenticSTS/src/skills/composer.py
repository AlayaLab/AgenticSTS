"""SkillComposer: formats retrieved skills into LLM prompt context.

Composes multiple skills into a structured prompt section that helps
the small LLM make better decisions. Skills are injected before the
"## Your Task" section in each prompt.
"""

from __future__ import annotations

from src.skills.models import Skill

_SKILL_HEADER = """## Expert Knowledge (retrieved skills)
*Apply these strategies to the current situation. Deviate only with good reason.*

"""


def compose_skill_context(
    skills: list[tuple[Skill, float]],
    *,
    threat_level: str = "",
) -> tuple[str, list[str]]:
    """Format retrieved skills into a prompt-ready string.

    Args:
        skills: List of (skill, relevance_score) from SkillLibrary.query().
        threat_level: Current threat level string ("lethal"|"high"|"medium"|"low"|"").
            At HIGH/LETHAL threat, filters to survival-relevant skills only.

    Returns:
        (formatted_text, skill_ids) — the prompt text and IDs of included skills
        for outcome tracking.
    """
    if not skills:
        return "", []

    # At HIGH/LETHAL threat, filter to survival-relevant skills only.
    # Survival skills: combat/boss category, or have hand/enemy power triggers.
    if threat_level in ("high", "lethal"):
        _SURVIVAL_CATEGORIES = {"combat", "boss"}
        filtered = []
        for skill, score in skills:
            is_survival_cat = skill.category in _SURVIVAL_CATEGORIES
            has_hand_trigger = bool(skill.trigger.requires_hand_capabilities)
            has_enemy_power_trigger = bool(skill.trigger.requires_enemy_powers)
            if is_survival_cat or has_hand_trigger or has_enemy_power_trigger:
                filtered.append((skill, score))
        # Keep at least 1 skill even if none pass filter
        if filtered:
            skills = filtered

    parts: list[str] = [_SKILL_HEADER]
    included_ids: list[str] = []

    for skill, score in skills:
        # Skip empty/corrupt skills (no name or no content)
        if not skill.name.strip() or not skill.content.strip():
            continue
        # Format this skill — slim format (no examples, no lessons, no category)
        lines: list[str] = []
        if skill.usage_count > 0:
            confidence_str = f"{skill.confidence:.0%}"
        else:
            confidence_str = "seed" if skill.source == "seed" else "new"
        verified_str = "" if skill.verified else " ⚠unverified"
        lines.append(f"**{skill.name}** ({confidence_str}{verified_str})")
        lines.append(skill.content)

        # Exception: combat sequencing skills keep 1 example
        _SEQ_KEYWORDS = {"sequence", "order", "先", "then", "before"}
        if (
            skill.category == "combat"
            and skill.examples
            and any(kw in skill.content.lower() for kw in _SEQ_KEYWORDS)
        ):
            lines.append(f"  - Example: {skill.examples[0]}")

        lines.append("")

        block = "\n".join(lines)
        parts.append(block)
        included_ids.append(skill.skill_id)

    if not included_ids:
        return "", []

    return "\n".join(parts), included_ids


def inject_skills_into_prompt(prompt: str, skill_text: str) -> str:
    """Insert skill context into an existing prompt.

    Inserts before the "## Your Task" section if present,
    otherwise before the last ## section.
    """
    if not skill_text:
        return prompt

    # Try to insert before "## Your Task"
    marker = "## Your Task"
    if marker in prompt:
        idx = prompt.index(marker)
        return prompt[:idx] + skill_text + "\n" + prompt[idx:]

    # Try to insert before the last "## " section
    last_section = prompt.rfind("\n## ")
    if last_section > 0:
        return prompt[:last_section + 1] + skill_text + "\n" + prompt[last_section + 1:]

    # Fallback: append before the prompt
    return skill_text + "\n" + prompt


def inject_candidate_into_prompt(
    prompt: str,
    *,
    name: str,
    content: str,
) -> str:
    """Inject a candidate skill into an existing prompt for A/B testing.

    Used by the pre-write A/B validator (spec §4.2). If the prompt already
    has an `## Expert Knowledge` section, append to it. Otherwise insert a
    fresh section before `## Your Task` (or at end of prompt if no markers).

    Candidate entry is tagged '(candidate - under evaluation)' so later audit
    logs can distinguish it from retrieved skills.
    """
    entry = f"- {name} (candidate - under evaluation): {content}"
    marker = "## Expert Knowledge"
    if marker in prompt:
        # Append entry to the end of that block (before next ## or EOF)
        idx = prompt.index(marker)
        tail_idx = prompt.find("\n## ", idx + len(marker))
        if tail_idx == -1:
            return prompt.rstrip() + "\n" + entry + "\n"
        return prompt[:tail_idx] + "\n" + entry + "\n" + prompt[tail_idx:]
    # No block exists — create one before `## Your Task`
    block = f"\n## Expert Knowledge\n{entry}\n"
    your_task = prompt.find("## Your Task")
    if your_task >= 0:
        return prompt[:your_task] + block + prompt[your_task:]
    # No `## Your Task` marker — append at end
    return prompt.rstrip() + "\n" + block
