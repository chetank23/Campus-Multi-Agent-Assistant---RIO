"""
agents/common/formatter.py
--------------------------
Centralized plain-English formatting and sanitization utility for RIO-MJP.
Enforces the mandatory plain-English response policy:
- No emojis or decorative Unicode icons.
- No markdown headings (#, ##, ###).
- No bold or italic asterisks (**bold**, *italic*).
- Preserves dates, times, IDs, numbers, punctuation, and hyphens for lists.
"""

from __future__ import annotations

import re

# Comprehensive regex matching decorative emojis and pictograms
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U0001F900-\U0001F9FF"  # supplemental symbols and pictographs
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
    "\u2700-\u27BF"          # dingbats
    "\u2600-\u26FF"          # miscellaneous symbols
    "\u2B50\u2B55\u231A\u231B\u23E9-\u23EC\u23F0\u23F3"
    "\u25A0-\u25FF"          # geometric shapes
    "\uFE0E\uFE0F"          # variation selectors
    "\u200D"                # zero width joiner
    "]+",
    flags=re.UNICODE,
)


def sanitize_plain_english(text: str) -> str:
    """
    Sanitizes any agent response string into strict, professional plain English:
    1. Removes all emojis and pictograms.
    2. Strips markdown headings (#, ##, ###).
    3. Strips bold and italic asterisks (**text**, *text*).
    4. Strips code backticks (`code` -> code).
    5. Preserves legitimate punctuation, dates, times, IDs, and bulleted lists.
    6. Normalizes consecutive whitespace and empty lines.
    """
    if not text:
        return ""

    # 1. Remove emojis
    cleaned = EMOJI_PATTERN.sub("", text)

    # 2. Process line by line
    lines = cleaned.splitlines()
    processed_lines = []
    for line in lines:
        # Skip markdown table divider lines like |---|---| or | :--- | :--- |
        if re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", line):
            continue
        # Strip markdown headings at start of line (e.g. "### Title" -> "Title")
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        # Strip standalone heading markers within lines (e.g. "Text # Heading" -> "Text Heading")
        # but preserve "#123" identifiers
        line = re.sub(r"(?<=\s)#{1,6}\s+([A-Za-z])", r"\1", line)
        # Convert * bullets to -
        line = re.sub(r"^\s*\*\s+", "- ", line)
        processed_lines.append(line)
    cleaned = "\n".join(processed_lines)

    # 3. Strip bold/italic asterisks: **word** or *word*
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    # Any residual lone asterisks
    cleaned = cleaned.replace("**", "").replace("*", "")

    # 4. Strip inline backticks: `code` -> code
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = cleaned.replace("`", "")

    # 5. Clean up artificial badges or double colons
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    # 6. Normalize blank lines (max 2 consecutive newlines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()
