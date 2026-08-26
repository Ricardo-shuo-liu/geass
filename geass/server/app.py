"""FastAPI 应用组装。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import api, ws
from .state import AppState

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def create_app(state: AppState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        streamer_task = asyncio.create_task(state.streamer.run())
        evolution_task = (
            asyncio.create_task(state.evolution.run())
            if state.evolution is not None
            else None
        )
        scheduler_task = (
            asyncio.create_task(state.scheduler.run())
            if state.scheduler is not None
            else None
        )
        try:
            yield
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except asyncio.CancelledError:
                    pass
            if evolution_task is not None:
                evolution_task.cancel()
                try:
                    await evolution_task
                except asyncio.CancelledError:
                    pass
            streamer_task.cancel()
            try:
                await streamer_task
            except asyncio.CancelledError:
                pass
            try:
                state.terminal_manager.close_all()
            except Exception:
                pass

    app = FastAPI(title="Geass", version="0.1.0", lifespan=lifespan)
    app.state.geass = state

    api.register(app)
    ws.register(app)

    if DIST_DIR.is_dir():
        assets = DIST_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        dist_root = DIST_DIR.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            candidate = (DIST_DIR / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and candidate.is_relative_to(dist_root)
            ):
                return FileResponse(candidate)
            return FileResponse(DIST_DIR / "index.html")

    return app
