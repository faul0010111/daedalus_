"""Research console API.

The API observes and steers the *substrate* (run, pause, speed, reset). It never
reaches into cognition: there is no endpoint to make the agent do a thing.
"""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..core.runtime import Daedalus, DaedalusConfig
from ..experiments.simulations.labyrinth import Labyrinth, LabyrinthConfig
from ..observability.timelines import cognitive_timeline

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


class SpeedRequest(BaseModel):
    ticks_per_second: float = 4.0


class RunRequest(BaseModel):
    ticks: int = 1


class ResetRequest(BaseModel):
    preset: str = "full"
    seed: int = 7
    size: int = 6


class Session:
    """Owns the agent and the background clock. One agent per server process."""

    def __init__(self, agent: Daedalus) -> None:
        self.agent = agent
        self.running = False
        self.tps = 4.0
        self.lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.error: str | None = None

    def start_clock(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            if not self.running:
                await asyncio.sleep(0.05)
                continue
            try:
                async with self.lock:
                    await self.agent.tick()
            except Exception as exc:  # a crashed runtime must be visible, not silent
                self.error = f"{type(exc).__name__}: {exc}"
                self.running = False
            await asyncio.sleep(max(0.0, 1.0 / max(self.tps, 0.1)))

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


def create_app(agent: Daedalus | None = None) -> FastAPI:
    app = FastAPI(title="DAEDALUS", version="0.1.0",
                  description="Agent intelligence research console API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    session = Session(agent or Daedalus(Labyrinth(LabyrinthConfig(seed=7)), DaedalusConfig()))
    app.state.session = session

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await session.stop()

    # ------------------------------------------------------------------ state
    @app.get("/api/state")
    async def get_state() -> Any:
        async with session.lock:
            return session.agent.state() | {"running": session.running, "tps": session.tps,
                                            "error": session.error}

    @app.get("/api/summary")
    async def get_summary() -> Any:
        a = session.agent
        return {"tick": a.clock.tick, "running": session.running, "tps": session.tps,
                "preset": a.config.run_id, "task": a.env.task_metrics(),
                "metrics": a.ctx.metrics.autonomy(a.clock.tick, a.ctx.world.cumulative_uncertainty_reduction),
                "focal": a.attention.focal_key, "error": session.error}

    @app.get("/api/events")
    async def get_events(limit: int = 200, quiet: bool = False) -> Any:
        return cognitive_timeline(session.agent.bus, limit, include_quiet=quiet)

    @app.get("/api/goals/{goal_id}")
    async def get_goal(goal_id: str) -> Any:
        ctx = session.agent.ctx
        goal = ctx.goals.goals.get(goal_id)
        if goal is None:
            return JSONResponse({"error": "unknown goal"}, status_code=404)
        return {"goal": goal.to_dict(),
                "parents": [g.to_dict() for g in ctx.goals.parents(goal_id)],
                "children": [g.to_dict() for g in ctx.goals.children(goal_id)],
                "value": round(ctx.goals.value(goal_id), 3),
                "team": [u.describe() for u in ctx.agents.team_for(goal_id)]}

    @app.get("/api/beliefs")
    async def get_beliefs(subject: str | None = None, predicate: str | None = None,
                          limit: int = 300) -> Any:
        beliefs = session.agent.ctx.world.query(subject, predicate, None)
        beliefs.sort(key=lambda b: b.updated_tick, reverse=True)
        return [b.to_dict() for b in beliefs[:limit]]

    @app.get("/api/memory/recall")
    async def recall(q: str, k: int = 6) -> Any:
        hits = session.agent.ctx.memory.episodic.recall(q, k)
        return [{"score": round(score, 3), **ep.to_dict()} for ep, score in hits]

    # ---------------------------------------------------------------- control
    @app.post("/api/control/play")
    async def play() -> Any:
        session.error = None
        session.running = True
        session.start_clock()
        return {"running": True}

    @app.post("/api/control/pause")
    async def pause() -> Any:
        session.running = False
        return {"running": False}

    @app.post("/api/control/step")
    async def step(req: RunRequest) -> Any:
        async with session.lock:
            for _ in range(max(1, min(req.ticks, 500))):
                await session.agent.tick()
        return {"tick": session.agent.clock.tick}

    @app.post("/api/control/speed")
    async def speed(req: SpeedRequest) -> Any:
        session.tps = max(0.25, min(req.ticks_per_second, 200.0))
        return {"tps": session.tps}

    @app.post("/api/control/reset")
    async def reset(req: ResetRequest) -> Any:
        async with session.lock:
            session.running = False
            env = Labyrinth(LabyrinthConfig(seed=req.seed, width=req.size, height=req.size))
            session.agent = Daedalus(env, DaedalusConfig.preset(req.preset, req.seed))
            session.error = None
        return {"tick": 0, "preset": req.preset, "seed": req.seed}

    @app.post("/api/control/snapshot")
    async def snapshot() -> Any:
        async with session.lock:
            session.agent.save()
            return {"saved": session.agent.store is not None, "tick": session.agent.clock.tick}

    # -------------------------------------------------------------- streaming
    @app.websocket("/ws/events")
    async def ws_events(socket: WebSocket) -> None:
        await socket.accept()
        queue = session.agent.bus.attach_queue()
        agent = session.agent
        try:
            await socket.send_json({"type": "hello", "tick": agent.clock.tick})
            while True:
                event = await queue.get()
                await socket.send_json(event.to_dict())
        except WebSocketDisconnect:
            pass
        finally:
            agent.bus.detach_queue(queue)

    # ------------------------------------------------------------- static UI
    @app.get("/")
    async def index() -> Any:
        page = FRONTEND / "index.html"
        if page.exists():
            return FileResponse(page)
        return JSONResponse({"daedalus": "console not built", "api": "/api/state"})

    for name in ("console.js", "styles.css"):
        def make(fname: str):
            async def serve_asset() -> Any:
                path = FRONTEND / fname
                if path.exists():
                    return FileResponse(path)
                return JSONResponse({"error": "not found"}, status_code=404)
            return serve_asset
        app.get(f"/{name}")(make(name))

    return app


app = create_app()
