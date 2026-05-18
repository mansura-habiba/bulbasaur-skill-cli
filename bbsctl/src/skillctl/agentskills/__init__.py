"""Bulbasaur's implementation of the agentskills.io specification rules.

The mental model (§8) and ADR 0004 specify that Bulbasaur aligns with
agentskills.io but does not depend on upstream `skills-ref` for validation.
We implement the rules ourselves so that:

  1. We are not blocked on upstream when fixing a bug.
  2. Our error messages follow the Bulbasaur error contract.
  3. We can ship in environments where Node-based reference tools are awkward.

Source-of-truth for the rules is https://agentskills.io/specification.
If we find a divergence between our interpretation and upstream, we file
an issue upstream and may emit a warning at compile time.
"""

from .frontmatter import (
    parse_skill_md,
    SkillFrontmatter,
    AgentSkillsValidationError,
)
from .rules import (
    validate_name,
    validate_description,
    validate_compatibility,
    validate_metadata,
    AGENTSKILLS_SPEC_URL,
)

__all__ = [
    "parse_skill_md",
    "SkillFrontmatter",
    "AgentSkillsValidationError",
    "validate_name",
    "validate_description",
    "validate_compatibility",
    "validate_metadata",
    "AGENTSKILLS_SPEC_URL",
]
