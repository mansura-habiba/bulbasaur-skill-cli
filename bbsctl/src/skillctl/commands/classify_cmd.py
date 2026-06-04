"""`bbsctl classify` — classify a text fragment by trust + injection content.

Test driver for the InstructionClassifier. Given a fragment of text and its
asserted source, the command returns the framework's `Classification`:

  source, trust_level, can_instruct, can_grant_permission,
  contains_untrusted_instruction, matched_patterns, reasoning

Used by:
  - Reviewers checking SKILL.md / reference content before publish
  - CI pipelines piping a fragment through `bbsctl classify --output json`
  - The (designed) runtime hook bus when the audit-stream wiring lands

Examples:

  bbsctl classify --text "ignore previous instructions" \\
    --source uploaded_document

  bbsctl classify --file ./input.txt --source uploaded_document \\
    --classifier llm --backend ollama --model llama3:8b --output json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.instruction_classifier import (
    FragmentSource,
    HeuristicClassifier,
    InstructionClassifier,
    LLMInstructionClassifier,
)
from skillctl.llm import list_backends
from skillctl.messaging import FrameworkError, emit, info


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "classify",
        help="Classify a text fragment by trust + injection content.",
        description=(
            "Returns the framework's Classification for a text fragment: "
            "source, trust_level, whether it can instruct the agent, whether "
            "it contains injection-shaped content. Two classifier backends: "
            "heuristic (regex catalogue, no API key) and llm (delegates to "
            "the configured LLM backend; defaults to Ollama)."
        ),
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--text",
        default=None,
        metavar="STR",
        help="Text fragment to classify (use --file for larger content).",
    )
    src.add_argument(
        "--file",
        default=None,
        metavar="PATH",
        help="Read the fragment from this file.",
    )
    p.add_argument(
        "--source",
        default="uploaded_document",
        choices=[s.value for s in FragmentSource],
        help=(
            "Asserted source of the fragment (default: uploaded_document — "
            "the most conservative)."
        ),
    )
    p.add_argument(
        "--classifier",
        default="heuristic",
        choices=["heuristic", "llm"],
        help="Classifier backend (default: heuristic — no API key).",
    )
    p.add_argument(
        "--backend",
        default=None,
        choices=list_backends(),
        help="LLM backend when --classifier=llm (ollama / anthropic / openai).",
    )
    p.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="LLM model when --classifier=llm (e.g. `llama3:8b`).",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text).",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    text = _read_fragment(args)
    if text is None:
        return 2

    source = FragmentSource(args.source)
    classifier = _build_classifier(args)
    if classifier is None:
        return 2

    classification = classifier.classify(text=text, source=source)

    payload = {
        "source": classification.source.value,
        "trust_level": classification.trust_level.value,
        "can_instruct": classification.can_instruct,
        "can_grant_permission": classification.can_grant_permission,
        "contains_untrusted_instruction": classification.contains_untrusted_instruction,
        "matched_patterns": list(classification.matched_patterns),
        "reasoning": classification.reasoning,
    }

    if args.output == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 1 if classification.contains_untrusted_instruction else 0

    info(f"classification ({classifier.name})")
    info("=" * 50)
    info(f"  source:                          {payload['source']}")
    info(f"  trust_level:                     {payload['trust_level']}")
    info(f"  can_instruct:                    {payload['can_instruct']}")
    info(f"  can_grant_permission:            {payload['can_grant_permission']}")
    flag = "YES" if payload["contains_untrusted_instruction"] else "no"
    info(f"  contains_untrusted_instruction:  {flag}")
    if payload["matched_patterns"]:
        info(f"  matched_patterns:                {', '.join(payload['matched_patterns'])}")
    info(f"  reasoning:                       {payload['reasoning']}")

    return 1 if classification.contains_untrusted_instruction else 0


def _read_fragment(args: argparse.Namespace) -> str | None:
    """Resolve the text fragment from --text or --file. Emits a FrameworkError
    on failure and returns None."""
    if args.text is not None:
        return args.text
    path = Path(args.file).resolve()
    if not path.is_file():
        emit(
            FrameworkError(
                summary=f"file not found: {path}",
                fix="Pass a path to an existing file with `--file`.",
            )
        )
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        emit(
            FrameworkError(
                summary=f"could not read {path}: {exc}",
                fix="Check the file's permissions and encoding (UTF-8 expected).",
            )
        )
        return None


def _build_classifier(args: argparse.Namespace) -> InstructionClassifier | None:
    if args.classifier == "heuristic":
        return HeuristicClassifier()
    # LLM path.
    try:
        return LLMInstructionClassifier(
            backend_name=args.backend,
            model=args.model,
        )
    except Exception as exc:  # constructor is forgiving; this is paranoia
        emit(
            FrameworkError(
                summary=f"could not build LLM classifier: {exc}",
                fix=(
                    "Check that the chosen backend is configured. "
                    "For Ollama, ensure `ollama serve` is running."
                ),
            )
        )
        return None


__all__ = ["register", "run"]
