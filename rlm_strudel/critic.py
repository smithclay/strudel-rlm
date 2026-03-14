"""Critic LLM — scores Strudel code on 4 dimensions and provides revision feedback."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import dspy

# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------

CRITIC_RUBRIC = """\
You are a music critic evaluating Strudel live-coding compositions.

Score on 4 dimensions (1-10). You MUST use EXACTLY this output format:

HARMONY: 7/10 — all layers in C minor, bass supports roots
RHYTHM: 6/10 — groove is stiff, needs syncopation
ARRANGEMENT: 8/10 — good use of arrange() with contrasting sections
PRODUCTION: 7/10 — balanced mix, reverb serves the mood
REVISIONS:
- add syncopated kick pattern
- open filter in chorus for more energy

Scoring guide:
- HARMONY: key consistency, chord logic, bass support. 1-3=clashing, 4-6=mostly ok, 7-9=solid, 10=beautiful
- RHYTHM: genre-appropriate groove, syncopation, interlocking layers. 1-3=broken, 4-6=stiff, 7-9=groovy, 10=infectious
- ARRANGEMENT: uses arrange() with sections? contrast? tension/release? 1-3=one loop, 4-6=some variation, 7-9=clear sections, 10=compelling journey
- PRODUCTION: gain balance, effects serve music, frequency spread. 1-3=muddy, 4-6=basic, 7-9=polished, 10=professional

If all scores >= 7, write: REVISIONS: None — composition approved.

IMPORTANT: Start your response with the four score lines. Do not add preamble.
"""

# ---------------------------------------------------------------------------
# DSPy Signature
# ---------------------------------------------------------------------------


class CriticSignature(dspy.Signature):
    """Evaluate Strudel code quality on harmonic, rhythmic, structural, and production dimensions."""

    query: str = dspy.InputField(desc="The original user request / music prompt")
    strudel_code: str = dspy.InputField(desc="The Strudel code to evaluate")
    evaluation: str = dspy.OutputField(desc="Rubric scores and revision suggestions")


# ---------------------------------------------------------------------------
# Parsed result
# ---------------------------------------------------------------------------


@dataclass
class CriticResult:
    """Parsed critic evaluation with scores and feedback."""

    harmony: int = 5
    rhythm: int = 5
    arrangement: int = 5
    production: int = 5
    reasons: dict = field(default_factory=dict)
    revisions: list[str] = field(default_factory=list)

    @property
    def average(self) -> float:
        return (self.harmony + self.rhythm + self.arrangement + self.production) / 4.0

    @property
    def min_score(self) -> int:
        return min(self.harmony, self.rhythm, self.arrangement, self.production)

    @property
    def approved(self) -> bool:
        return self.average >= 7.0 and self.min_score >= 6

    def format_feedback(self) -> str:
        lines = [
            f"HARMONY:     {self.harmony}/10 — {self.reasons.get('harmony', '')}",
            f"RHYTHM:      {self.rhythm}/10 — {self.reasons.get('rhythm', '')}",
            f"ARRANGEMENT: {self.arrangement}/10 — {self.reasons.get('arrangement', '')}",
            f"PRODUCTION:  {self.production}/10 — {self.reasons.get('production', '')}",
            f"AVERAGE:     {self.average:.1f}/10  (min {self.min_score})",
            "",
        ]
        if self.revisions:
            lines.append("REVISIONS:")
            for rev in self.revisions:
                lines.append(f"  - {rev}")
        else:
            lines.append("REVISIONS: None — composition approved.")
        return "\n".join(lines)

    def __repr__(self) -> str:
        status = "APPROVED" if self.approved else "NEEDS WORK"
        return (
            f"CriticResult({status} avg={self.average:.1f} "
            f"H={self.harmony} R={self.rhythm} A={self.arrangement} P={self.production})"
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SCORE_RE = re.compile(
    r"(harmony|rhythm|arrangement|production)\s*:\s*(\d{1,2})\s*/\s*10(?:\s*[-—]\s*(.*))?",
    re.IGNORECASE,
)

_DIMENSION_MAP = {
    "harmony": "harmony",
    "rhythm": "rhythm",
    "arrangement": "arrangement",
    "production": "production",
}


def parse_critic_output(text: str) -> CriticResult:
    """Parse the critic's textual output into a structured CriticResult."""
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}

    for m in _SCORE_RE.finditer(text):
        dim = _DIMENSION_MAP[m.group(1).lower()]
        scores[dim] = int(m.group(2))
        reason = (m.group(3) or "").strip()
        if reason:
            reasons[dim] = reason

    # Parse revisions
    revisions: list[str] = []
    rev_match = re.search(r"REVISIONS?\s*:\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    if rev_match:
        rev_text = rev_match.group(1).strip()
        # Check for "None" / approved
        if not re.match(r"none\b", rev_text, re.IGNORECASE):
            for line in rev_text.splitlines():
                line = line.strip()
                line = re.sub(r"^[-*]\s*", "", line).strip()
                if line:
                    revisions.append(line)

    return CriticResult(
        harmony=scores.get("harmony", 5),
        rhythm=scores.get("rhythm", 5),
        arrangement=scores.get("arrangement", 5),
        production=scores.get("production", 5),
        reasons=reasons,
        revisions=revisions,
    )


# ---------------------------------------------------------------------------
# Critic module
# ---------------------------------------------------------------------------


class StrudelCritic:
    """DSPy-based critic that scores Strudel compositions."""

    def __init__(self) -> None:
        self.predict = dspy.Predict(CriticSignature, instructions=CRITIC_RUBRIC)

    def evaluate(self, query: str, strudel_code: str) -> CriticResult:
        result = self.predict(query=query, strudel_code=strudel_code)
        return parse_critic_output(result.evaluation)
