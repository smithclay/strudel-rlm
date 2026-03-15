"""Sanitize Strudel code — strip markdown, commentary, forbidden functions, stray .play() calls."""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


def extract_section_code(raw: str) -> str:
    """Extract clean inner-stack code from any LLM output format.

    Handles: raw lines, stack() wrapper, const NAME = stack(...), arrange(...) blocks.
    Returns just the inner contents suitable for wrapping in stack().
    """
    # Strip markdown fences first
    raw = re.sub(r"```(?:javascript|js|strudel)?\s*\n?", "", raw).strip()

    # If output contains arrange(...), extract only the first stack() body and warn
    if "arrange(" in raw:
        logger.warning("[extract_section_code] Output contains arrange() — extracting first stack() body only")
        body = _extract_first_stack_body(raw)
        if body is not None:
            return body

    # If output contains `const NAME = stack(`, extract the inner contents
    const_match = re.search(r"const\s+\w+\s*=\s*stack\s*\(", raw)
    if const_match:
        body = _extract_paren_contents(raw, const_match.end() - 1)
        if body is not None:
            return _strip_trailing_chains(body)

    # If output is wrapped in stack(...), extract inner contents
    stack_match = re.match(r"^\s*stack\s*\(", raw)
    if stack_match:
        body = _extract_paren_contents(raw, stack_match.end() - 1)
        if body is not None:
            return _strip_trailing_chains(body)

    # No wrappers — return as-is (already just inner lines), but strip trailing chains
    return _strip_trailing_chains(raw)


def _extract_first_stack_body(code: str) -> str | None:
    """Extract the body of the first stack() call in the code."""
    match = re.search(r"stack\s*\(", code)
    if match:
        return _extract_paren_contents(code, match.end() - 1)
    return None


def _extract_paren_contents(code: str, open_pos: int) -> str | None:
    """Extract contents between matching parens using depth counting.

    open_pos should point to the opening '('.
    """
    if open_pos >= len(code) or code[open_pos] != "(":
        return None
    depth = 0
    start = open_pos + 1
    for i in range(open_pos, len(code)):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                inner = code[start:i].strip()
                # Remove leading/trailing newlines but preserve internal structure
                return inner
    return None


def _strip_trailing_chains(code: str) -> str:
    """Strip trailing .cpm(N).play() or .play() chains from code."""
    code = code.strip()
    # Remove trailing .play() and optional semicolons
    code = re.sub(r"\s*\.play\(\)\s*;?\s*$", "", code)
    # Remove trailing .cpm(N)
    code = re.sub(r"\s*\.cpm\(\d+\)\s*$", "", code)
    # One more pass in case .cpm came before .play
    code = re.sub(r"\s*\.play\(\)\s*;?\s*$", "", code)
    return code.strip()


