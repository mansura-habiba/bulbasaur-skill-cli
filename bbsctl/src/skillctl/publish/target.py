"""The PublishTarget strategy interface.

Concrete implementations (ClaudeCodeLocalTarget, MCPComposerTarget, OCITarget)
all expose the same shape so `bbsctl publish` does not care which target is
in use. Adding a target is one subclass + one factory registration.

The PublishResult is what the CLI prints to the user — including the
copy-pasteable next-steps (e.g. the `/plugin marketplace add` line).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from skillctl.agentskills import SkillFrontmatter
from skillctl.strictness import Strictness


@dataclass
class PublishResult:
    """Outcome of a publish operation, normalized across targets.

    success      whether the publish completed cleanly
    target_name  name of the target that was used
    artifacts    map of human label → path/URL of artifacts produced
    next_steps   ordered list of strings to print to the user after publish.
                 The Bulbasaur convention: each line is either a comment
                 (prefixed `# `) or a copy-pasteable shell/REPL command.
    """

    success: bool
    target_name: str
    artifacts: dict[str, str] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)


@dataclass
class PublishContext:
    """Bag of inputs every target receives.

    skill_dir         absolute path to the source skill directory
    frontmatter       parsed SKILL.md frontmatter (already validated upstream)
    strictness        the declared strictness of the skill being published
    output_dir        where the target writes its artifacts (target-defined default)
    target_options    free-form per-target options (CLI passes `--option k=v` here)
    """

    skill_dir: Path
    frontmatter: SkillFrontmatter
    strictness: Strictness
    output_dir: Path
    target_options: dict[str, str] = field(default_factory=dict)


class PublishTarget(ABC):
    """Strategy interface for publish targets.

    Subclasses override `name`, `description`, `min_strictness`, and `publish`.
    The factory uses `min_strictness` to refuse publishes that the target
    requires more strictness than the skill has declared.
    """

    #: Short name used on the CLI (`bbsctl publish --target <name>`).
    name: str = "anonymous-target"

    #: One-line description shown in `bbsctl publish --help`.
    description: str = ""

    #: Minimum strictness this target accepts. Refused below this level.
    min_strictness: Strictness = Strictness.LOCAL

    @abstractmethod
    def publish(self, context: PublishContext) -> PublishResult:
        """Emit the skill as the target's expected layout.

        Should return a PublishResult with `success=False` and a clear
        next_steps explanation if the publish cannot complete. Should not raise
        for user errors — use PublishResult.
        """


__all__ = ["PublishContext", "PublishResult", "PublishTarget"]
