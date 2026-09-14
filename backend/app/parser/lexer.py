"""Markdown to a flat block stream.

``markdown-it-py`` emits an open/close token stream. Walking that directly in
``build_plan`` would mix two concerns and make the plan rules hard to read, so
this flattens it once into the five block kinds the parser rules actually talk
about, and nothing else.

The parser is real: everything in the plan is derived from these blocks. There
is no filename-keyed shortcut anywhere behind this.
"""

from dataclasses import dataclass
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    """Body text.

    ``text`` keeps its internal newlines. That matters: a task's directive lines
    arrive as one paragraph,

        Agent: ETL Engineer
        Depends on: 1.1, 1.2

    because a single newline is a soft break, not a paragraph boundary. Joining
    them would lose the second directive.
    """

    text: str


@dataclass(frozen=True)
class Bullet:
    text: str


@dataclass(frozen=True)
class Fence:
    lang: str
    code: str


@dataclass(frozen=True)
class Quote:
    text: str


Block = Heading | Paragraph | Bullet | Fence | Quote

_MD: Final[MarkdownIt] = MarkdownIt("commonmark")


def lex(markdown: str) -> list[Block]:
    tokens: list[Token] = _MD.parse(markdown)
    blocks: list[Block] = []

    # Depth counters rather than flags: a quote inside a list, or a nested list,
    # should not flip the state off on its first close token.
    quote_depth = 0
    item_depth = 0
    heading_level: int | None = None

    for token in tokens:
        match token.type:
            case "heading_open":
                heading_level = int(token.tag[1:])

            case "blockquote_open":
                quote_depth += 1
            case "blockquote_close":
                quote_depth -= 1

            case "list_item_open":
                item_depth += 1
            case "list_item_close":
                item_depth -= 1

            case "fence":
                blocks.append(Fence(lang=token.info.strip(), code=token.content))

            case "inline":
                text = token.content.strip()
                if not text:
                    continue
                if heading_level is not None:
                    blocks.append(Heading(level=heading_level, text=text))
                    heading_level = None
                elif quote_depth > 0:
                    blocks.append(Quote(text=text))
                elif item_depth > 0:
                    blocks.append(Bullet(text=text))
                else:
                    blocks.append(Paragraph(text=text))

    return blocks
