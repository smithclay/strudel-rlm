"""Harvest layer — auto-saves compositions with full observability traces."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


LIBRARY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library")


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# Trace collector — accumulates everything during a run
# ---------------------------------------------------------------------------

@dataclass
class IterationTrace:
    number: int
    code: str
    reasoning: str = ""
    valid: bool = False
    error: str | None = None
    timestamp: str = ""


@dataclass
class CriticRoundTrace:
    round: int
    harmony: int = 5
    rhythm: int = 5
    arrangement: int = 5
    production: int = 5
    average: float = 5.0
    approved: bool = False
    revisions: list[str] = field(default_factory=list)
    strudel_code: str = ""


@dataclass
class RunTrace:
    """Full observability trace for a single RLM run."""

    query: str
    model: str
    started_at: str = ""
    finished_at: str = ""
    iterations: list[IterationTrace] = field(default_factory=list)
    critic_rounds: list[CriticRoundTrace] = field(default_factory=list)
    final_code: str = ""
    final_explanation: str = ""
    total_llm_calls: int = 0
    outcome: str = ""  # "approved", "max_rounds", "error"

    def add_iteration(self, number: int, code: str, reasoning: str = "",
                      valid: bool = False, error: str | None = None):
        self.iterations.append(IterationTrace(
            number=number, code=code, reasoning=reasoning,
            valid=valid, error=error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def add_critic_round(self, round_num: int, critic_result, strudel_code: str):
        self.critic_rounds.append(CriticRoundTrace(
            round=round_num,
            harmony=critic_result.harmony,
            rhythm=critic_result.rhythm,
            arrangement=critic_result.arrangement,
            production=critic_result.production,
            average=critic_result.average,
            approved=critic_result.approved,
            revisions=list(critic_result.revisions),
            strudel_code=strudel_code,
        ))

    def finalize(self, code: str, explanation: str, outcome: str):
        self.final_code = code
        self.final_explanation = explanation
        self.outcome = outcome
        self.finished_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Save to disk
# ---------------------------------------------------------------------------

def save_run(trace: RunTrace) -> str:
    """Save the full harvest — .js composition + .trace.json observability log.

    Returns the path to the saved .js file.
    """
    os.makedirs(LIBRARY_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = _slugify(trace.query)
    basename = f"{timestamp}_{slug}"

    # The composition (.js) — playable in Strudel REPL
    js_path = os.path.join(LIBRARY_DIR, f"{basename}.js")
    best_critic = trace.critic_rounds[-1] if trace.critic_rounds else None
    with open(js_path, "w") as f:
        f.write(f"// Query: {trace.query}\n")
        f.write(f"// Generated: {timestamp} | Model: {trace.model}\n")
        f.write(f"// Outcome: {trace.outcome}\n")
        if best_critic:
            f.write(f"// Critic: H={best_critic.harmony} R={best_critic.rhythm} "
                    f"A={best_critic.arrangement} P={best_critic.production} "
                    f"avg={best_critic.average:.1f}\n")
        f.write(f"// Iterations: {len(trace.iterations)} | "
                f"Debate rounds: {len(trace.critic_rounds)}\n")
        f.write("\n")
        f.write(trace.final_code)
        if not trace.final_code.endswith("\n"):
            f.write("\n")

    # The full trace (.trace.json) — the observability layer
    trace_path = os.path.join(LIBRARY_DIR, f"{basename}.trace.json")
    with open(trace_path, "w") as f:
        json.dump(asdict(trace), f, indent=2, default=str)

    return js_path
