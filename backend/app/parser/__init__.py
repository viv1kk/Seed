"""The requirement document parser.

The plan is derived entirely from the markdown. Editing a heading changes the
graph, because nothing else feeds it.
"""

from app.parser.build_plan import build_plan

__all__ = ["build_plan"]
