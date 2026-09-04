"""Format conversion utilities for channel messages.

Converts markdown content from agent responses to platform-appropriate formats:
- Telegram: HTML (for parse_mode="HTML")
- Discord: Markdown with table-to-code-block conversion
"""

from __future__ import annotations

import re
from typing import Literal

# Platform type
Platform = Literal["telegram", "discord"]


def convert_markdown(text: str, platform: Platform) -> str:
    """Convert markdown text to platform-appropriate format.

    Args:
        text: Raw markdown text from agent response.
        platform: Target platform ("telegram" or "discord").

    Returns:
        Formatted text suitable for the target platform.
    """
    if platform == "telegram":
        return _markdown_to_telegram_html(text)
    elif platform == "discord":
        return _markdown_to_discord(text)
    return text


def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram HTML format.

    Telegram HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a href="...">, <blockquote>
    See: https://core.telegram.org/bots/api#html-style
    """
    if not text:
        return text

    # Use placeholders to protect HTML tags from escaping
    _placeholders: dict[str, str] = {}
    _counter = 0

    def _save_html(html: str) -> str:
        nonlocal _counter
        key = f"%%HTML_{_counter}%%"
        _counter += 1
        _placeholders[key] = html
        return key

    def _replace_pattern(pattern: str, replacement_func, flags: int = 0) -> None:
        """Replace matches with HTML, then save to placeholder."""
        nonlocal text

        def _replacer(match: re.Match) -> str:
            html = replacement_func(match)
            return _save_html(html)

        text = re.sub(pattern, _replacer, text, flags=flags)

    # Convert code blocks first (before HTML escaping)
    _replace_pattern(r'```(\w*)\n(.*?)```', lambda m: _build_code_html(m.group(1), m.group(2)), flags=re.DOTALL)

    # Convert inline code: `code` → <code>code</code>
    _replace_pattern(r'`([^`]+)`', lambda m: f'<code>{m.group(1)}</code>')

    # Convert bold: **text** or __text__ → <b>text</b>
    _replace_pattern(r'\*\*(.+?)\*\*', lambda m: f'<b>{m.group(1)}</b>')
    _replace_pattern(r'__(.+?)__', lambda m: f'<b>{m.group(1)}</b>')

    # Convert italic: *text* → <i>text</i>
    _replace_pattern(r'\*([^*]+?)\*', lambda m: f'<i>{m.group(1)}</i>')

    # Convert strikethrough: ~~text~~ → <s>text</s>
    _replace_pattern(r'~~(.+?)~~', lambda m: f'<s>{m.group(1)}</s>')

    # Convert links: [text](url) → <a href="url">text</a>
    _replace_pattern(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>')

    # Convert headers: ### text → <b>text</b>
    _replace_pattern(r'^#{1,3}\s+(.+)$', lambda m: f'<b>{m.group(1)}</b>', flags=re.MULTILINE)

    # Convert blockquotes and tables before escaping
    text = _process_blockquotes(text)
    text = _process_tables(text)

    # Split by HTML tags to escape only text content
    parts = re.split(r'(<[^>]+>)', text)
    escaped_parts: list[str] = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            # This is an HTML tag - keep as-is
            escaped_parts.append(part)
        else:
            # This is text content - escape it
            escaped_parts.append(_escape_html(part))
    text = ''.join(escaped_parts)

    # Restore all HTML placeholders
    for key, html in _placeholders.items():
        text = text.replace(key, html)

    # Convert horizontal rules: --- →─────────
    text = re.sub(r'^-{3,}\s*$', '───────────────', text, flags=re.MULTILINE)

    return text


def _process_blockquotes(text: str) -> str:
    """Convert markdown blockquotes to <blockquote> HTML."""
    lines = text.split('\n')
    result: list[str] = []
    quote_lines: list[str] = []

    for line in lines:
        if line.strip().startswith('> '):
            quote_lines.append(line.strip()[2:])
        else:
            if quote_lines:
                quote_text = '\n'.join(quote_lines)
                result.append(f'<blockquote>{quote_text}</blockquote>')
                quote_lines = []
            result.append(line)

    if quote_lines:
        quote_text = '\n'.join(quote_lines)
        result.append(f'<blockquote>{quote_text}</blockquote>')

    return '\n'.join(result)


def _process_tables(text: str) -> str:
    """Convert markdown tables to formatted text with bold headers."""
    lines = text.split('\n')
    result: list[str] = []
    in_table = False
    table_lines: list[str] = []

    for line in lines:
        if '|' in line and _is_table_row(line):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
        else:
            if in_table:
                result.extend(_format_table_as_text(table_lines))
                in_table = False
                table_lines = []
            result.append(line)

    if in_table:
        result.extend(_format_table_as_text(table_lines))

    return '\n'.join(result)


def _build_code_html(lang: str, code: str) -> str:
    """Build HTML for a code block."""
    if lang:
        return f'<pre><code class="language-{lang}">{code}</code></pre>'
    return f'<pre>{code}</pre>'


def _markdown_to_discord(text: str) -> str:
    """Convert markdown for Discord.

    Discord supports most markdown natively but NOT tables.
    Convert tables to code blocks for readability.
    """
    if not text:
        return text

    # Convert tables to code blocks (Discord doesn't render tables)
    text = _convert_table_to_code_block(text)

    return text


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    # Don't escape quotes in text content (only needed in attributes)
    return text




def _convert_blockquotes_html(text: str) -> str:
    """Convert markdown blockquotes to Telegram HTML."""
    lines = text.split('\n')
    result: list[str] = []
    in_quote = False
    quote_lines: list[str] = []

    for line in lines:
        if line.startswith('> '):
            if not in_quote:
                in_quote = True
                quote_lines = []
            quote_lines.append(line[2:])
        else:
            if in_quote:
                quote_text = '\n'.join(quote_lines)
                result.append(f'<blockquote>{quote_text}</blockquote>')
                in_quote = False
                quote_lines = []
            result.append(line)

    if in_quote:
        quote_text = '\n'.join(quote_lines)
        result.append(f'<blockquote>{quote_text}</blockquote>')

    return '\n'.join(result)


def _convert_table_to_text(text: str) -> str:
    """Convert markdown tables to formatted text for Telegram.

    Tables don't render in Telegram, so convert to a readable text format.
    """
    lines = text.split('\n')
    result: list[str] = []
    in_table = False
    table_lines: list[str] = []

    for line in lines:
        if '|' in line and _is_table_row(line):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
        else:
            if in_table:
                result.extend(_format_table_as_text(table_lines))
                in_table = False
                table_lines = []
            result.append(line)

    if in_table:
        result.extend(_format_table_as_text(table_lines))

    return '\n'.join(result)


def _is_table_row(line: str) -> bool:
    """Check if a line is part of a markdown table."""
    stripped = line.strip()
    if not stripped.startswith('|'):
        return False
    # Check if it's a separator line (|---|---|)
    if re.match(r'^\|[\s\-:|]+\|$', stripped):
        return True
    # Check if it has multiple columns
    return stripped.count('|') >= 2


def _format_table_as_text(table_lines: list[str]) -> list[str]:
    """Convert table lines to formatted text with bold headers (HTML)."""
    if len(table_lines) < 2:
        return table_lines

    # Parse header and rows (skip separator line)
    header = _parse_table_row(table_lines[0])
    rows = [_parse_table_row(line) for line in table_lines[2:] if _parse_table_row(line)]

    if not header:
        return table_lines

    result = []
    for i, row in enumerate(rows):
        if i == 0:
            result.append('📊 ')
        else:
            result.append('   ')
        for j, cell in enumerate(row):
            if j < len(header):
                # Use <b> for bold (Telegram HTML)
                result.append(f'<b>{header[j]}</b>: {cell}  ')
        result.append('')

    return result


def _parse_table_row(line: str) -> list[str]:
    """Parse a table row into cells."""
    stripped = line.strip().strip('|')
    return [cell.strip() for cell in stripped.split('|') if cell.strip()]


def _convert_table_to_code_block(text: str) -> str:
    """Convert markdown tables to code blocks for Discord."""
    lines = text.split('\n')
    result: list[str] = []
    in_table = False
    table_lines: list[str] = []

    for line in lines:
        if '|' in line and _is_table_row(line):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
        else:
            if in_table:
                result.append('```')
                result.extend(table_lines)
                result.append('```')
                in_table = False
                table_lines = []
            result.append(line)

    if in_table:
        result.append('```')
        result.extend(table_lines)
        result.append('```')

    return '\n'.join(result)