def sanitize_strudel(code: str) -> str:
    """Clean up LLM-generated Strudel code.

    Strips markdown fences, inline commentary, forbidden function calls,
    and stray .play() calls from mid-composition sections.
    Returns clean Strudel code ready for browser eval.
    """
    # Remove markdown code fences
    code = re.sub(r"```(?:javascript|js|strudel)?\s*\n?", "", code)

    # Remove lines that are pure markdown (headers, bullets, bold text, blank explanations)
    cleaned_lines = []
    in_code = False
    for line in code.splitlines():
        stripped = line.strip()

        # Skip markdown headers
        if stripped.startswith("###") or stripped.startswith("##") or stripped.startswith("#"):
            continue

        # Skip markdown list items that aren't Strudel comments
        if stripped.startswith("*") and not stripped.startswith("*/"):
            # Check if it looks like markdown (bold, list) vs multiplication
            if re.match(r"^\*{1,2}\s*[A-Z]", stripped):
                continue
            if re.match(r"^\*\s+", stripped):
                continue

        # Skip lines that are pure prose (no code-like characters)
        if stripped and not stripped.startswith("//"):
            # Remove inline backtick-quoted code before checking
            no_backticks = re.sub(r"`[^`]+`", "", stripped)
            code_chars = set("(){}[];=.,<>")
            has_code = any(c in no_backticks for c in code_chars)
            if not has_code and len(stripped.split()) > 3:
                continue
            # Also catch sentences that start with "Here is" / "This is" / "I have" etc.
            if re.match(r"^(Here|This|That|I |The |It |Note:|To |Using|For )", stripped):
                continue

        # Keep the line
        cleaned_lines.append(line)

    code = "\n".join(cleaned_lines)

    # Remove stray .play() from mid-composition (keep only the final one)
    # Strategy: remove all .play() then add it back at the end
    play_count = code.count(".play()")
    if play_count > 1:
        # Remove all .play() and their trailing semicolons
        code = re.sub(r"\.play\(\)\s*;?", "", code)
        # Add .play() at the very end
        code = code.rstrip().rstrip(";") + "\n.play()\n"

    # Replace forbidden function calls with valid alternatives
    replacements = [
        (r"\.adsr\(\s*[\d.,\s]+\)", ""),  # Remove .adsr() — user should use separate attack/decay/sustain/release
        (r'\.s\("gm_\w+"\)', '.s("sine")'),
        (r'\.s\("supersaw"\)', '.s("sawtooth")'),
        (r'\.s\("superpulse"\)', '.s("square")'),
        (r'\.s\("superreese"\)', '.s("sawtooth")'),
        (r'\.s\("melodica"\)', '.s("sawtooth")'),
        (r"\.sound\(\)", ""),  # Remove empty .sound() calls
        (r'\.sound\("(\w+)"\)', r'.s("\1")'),  # .sound("x") → .s("x")
        (r"\.distort\([\d.]+\)", ""),  # Remove .distort()
        (r"\.lpq\([\d.]+\)", ""),  # Remove .lpq()
        (r"\.fadeIn\([\d.]+\)", ""),  # Remove .fadeIn()
        (r"\.fadeOut\([\d.]+\)", ""),  # Remove .fadeOut()
        (r'\.arp\("(?!up"|down"|updown")\w+"\)', '.arp("up")'),  # Fix invalid arp modes
        (r"line\([\d.,\s]+\)", "0.3"),  # Replace line() with static value
    ]

    for pattern, replacement in replacements:
        code = re.sub(pattern, replacement, code)

    # Clean up empty chains (consecutive dots from removed methods)
    code = re.sub(r"\.\.", ".", code)
    # Clean up trailing commas before )
    code = re.sub(r",\s*\)", ")", code)

    # Remove excessive blank lines
    code = re.sub(r"\n{3,}", "\n\n", code)

    return code.strip() + "\n"


# Patterns that indicate hallucinated/forbidden API usage
_SEMANTIC_VIOLATIONS = [
    (r"\.bank\(", ".bank() — banks are not loaded"),
    (r"\.distort\(", ".distort() — use .shape(0-1) instead"),
    (r"\.lpq\(", ".lpq() — use .resonance(0-40) instead"),
    (r"\.res\(", ".res() — use .resonance(0-40) instead"),
    (r"\.adsr\(", ".adsr() — use separate .attack()/.decay()/.sustain()/.release()"),
    (r"\.fadeIn\(", ".fadeIn() — does not exist"),
    (r"\.fadeOut\(", ".fadeOut() — does not exist"),
    (r"\.perc\(", ".perc() — use .decay() and .sustain(0) instead"),
    (r"\.chord\(", ".chord() — use comma-separated notes in note()"),
    (r"\.euclid\(", ".euclid() — use mini-notation s(\"bd(3,8)\") instead"),
    (r"\bpattern\(", "pattern() — does not exist"),
    (r"\bperlin\b", "perlin — does not exist"),
    (r"patterns\.\w+", "patterns.* — does not exist"),
    (r"sine\.range\(", "sine.range() — does not exist"),
    (r"\bsaw\(", "saw() — does not exist as standalone"),
    (r"\.arp\(\"(?!up\"|down\"|updown\")", "invalid arp mode — only up/down/updown"),
    (r'\.s\("supersaw"\)', "supersaw — use sawtooth instead"),
    (r'\.s\("superpulse"\)', "superpulse — use square instead"),
    (r'\.s\("superreese"\)', "superreese — use sawtooth instead"),
    (r'\.s\("melodica"\)', "melodica — use sawtooth instead"),
    (r'\.s\("gm_\w+"\)', "gm_* synths — not available"),
    (r"\bsetbpm\b", "setbpm — use .cpm(N) instead"),
    (r"\bline\(", "line() — does not exist"),
    (r"note\([^)]*'[0-9]", "chord shorthand (e.g. '7) — use comma-separated notes"),
]


def validate_semantic(code: str) -> list[str]:
    """Check for forbidden/hallucinated API patterns in Strudel code.

    Returns a list of violation descriptions. Empty list means clean.
    """
    violations = []
    for pattern, description in _SEMANTIC_VIOLATIONS:
        if re.search(pattern, code):
            violations.append(description)
    return violations
