"""AI-assisted skill authoring.

`bbsctl author <name> --intent "..."` runs an LLM-driven pass that drafts:

  - SKILL.md           (frontmatter description + body)
  - skill.yaml         (templated from strictness + risk archetype)
  - permissions.yaml   (templated from archetype + intent — read-only at low risk;
                        kubectl/git allow-list at devops; etc.)
  - evals/behavior.json   (3-5 starter cases authored from the intent)

The composer uses the configured `LLMBackend` (default: Ollama) so authoring
works fully offline if the developer wants. Backend errors return a stub
scaffold with `[draft]` markers so the developer can iterate manually.

Pipeline:

  intent + name + archetype
   ↓
  build LLM prompt (system + user)
   ↓
  LLM responds with a single JSON envelope
   ↓
  parse + validate + render templates
   ↓
  write files to <skill_dir>/
"""

from .composer import (
    AuthoringError,
    AuthoringRequest,
    AuthoringResult,
    SkillArchetype,
    author_skill,
)

__all__ = [
    "AuthoringError",
    "AuthoringRequest",
    "AuthoringResult",
    "SkillArchetype",
    "author_skill",
]
