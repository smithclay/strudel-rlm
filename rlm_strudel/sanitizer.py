"""Sanitize Strudel code — strip markdown, commentary, forbidden functions, stray .play() calls."""

from __future__ import annotations

import re


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
