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

## Output format (MANDATORY — no preamble, start immediately with scores)

HARMONY: 7/10 — [cite specific code] reason
RHYTHM: 6/10 — [cite specific code] reason
ARRANGEMENT: 8/10 — [cite specific code] reason
PRODUCTION: 7/10 — [cite specific code] reason
REVISIONS:
- [section] specific fix with values

## Scoring rubric — cite evidence from the code for EVERY score

HARMONY (key consistency, chord logic, bass support):
- 3/10: notes clash, no key center, bass contradicts chords
- 5/10: mostly in key but some clashing notes, bass sometimes wrong
- 7/10: consistent key, logical progression, bass follows roots
- 9/10: rich voicings (7ths/9ths), voice leading, chromatic color

RHYTHM (genre groove, syncopation, drum interplay):
- 3/10: patterns don't align, wrong feel for genre
- 5/10: basic on-beat patterns, no swing or ghost notes
- 7/10: genre-appropriate groove, some syncopation, layers interlock
- 9/10: infectious groove, varied hi-hat patterns, ghost notes, swing

ARRANGEMENT (structure checklist — score based on how many are met):
Count these concrete criteria:
  A. Uses arrange() with named const sections? (+2 points, starting from base 3)
  B. Has >= 3 distinct sections (intro/verse/chorus/outro)? (+1)
  C. Sections differ in layer count (intro sparse, chorus full)? (+1)
  D. Filter/effect values change between sections (e.g. lpf opens up)? (+1)
  E. Has intro that is sparser than verse? (+1)
  F. Has outro that winds down from chorus? (+1)
Base score is 3. Add points for each criterion met. Cap at 10.
Example: arrange() ✓(+2=5), 4 sections ✓(+1=6), layer contrast ✓(+1=7), filter contrast ✓(+1=8), sparse intro ✓(+1=9), outro winds down ✓(+1=10) → ARRANGEMENT: 10/10

PRODUCTION (mix balance, effects serve music, frequency spread):
- 3/10: all layers same gain, no effects, muddy
- 5/10: some gain variation, basic lpf, one effect
- 7/10: balanced gains, lpf+room+delay, effects match genre
- 9/10: layered effects, frequency separation, crush/shape for texture

## Revision rules — for each dimension below 7:
- Name the specific section and layer
- Give a concrete fix with actual values (e.g. "change lpf(400) to lpf(1200)")
- Do NOT give vague feedback

If all scores >= 7: REVISIONS: None — composition approved.

## Example evaluation (study this for calibration)

HARMONY: 8/10 — I-vi-IV-V in C major with 7th chords in chorus "[c3,e3,g3,b3]", bass follows roots "<c2 a1 f1 g1>"
RHYTHM: 7/10 — boom-bap kick "bd ~ [~ bd] ~" with ghost note, snare on 2&4, but hi-hats "hh*8" are mechanical
ARRANGEMENT: 9/10 — arrange() with 4 const sections, intro has 3 layers vs chorus has 6, lpf opens 600→1200, outro strips to pad+kick
PRODUCTION: 7/10 — gains balanced (0.15-0.7 range), room(0.4) and delay(0.2) add space, but no crush or shape for lo-fi texture
REVISIONS:
- [verse] hi-hats too mechanical: change "hh*8" to "[hh hh] [hh hh] [hh hh] [hh ~]" for shuffle
- [chorus] add .crush(12) on chord pad for lo-fi character

CRITICAL: Use 1-10 scale. Write "7/10" NOT "3.5/5". Cite code evidence for every score.
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
        elif self.approved:
            lines.append("REVISIONS: None — composition approved.")
        else:
            # Scores are below threshold but no specific revisions were parsed.
            # Generate generic feedback from low-scoring dimensions so the
            # composer knows what to fix.
            lines.append("REVISIONS:")
            for dim, score in [("harmony", self.harmony), ("rhythm", self.rhythm),
                               ("arrangement", self.arrangement), ("production", self.production)]:
                if score < 7:
                    reason = self.reasons.get(dim, "needs improvement")
                    lines.append(f"  - [{dim}] scored {score}/10 — {reason}")
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
    "harmonic quality": "harmony", "harmonic dimension": "harmony",
    "melodic": "harmony", "harmonic & melodic": "harmony",
    "rhythm": "rhythm", "rhythmic": "rhythm", "rhythmic groove": "rhythm",
    "rhythmic quality": "rhythm", "rhythmic dimension": "rhythm",
    "rhythmic programming": "rhythm", "beat": "rhythm",
    "arrangement": "arrangement", "structure": "arrangement", "arrangement & structure": "arrangement",
    "structural": "arrangement", "structural quality": "arrangement",
    "arrangement dimension": "arrangement",
    "production": "production", "mix": "production", "production quality": "production",
    "production dimension": "production", "sound design": "production",
}


