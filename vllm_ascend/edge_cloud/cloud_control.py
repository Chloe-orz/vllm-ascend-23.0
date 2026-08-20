# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""HTTP and IPC bridge for the cloud prefix-cache control plane."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from vllm.logger import init_logger

from vllm_ascend.edge_cloud.prefix_protocol import PrefixManifest, UsageInfo

logger = init_logger(__name__)


class CloudControlBridge:
    """Route multiprocessing responses to the matching HTTP coroutine."""

    def __init__(self, command_queue: Any, event_queue: Any) -> None:
        self.command_queue = command_queue
        self.event_queue = event_queue
        self._loop: asyncio.AbstractEventLoop | None = None
        self._probe_futures: dict[str, asyncio.Future[Any]] = {}
        self._usage_futures: dict[str, asyncio.Future[UsageInfo]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the single event dispatcher on the server event loop."""
        if self._thread is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(
            target=self._dispatch_events,
            daemon=True,
            name="edge-cloud-control-events",
        )
        self._thread.start()

    def close(self) -> None:
        """Stop dispatch and fail HTTP requests still waiting for the core."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        error = RuntimeError("cloud control plane stopped")
        for future in [*self._probe_futures.values(), *self._usage_futures.values()]:
            if not future.done():
                future.set_exception(error)

    async def probe(self, manifest: PrefixManifest):
        """Ask PassiveEngineCore to find and pin a prefix."""
        if self._loop is None:
            raise RuntimeError("cloud control bridge has not started")
        request_id = manifest.request_id
        if request_id in self._probe_futures or request_id in self._usage_futures:
            raise ValueError(f"duplicate control request {request_id!r}")
        probe_future = self._loop.create_future()
        usage_future = self._loop.create_future()
        self._probe_futures[request_id] = probe_future
        self._usage_futures[request_id] = usage_future
        self.command_queue.put({"type": "probe", "manifest": manifest})
        try:
            return await probe_future
        except BaseException:
            self._probe_futures.pop(request_id, None)
            self._usage_futures.pop(request_id, None)
            raise

    async def wait_usage(self, request_id: str) -> UsageInfo:
        """Wait for the data-plane finish notification for a request."""
        try:
            future = self._usage_futures[request_id]
        except KeyError as exc:
            raise ValueError(f"unknown control request {request_id!r}") from exc
        try:
            return await asyncio.shield(future)
        finally:
            if future.done():
                self._usage_futures.pop(request_id, None)

    def _dispatch_events(self) -> None:
        while not self._stop.is_set():
            try:
                event = self.event_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if not isinstance(event, dict):
                logger.error("Ignoring malformed cloud control event: %r", event)
                continue
            assert self._loop is not None
            self._loop.call_soon_threadsafe(self._deliver_event, event)

    def _deliver_event(self, event: dict[str, Any]) -> None:
        request_id = event.get("request_id")
        event_type = event.get("type")
        if event_type == "probe":
            future = self._probe_futures.pop(request_id, None)
            if future is None or future.done():
                return
            if event.get("ok"):
                future.set_result(event["result"])
            else:
                future.set_exception(RuntimeError(event.get("error", "probe failed")))
        elif event_type == "usage":
            future = self._usage_futures.get(request_id)
            if future is not None and not future.done():
                future.set_result(event["usage"])


class CloudControlProcessor:
    """Execute parent HTTP commands in the KV-owning EngineCore process."""

    def __init__(self, command_queue: Any, event_queue: Any) -> None:
        self.command_queue = command_queue
        self.event_queue = event_queue

    def poll(self, kv_manager: Any) -> None:
        """Drain all currently queued commands without blocking scheduling."""
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                return
            if command.get("type") != "probe":
                logger.error("Ignoring unknown cloud control command: %r", command)
                continue
            manifest = command.get("manifest")
            request_id = getattr(manifest, "request_id", None)
            try:
                result = kv_manager.probe(manifest)
                event = {
                    "type": "probe",
                    "request_id": request_id,
                    "ok": True,
                    "result": result,
                }
            except Exception as exc:
                logger.exception("Cloud prefix probe failed for %s", request_id)
                event = {
                    "type": "probe",
                    "request_id": request_id,
                    "ok": False,
                    "error": str(exc),
                }
            self.event_queue.put(event)

    def publish_usage(self, request_id: str, usage: UsageInfo) -> None:
        """Complete the matching OpenAI stream in the parent process."""
        self.event_queue.put(
            {"type": "usage", "request_id": request_id, "usage": usage}
        )


def create_cloud_control_app(bridge: CloudControlBridge) -> FastAPI:
    """Create the minimal OpenAI-compatible cloud control endpoint."""
    app = FastAPI(title="vLLM Ascend edge-cloud control plane")

    @app.on_event("startup")
    async def start_bridge() -> None:
        bridge.start()

    @app.on_event("shutdown")
    async def stop_bridge() -> None:
        bridge.close()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        try:
            body = await request.json()
            manifest = PrefixManifest.from_openai_request(request.headers, body)
            probe = await bridge.probe(manifest)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        model = body.get("model", "edge-cloud-internal")

        async def events():
            yield ": edge-cloud-prefix-reserved\n\n"
            usage = await bridge.wait_usage(manifest.request_id)
            chunk = {
                "id": manifest.request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [],
                "usage": usage.to_openai_dict(),
            }
            yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
            yield "data: [DONE]\n\n"

        headers = {
            **probe.to_headers(),
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(
            events(), media_type="text/event-stream", headers=headers
        )

    return app


def run_cloud_control_server(
    bridge: CloudControlBridge,
    host: str,
    port: int,
    process: Any,
) -> None:
    """Run Uvicorn until the PassiveEngineCore child exits."""
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            create_cloud_control_app(bridge),
            host=host,
            port=port,
            log_level="info",
        )
    )

    def watch_process() -> None:
        process.join()
        server.should_exit = True

    watcher = threading.Thread(
        target=watch_process,
        daemon=True,
        name="edge-cloud-passive-core-watch",
    )
    watcher.start()
    try:
        server.run()
    finally:
        server.should_exit = True
        with suppress(RuntimeError):
            watcher.join(timeout=1.0)
