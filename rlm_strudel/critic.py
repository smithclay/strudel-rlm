"""Critic LLM — scores Strudel code on 4 dimensions and provides revision feedback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import NamedTuple

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

PRODUCTION (mix clarity, gain staging, mid-range presence):
- 3/10: all layers same gain, chords muffled (lpf < 600), no effects, bass inaudible
- 5/10: some gain variation, chords still dark (lpf < 800), one effect type
- 7/10: clear gain hierarchy (bass 0.7+, chords 0.4-0.6, hats 0.2-0.35), chords lpf 700-1200, delay on 2+ layers
- 9/10: every layer audible at intended level, warm mid-range (lpf 800-1200 on chords), bass with harmonics (sawtooth not sine), delay creates depth without muddiness

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

CRITIC_STRUCTURED_INSTRUCTIONS = """\
Evaluate the composition with the same rubric, but return typed fields instead of a free-form block.

Rules:
- `harmony`, `rhythm`, `arrangement`, and `production` must be integers from 1 to 10.
- Each `*_reason` must cite concrete evidence from the code.
- `revisions` must be a list of concrete fixes with values and `[section]` prefixes.
- If all scores are at least 7, return an empty `revisions` list.
"""

# ---------------------------------------------------------------------------
# DSPy Signature
# ---------------------------------------------------------------------------


class CriticSignature(dspy.Signature):
    """Evaluate Strudel code quality on harmonic, rhythmic, structural, and production dimensions."""

    query: str = dspy.InputField(desc="The original user request / music prompt")
    strudel_code: str = dspy.InputField(desc="The Strudel code to evaluate")
    evaluation: str = dspy.OutputField(desc="Rubric scores and revision suggestions")


class CriticStructuredSignature(dspy.Signature):
    """Evaluate Strudel code and return structured rubric fields."""

    query: str = dspy.InputField(desc="The original user request / music prompt")
    strudel_code: str = dspy.InputField(desc="The Strudel code to evaluate")
    harmony: int = dspy.OutputField(desc="Harmony score from 1 to 10")
    harmony_reason: str = dspy.OutputField(desc="Code-cited reason for the harmony score")
    rhythm: int = dspy.OutputField(desc="Rhythm score from 1 to 10")
    rhythm_reason: str = dspy.OutputField(desc="Code-cited reason for the rhythm score")
    arrangement: int = dspy.OutputField(desc="Arrangement score from 1 to 10")
    arrangement_reason: str = dspy.OutputField(desc="Code-cited reason for the arrangement score")
    production: int = dspy.OutputField(desc="Production score from 1 to 10")
    production_reason: str = dspy.OutputField(desc="Code-cited reason for the production score")
    revisions: list[str] = dspy.OutputField(desc="Concrete revision fixes with [section] prefixes")


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
        return self.min_score >= 7

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

    # Split into lines for multi-line reason extraction
    text_lines = text.splitlines()

    # Try /10 patterns first
    for pattern in _SCORE_PATTERNS:
        for m in pattern.finditer(text):
            dim = _normalize_dim(m.group(1))
            if dim and dim not in scores:
                scores[dim] = min(int(m.group(2)), 10)
                reason = _clean_reason(m.group(3) or "")
                # Gemini multi-line: if reason is empty, grab indented bullets on following lines
                if not reason:
                    match_line_idx = text[:m.start()].count('\n')
                    reason_parts: list[str] = []
                    for subsequent in text_lines[match_line_idx + 1:]:
                        stripped = subsequent.strip().lstrip("*•- ")
                        # Stop at next score line (contains N/10 or N/5), empty line, or REVISIONS
                        if not subsequent.strip():
                            break
                        if re.search(r'\d{1,2}\s*/\s*(?:10|5)', subsequent):
                            break
                        if re.match(r'REVISIONS?\s*:', subsequent, re.IGNORECASE):
                            break
                        # Grab indented bullet content
                        bullet = re.match(r'^[\s*•-]+(.+)', subsequent)
                        if bullet:
                            reason_parts.append(_clean_reason(bullet.group(1)))
                    if reason_parts:
                        reason = "; ".join(p for p in reason_parts if p)
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
        for line_idx, line in enumerate(text_lines):
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
                        after = _clean_reason(line[num_match.end():])
                        if not after:
                            # Multi-line: grab indented bullets below
                            reason_parts_fb: list[str] = []
                            for subsequent in text_lines[line_idx + 1:]:
                                if not subsequent.strip():
                                    break
                                if re.search(r'\d{1,2}\s*/\s*(?:10|5)', subsequent):
                                    break
                                if re.match(r'REVISIONS?\s*:', subsequent, re.IGNORECASE):
                                    break
                                bullet = re.match(r'^[\s*•-]+(.+)', subsequent)
                                if bullet:
                                    reason_parts_fb.append(_clean_reason(bullet.group(1)))
                            if reason_parts_fb:
                                after = "; ".join(p for p in reason_parts_fb if p)
                        if after:
                            reasons[dim] = after

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


def _clamp_score(value, default: int = 5) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, score))


def _normalize_revisions(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = [str(item) for item in value]
    cleaned = [item.strip() for item in items if str(item).strip()]
    if cleaned and cleaned[0].lower().startswith("none"):
        return []
    return cleaned


def structured_prediction_to_result(result) -> CriticResult:
    """Convert a typed DSPy prediction into a CriticResult."""
    return CriticResult(
        harmony=_clamp_score(getattr(result, "harmony", 5)),
        rhythm=_clamp_score(getattr(result, "rhythm", 5)),
        arrangement=_clamp_score(getattr(result, "arrangement", 5)),
        production=_clamp_score(getattr(result, "production", 5)),
        reasons={
            "harmony": str(getattr(result, "harmony_reason", "") or "").strip(),
            "rhythm": str(getattr(result, "rhythm_reason", "") or "").strip(),
            "arrangement": str(getattr(result, "arrangement_reason", "") or "").strip(),
            "production": str(getattr(result, "production_reason", "") or "").strip(),
        },
        revisions=_normalize_revisions(getattr(result, "revisions", [])),
    )


# ---------------------------------------------------------------------------
# Mechanical production analysis — shared detection layer
# ---------------------------------------------------------------------------


class LineFinding(NamedTuple):
    """A per-line issue found by mechanical analysis."""
    line_idx: int
    message: str


def _analyze_lines(code: str) -> tuple[list[LineFinding], list[str]]:
    """Shared detection logic for mechanical production analysis.

    Returns:
        line_findings: per-line issues with line index and message
        structural: whole-composition issues (not tied to a single line)
    """
    lines = code.splitlines()
    line_findings: list[LineFinding] = []
    structural: list[str] = []

    # --- Per-line checks ---
    total_room_count = len(re.findall(r'\.room\(', code))
    room_seen = 0

    for idx, line in enumerate(lines):
        # LPF checks — creative nudges, not error reports
        for m in re.finditer(r'\.lpf\((\d+)\)', line):
            val = int(m.group(1))
            is_bass = bool(re.search(r'(?:bass|jvbass|"sine")', line, re.IGNORECASE)) and \
                      bool(re.search(r'note\(".*?[0-2]"?\)', line))
            if is_bass and val < 200:
                line_findings.append(LineFinding(idx, "this bass is all sub — give it some teeth with sawtooth + lpf(300-400) so it translates on small speakers"))
            elif not is_bass:
                if val < 700:
                    line_findings.append(LineFinding(idx, f"this layer is hiding behind lpf({val}) — let it breathe, open the filter to 700-1200 so the mid-range sings"))
                elif val > 2000:
                    line_findings.append(LineFinding(idx, f"lpf({val}) is wide open — could get harsh in the mix, try 700-1200 for warmth with presence"))

        # Gain checks
        for m in re.finditer(r'\.gain\(([\d.]+)\)', line):
            g = float(m.group(1))
            is_melodic = bool(re.search(r'note\(|\.s\("(?:sawtooth|triangle|square)"', line))
            if g < 0.15:
                line_findings.append(LineFinding(idx, f"gain({g}) — this voice is whispering, bring it up to at least 0.15 so it's part of the conversation"))
            elif is_melodic and g < 0.35:
                line_findings.append(LineFinding(idx, f"gain({g}) on a melodic layer — this should be a lead voice, not background, try 0.3-0.5"))

        # Room check — flag .room() on 4th+ layer when total > 6
        if '.room(' in line:
            room_seen += 1
            if total_room_count > 6 and room_seen >= 4:
                line_findings.append(LineFinding(idx, "reverb on everything washes out the depth — pick 1-3 layers that deserve the space and let the rest stay dry"))

    # --- Structural suggestions ---
    has_delay = bool(re.search(r'\.delay\(', code))
    if not has_delay:
        structural.append("No delay anywhere — delay is the secret weapon for depth and groove, try it on a chord or percussion layer")

    has_repetition = bool(re.search(r'\[.*?verse\].*\[.*?chorus\].*\[.*?verse\]', code, re.DOTALL))
    if not has_repetition:
        structural.append("No verse-chorus repetition — repeating sections lets the listener lock in and feel the groove build")

    # Layer count per section
    sections = re.split(r'const\s+\w+\s*=\s*stack\s*\(', code)
    max_layers = 0
    for section in sections:
        layer_count = section.count('\n  s(') + section.count('\n  note(') + section.count('\ns(') + section.count('\nnote(')
        max_layers = max(max_layers, layer_count)
    if max_layers > 8:
        structural.append(f"~{max_layers} layers competing — a tight 5-7 layer mix has more punch than a crowded 10, each voice gets room to speak")

    return line_findings, structural


def critique_code_inline(code: str) -> str:
    """Return code with inline ``// IDEA:`` comments suggesting creative improvements.

    Strips any existing ``// IDEA`` / ``// CRITIC`` comments first to avoid
    accumulation, then appends per-line suggestions and prepends structural ideas.
    """
    # Strip existing annotations (both old CRITIC and new IDEA format)
    stripped_lines: list[str] = []
    for line in code.splitlines():
        cleaned = re.sub(r'\s*//\s*(?:CRITIC(?:-STRUCTURAL)?|IDEA(?:-BIG)?):.*$', '', line)
        stripped_lines.append(cleaned)

    line_findings, structural = _analyze_lines("\n".join(stripped_lines))

    # Build index of findings per line
    findings_by_line: dict[int, list[str]] = {}
    for lf in line_findings:
        findings_by_line.setdefault(lf.line_idx, []).append(lf.message)

    # Annotate lines
    result_lines: list[str] = []

    # Prepend structural ideas as a block
    for s in structural:
        result_lines.append(f"// IDEA-BIG: {s}")
    if structural:
        result_lines.append("")

    for idx, line in enumerate(stripped_lines):
        if idx in findings_by_line:
            comments = "; ".join(findings_by_line[idx])
            result_lines.append(f"{line}  // IDEA: {comments}")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def analyze_production(code: str) -> str:
    """Scan Strudel code for measurable production facts.

    Returns a text block suitable for injection into the critic prompt so the
    LLM can't overlook concrete issues like muffled filters or inaudible gains.
    """
    line_findings, structural = _analyze_lines(code)

    findings: list[str] = []

    # Flatten per-line findings into summary text
    # Group similar issues rather than listing every line
    lpf_muffled = [lf for lf in line_findings if "hiding behind lpf(" in lf.message]
    lpf_harsh = [lf for lf in line_findings if "could get harsh" in lf.message]
    sine_bass = [lf for lf in line_findings if "bass is all sub" in lf.message]
    gain_inaudible = [lf for lf in line_findings if "voice is whispering" in lf.message]
    gain_quiet = [lf for lf in line_findings if "melodic layer" in lf.message]
    room_excess = [lf for lf in line_findings if "washes out the depth" in lf.message]

    if lpf_muffled:
        vals = re.findall(r'lpf\((\d+)\)', " ".join(lf.message for lf in lpf_muffled))
        max_val = max(int(v) for v in vals) if vals else 0
        findings.append(f"PROBLEM: All non-bass layers have lpf <= {max_val}Hz — mix sounds muffled. Chords need lpf 700-1200.")
    if lpf_harsh:
        vals = re.findall(r'lpf\((\d+)\)', " ".join(lf.message for lf in lpf_harsh))
        max_val = max(int(v) for v in vals) if vals else 0
        findings.append(f"WARNING: Non-bass lpf goes up to {max_val}Hz — may sound harsh. Sweet spot is 700-1200 for chords.")
    if sine_bass:
        findings.append("NOTE: Bass uses sine — lacks harmonics. Sawtooth with lpf(300-400) translates better on all speakers.")
    if gain_inaudible:
        findings.append(f"PROBLEM: {len(gain_inaudible)} layer(s) with gain < 0.15 — inaudible.")
    if gain_quiet:
        findings.append(f"PROBLEM: All melodic/harmonic layers have gain too quiet — needs 0.3-0.5.")
    if room_excess:
        findings.append(f"WARNING: .room() on too many layers — too much reverb muddies the mix. Use on 1-3 layers.")

    # Structural findings
    for s in structural:
        if "delay" in s.lower():
            findings.append("MISSING: No .delay() — delay is the primary depth/space effect.")
        elif "repetition" in s.lower():
            findings.append("NOTE: No verse-chorus repetition detected. Repeating sections improves musical coherence.")
        elif "layers" in s.lower():
            findings.append(f"WARNING: Densest section has {s.split('~')[1].split('layers')[0].strip() if '~' in s else '8+'} layers — too many competing elements. 5-7 is the sweet spot.")

    if not findings:
        return "CODE ANALYSIS: No production issues detected."

    return "CODE ANALYSIS (mechanical scan — address these in PRODUCTION score):\n" + "\n".join(f"  - {f}" for f in findings)


# ---------------------------------------------------------------------------
# Critic module
# ---------------------------------------------------------------------------


class StrudelCritic:
    """DSPy-based critic that scores Strudel compositions."""

    def __init__(self) -> None:
        self.predict_structured = dspy.Predict(
            CriticStructuredSignature,
            instructions=CRITIC_STRUCTURED_INSTRUCTIONS,
        )
        self.predict_text = dspy.Predict(CriticSignature, instructions=CRITIC_RUBRIC)

    def evaluate(self, query: str, strudel_code: str) -> CriticResult:
        # Mechanical pre-analysis — gives the LLM concrete facts to anchor on
        analysis = analyze_production(strudel_code)
        logger.info(f"[critic] {analysis}")
        augmented_code = f"{analysis}\n\n{strudel_code}"

        # Use low temperature for consistent scoring (LLM-as-judge best practice)
        with dspy.context(lm=dspy.settings.lm.copy(temperature=0.0)):
            try:
                result = self.predict_structured(query=query, strudel_code=augmented_code)
                parsed = structured_prediction_to_result(result)
                logger.info(
                    "[critic structured] H=%s R=%s A=%s P=%s revisions=%s",
                    parsed.harmony,
                    parsed.rhythm,
                    parsed.arrangement,
                    parsed.production,
                    len(parsed.revisions),
                )
                return parsed
            except Exception as exc:
                logger.warning(f"[critic structured] Falling back to text parser: {exc}")
                result = self.predict_text(query=query, strudel_code=augmented_code)

        logger.info(f"[critic raw output] {result.evaluation[:500]}")
        parsed = parse_critic_output(result.evaluation)
        logger.info(f"[critic parsed] {parsed}")
        return parsed
