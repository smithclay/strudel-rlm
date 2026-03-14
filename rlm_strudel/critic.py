"""Critic LLM — scores Strudel code on 4 dimensions and provides revision feedback."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import dspy

# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------

CRITIC_RUBRIC = """\
You are a music composition critic specialising in Strudel live-coding.

Score the given Strudel code on FOUR dimensions (1-10 each):

1. **Harmonic Coherence** — Do all melodic/harmonic layers stay in a consistent
   key or mode? Does the bass support the chord roots? Are dissonances
   intentional and musical?
   - 1-3: clashing notes, random pitches, no tonal centre
   - 4-6: mostly in key but some wrong notes or weak voice leading
   - 7-8: clear key centre, bass and chords agree, minor issues only
   - 9-10: perfect key consistency, smooth voice leading, intentional tensions

2. **Rhythmic Groove** — Does the rhythm feel alive and genre-appropriate?
   Is there syncopation where expected? Do layers interlock rather than clash?
   - 1-3: robotic or chaotic, layers step on each other
   - 4-6: basic beat present but stiff, lacks swing or syncopation
   - 7-8: good groove, appropriate feel for the genre, layers mesh well
   - 9-10: infectious groove, masterful syncopation, perfectly interlocking parts

3. **Arrangement & Structure** — Does the piece use arrange() or equivalent
   sectioning? Are there contrasting sections (intro, verse, chorus, outro)?
   Does density evolve over time?
   - 1-3: single loop with no variation or sections
   - 4-6: some variation (e.g. every()) but no real sections
   - 7-8: uses arrange() with clear sections that contrast in energy/density
   - 9-10: compelling arc, builds and releases tension, professional structure

4. **Production Quality** — Are gain levels balanced? Do effects (reverb,
   delay, filter) serve the music? Is the frequency spectrum well-distributed?
   - 1-3: everything same volume, no effects, muddy or thin
   - 4-6: some gain variation, basic effects, but mix could improve
   - 7-8: good balance, effects enhance the mood, clear mix
   - 9-10: polished mix, creative effects, wide stereo, radio-ready

Output format (exactly):
HARMONY: N/10 — reason
RHYTHM: N/10 — reason
ARRANGEMENT: N/10 — reason
PRODUCTION: N/10 — reason
REVISIONS:
- suggestion 1
- suggestion 2
...

If the composition is strong (all dimensions >= 7, average >= 7), write:
REVISIONS: None — composition approved.
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