def _normalize_dim(raw: str) -> str | None:
    """Normalize a dimension name to a canonical key."""
    raw = raw.strip().lower().strip("*")
    for prefix, canonical in _DIM_NORMALIZE.items():
        if raw.startswith(prefix):
            return canonical
    return None


def _clean_reason(text: str) -> str:
    """Strip markdown artifacts from a reason string."""
    text = re.sub(r"\*+", "", text).strip().rstrip(".-—: ")
    return text if len(text) > 2 else ""


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
                reason = _clean_reason(m.group(3) or "")
                if reason:
                    reasons[dim] = reason

    # Try /5 patterns if we're still missing scores
    if len(scores) < 4:
        for pattern in _SCORE_PATTERNS_5:
            for m in pattern.finditer(text):
                dim = _normalize_dim(m.group(1))
                if dim and dim not in scores:
                    raw_score = int(m.group(2))
                    scores[dim] = min(raw_score * 2, 10)
                    logger.warning(f"[critic] /5 fallback fired: {dim}={raw_score}/5 → {scores[dim]}/10")
                    reason = _clean_reason(m.group(3) or "")
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

    # Last resort: bare number after dimension keyword (e.g. "**Harmonic Quality:** 4.")
    if len(scores) < 4:
        for line in text.splitlines():
            line_lower = line.lower()
            for keyword, dim in _DIM_NORMALIZE.items():
                if keyword in line_lower and dim not in scores:
                    # Match "keyword:** N." or "keyword: N." or "keyword - N."
                    bare_match = re.search(
                        r"(?:{})\s*(?:\*{{0,2}})\s*[:|-]\s*(\d{{1,2}})(?:\s*\.|[,\s])".format(re.escape(keyword)),
                        line_lower,
                    )
                    if bare_match:
                        raw = int(bare_match.group(1))
                        # If score is 1-5, assume /5 scale and double
                        if raw <= 5:
                            scores[dim] = min(raw * 2, 10)
                            logger.warning(f"[critic] bare-number fallback: {dim}={raw} → {scores[dim]}/10 (assumed /5)")
                        else:
                            scores[dim] = min(raw, 10)
                            logger.warning(f"[critic] bare-number fallback: {dim}={raw}/10")

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

    # Fallback: extract *Improvement:* or *Suggestion:* lines from prose output
    # (Gemini Flash often embeds feedback inline instead of a REVISIONS block)
    if not revisions:
        for m in re.finditer(
            r"\*(?:Improvement|Suggestion|Fix|Issue|Recommendation)[:]*\*\s*[:]*\s*(.+)",
            text, re.IGNORECASE,
        ):
            rev = m.group(1).strip().rstrip(".")
            if rev and len(rev) > 5:
                revisions.append(rev)

    # Second fallback: pull bullet points that look like actionable feedback
    if not revisions:
        for line in text.splitlines():
            line = line.strip()
            # Match lines starting with - or * that contain actionable keywords
            bullet = re.match(r"^[-*•]\s+(.+)", line)
            if bullet:
                content = bullet.group(1).strip()
                # Filter for lines that look like revision suggestions
                action_words = ("add", "change", "increase", "decrease", "open", "remove",
                                "replace", "use", "try", "consider", "swap", "introduce")
                if any(content.lower().startswith(w) for w in action_words) and len(content) > 10:
                    revisions.append(content.rstrip("."))

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
        # Use low temperature for consistent scoring (LLM-as-judge best practice)
        with dspy.context(lm=dspy.settings.lm.copy(temperature=0.0)):
            result = self.predict(query=query, strudel_code=strudel_code)
        logger.info(f"[critic raw output] {result.evaluation[:500]}")
        parsed = parse_critic_output(result.evaluation)
        logger.info(f"[critic parsed] {parsed}")
        return parsed
