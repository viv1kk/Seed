"""Syntax highlighting, done here rather than in the browser.

The artifacts panel shows the pipeline modules that actually ran. Highlighting
them server side keeps a second lexer out of the frontend bundle, and it means
the markup the browser receives is the same markup a future export or print path
would use.

``nowrap=True`` emits only the highlighted spans, with no wrapper ``<div>`` and
no inline stylesheet. The spans carry Pygments' standard token classes and the
frontend supplies the container and the colours from its own tokens, so the code
block sits inside the cyanotype palette instead of importing a Pygments theme
that was designed against a different background. Those colours are part of the
design system and arrive with it in phase 4; until then the markup is correct
and unstyled.
"""

from typing import Final

from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

# Language tags seen on artifacts, mapped to the lexer names Pygments knows.
# Anything absent falls back to plain text rather than raising: an artifact that
# shows up unhighlighted is a small disappointment, and one that fails the
# request is a broken panel.
_LEXER_ALIASES: Final[dict[str, str]] = {
    "python": "python",
    "py": "python",
    "sql": "sql",
    "yaml": "yaml",
    "json": "json",
    "typescript": "typescript",
    "tsx": "tsx",
    "markdown": "markdown",
    "md": "markdown",
    "text": "text",
}

_FORMATTER: Final[HtmlFormatter[str]] = HtmlFormatter(nowrap=True)


def lexer_for(lang: str | None) -> Lexer:
    alias = _LEXER_ALIASES.get((lang or "text").lower(), lang or "text")
    try:
        return get_lexer_by_name(alias)
    except ClassNotFound:
        return get_lexer_by_name("text")


def highlight(source: str, lang: str | None) -> str:
    """Source to HTML spans. Never raises on an unknown language."""
    return pygments_highlight(source, lexer_for(lang), _FORMATTER)
