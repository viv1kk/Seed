"""The FastAPI application.

The static mount that serves the built frontend is
deliberately absent: when it arrives it goes at the very bottom of
``create_app``, after every router, because mounting "/" earlier swallows
every /api request underneath it.
"""

from fastapi import FastAPI

from app.api.examples import router as examples_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.version import VERSION


def create_app() -> FastAPI:
    app = FastAPI(
        title="Seed",
        version=VERSION,
        description="A requirements document, decomposed and fulfilled by a team of agents.",
    )

    app.include_router(health_router)
    app.include_router(examples_router)
    app.include_router(plans_router)

    # Routers go above this line.
    #
    # The static files mount for frontend/dist goes below it, from phase 2, and
    # must stay last. See docs/02-ARCHITECTURE.md.

    return app


app = create_app()
