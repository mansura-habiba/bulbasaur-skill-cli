"""Skill evaluation — behavioral testing for skills.

Validation is structural (does the manifest parse). Evaluation is behavioral
(given a corpus of test prompts, does the skill produce the right output and
satisfy each declared assertion).

The format follows the LLM-as-judge pattern. Each eval case has a natural-
language prompt, a natural-language `expected_output`, and an `assertions`
list — each assertion is a plain-English claim a judge model scores against
the runtime's actual output.

Pluggable shape:

  Evaluator (ABC)         the strategy interface — BehaviorEvaluator,
                          TriggerEvaluator, InjectionEvaluator,
                          RegressionEvaluator
  Judge (ABC)             scores one assertion against one output —
                          HeuristicJudge (no API key, deterministic),
                          LLMJudge (Phase 4 — Claude Agent SDK adapter)
  EvalRunner              orchestrates loading suites + running evaluators

The eval module reuses the existing `AgentRuntime` abstraction to activate
the skill under test, so the mock runtime works without an API key.
"""

from .base import (
    AssertionResult,
    EvalCase,
    EvalMode,
    EvalReport,
    EvalSuite,
    Evaluator,
    SuiteResult,
)
from .judge import HeuristicJudge, Judge, JudgeVerdict
from .loader import load_suites
from .runner import EvalRunner

__all__ = [
    "AssertionResult",
    "EvalCase",
    "EvalMode",
    "EvalReport",
    "EvalRunner",
    "EvalSuite",
    "Evaluator",
    "HeuristicJudge",
    "Judge",
    "JudgeVerdict",
    "SuiteResult",
    "load_suites",
]
