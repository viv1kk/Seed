"""The FastAPI application.

One process serves everything: the API under /api, and the built frontend from
frontend/dist as static files. That is how the demo runs and how it should be
tested, because it is the only configuration where the two halves share an
origin and there is no Vite proxy in between.

The static mount goes last, after every router. Mounting "/" earlier swallows
every /api request underneath it, and the symptom is a 404 page returned from an
endpoint that plainly exists.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.artifacts import router as artifacts_router
from app.api.examples import router as examples_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.api.runs import router as runs_router
from app.version import VERSION

# backend/app/main.py -> backend/app -> backend -> the repository root.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

NOT_BUILT = (
    "The frontend has not been built yet.\n\n"
    "Run: python tasks.py demo\n\n"
    "The API is up and serving under /api.\n"
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Seed",
        version=VERSION,
        description="A requirements document, decomposed and fulfilled by a team of agents.",
    )

    app.include_router(health_router)
    app.include_router(examples_router)
    app.include_router(plans_router)
    app.include_router(runs_router)
    app.include_router(artifacts_router)

    # Routers go above this line. The static mount goes below it and stays last.
    mount_frontend(app)
    return app


def mount_frontend(app: FastAPI) -> None:
    """Serve frontend/dist from "/", if it has been built.

    Absent, which is the case under pytest and whenever the backend runs beside
    the Vite dev server, the mount is skipped and "/" says how to build it. That
    beats refusing to start: the API is the half that is running, and every test
    in the suite exercises it without a bundle existing.
    """
    if not (DIST / "index.html").is_file():

        @app.get("/", response_class=PlainTextResponse, include_in_schema=False)
        async def frontend_missing() -> str:
            return NOT_BUILT

        return

    # html=True serves index.html for "/" and appends it to directory paths.
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")


app = create_app()
