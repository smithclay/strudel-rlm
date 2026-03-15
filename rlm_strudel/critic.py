"""Critic LLM — scores Strudel code on 4 dimensions and provides revision feedback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import dspy

logger = logging.getLogger(__name__)

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

# Multiple regex patterns to handle different LLM output formats:
# "HARMONY: 7/10 — reason", "**Harmony**: 7/10 - reason", "Harmony: 7 / 10 reason", "harmony - 7/10", etc.
_SCORE_PATTERNS = [
    # N/10 format: HARMONY: 7/10 — reason
    re.compile(r"\*{0,2}(harmony|harmonic[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*10(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(rhythm|rhythmic[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*10(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(arrangement|structure[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*10(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(production|mix[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*10(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
]

# N/5 format — scores get doubled to normalize to /10 scale
_SCORE_PATTERNS_5 = [
    re.compile(r"\*{0,2}(harmony|harmonic[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*5(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(rhythm|rhythmic[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*5(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(arrangement|structure[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*5(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
    re.compile(r"\*{0,2}(production|mix[^\*:]*?)\*{0,2}\s*[:|-]\s*(\d{1,2})\s*/\s*5(?:\s*[-—:]\s*(.*))?", re.IGNORECASE),
]

# Map various dimension names to canonical keys
_DIM_NORMALIZE = {
    "harmony": "harmony", "harmonic": "harmony", "harmonic coherence": "harmony",
    "rhythm": "rhythm", "rhythmic": "rhythm", "rhythmic groove": "rhythm",
    "arrangement": "arrangement", "structure": "arrangement", "arrangement & structure": "arrangement",
    "production": "production", "mix": "production", "production quality": "production",
}


def _normalize_dim(raw: str) -> str | None:
    """Normalize a dimension name to a canonical key."""
    raw = raw.strip().lower().strip("*")
    for prefix, canonical in _DIM_NORMALIZE.items():
        if raw.startswith(prefix):
            return canonical
    return None


def parse_critic_output(text: str) -> CriticResult:
    """Parse the critic's textual output into a structured CriticResult.

    Tries multiple regex patterns and normalization strategies to handle
    different LLM output formats (markdown bold, varied punctuation, etc.).
    """
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}

    # Try /10 patterns first
    for pattern in _SCORE_PATTERNS:
        for m in pattern.finditer(text):
            dim = _normalize_dim(m.group(1))
            if dim and dim not in scores:
                scores[dim] = min(int(m.group(2)), 10)
                reason = (m.group(3) or "").strip().rstrip(".")
                if reason:
                    reasons[dim] = reason

    # Try /5 patterns if we're still missing scores
    if len(scores) < 4:
        for pattern in _SCORE_PATTERNS_5:
            for m in pattern.finditer(text):
                dim = _normalize_dim(m.group(1))
                if dim and dim not in scores:
                    scores[dim] = min(int(m.group(2)) * 2, 10)
                    reason = (m.group(3) or "").strip().rstrip(".")
                    if reason:
                        reasons[dim] = reason

    # Fallback: look for any "N/10" or "N/5" near dimension keywords
    if len(scores) < 4:
        for line in text.splitlines():
            line_lower = line.lower()
            for keyword, dim in _DIM_NORMALIZE.items():
                if keyword in line_lower and dim not in scores:
                    # Try N/10 first, then N/5 (scale up to /10)
                    num_match = re.search(r"(\d{1,2})\s*/\s*10", line)
                    if num_match:
                        scores[dim] = min(int(num_match.group(1)), 10)
                    else:
                        num_match = re.search(r"(\d{1,2})\s*/\s*5", line)
                        if num_match:
                            scores[dim] = min(int(num_match.group(1)) * 2, 10)
                    if num_match:
                        after = line[num_match.end():].strip().lstrip("-—: ").strip()
                        if after:
                            reasons[dim] = after.rstrip(".")

    # Parse revisions
    revisions: list[str] = []
    rev_match = re.search(r"REVISIONS?\s*[:]\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    if rev_match:
        rev_text = rev_match.group(1).strip()
        if not re.match(r"none\b", rev_text, re.IGNORECASE):
            for line in rev_text.splitlines():
                line = line.strip()
                line = re.sub(r"^[-*•]\s*", "", line).strip()
                if line and len(line) > 3 and not line.startswith("HARMONY") and not line.startswith("RHYTHM"):
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
        logger.info(f"[critic raw output] {result.evaluation[:500]}")
        parsed = parse_critic_output(result.evaluation)
        logger.info(f"[critic parsed] {parsed}")
        return parsed
