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
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from vllm.logger import logger

from vllm_ascend.edge_cloud.id_adapter import wrap_req_id
from vllm_ascend.edge_cloud.observability import format_event, log_event
from vllm_ascend.edge_cloud.prefix_protocol import (
    HEADER_EDGE_ID,
    HEADER_REQUEST_ID,
    PrefixManifest,
    UsageInfo,
)


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
        log_event(logger, "info", "cloud_control_bridge_started")

    def close(self) -> None:
        """Stop dispatch and fail HTTP requests still waiting for the core."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        error = RuntimeError("cloud control plane stopped")
        for future in [*self._probe_futures.values(), *self._usage_futures.values()]:
            if not future.done():
                future.set_exception(error)
        log_event(
            logger,
            "info",
            "cloud_control_bridge_stopped",
            pending_probes=len(self._probe_futures),
            pending_usage=len(self._usage_futures),
        )

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
        log_event(
            logger,
            "debug",
            "cloud_probe_enqueued",
            request_id=request_id,
            prompt_tokens=manifest.prompt_tokens,
            full_blocks=manifest.full_block_count,
            has_tail=manifest.tail_hash is not None,
            block_size=manifest.block_size,
        )
        try:
            return await probe_future
        except BaseException as exc:
            self._probe_futures.pop(request_id, None)
            self._usage_futures.pop(request_id, None)
            log_event(
                logger,
                "warning",
                "cloud_probe_wait_failed",
                request_id=request_id,
                error_type=type(exc).__name__,
            )
            raise

    async def wait_usage(self, request_id: str) -> UsageInfo:
        """Wait for the data-plane finish notification for a request."""
        try:
            future = self._usage_futures[request_id]
        except KeyError as exc:
            log_event(
                logger,
                "warning",
                "cloud_usage_unknown_request",
                request_id=request_id,
            )
            raise ValueError(f"unknown control request {request_id!r}") from exc
        log_event(
            logger,
            "debug",
            "cloud_usage_wait_started",
            request_id=request_id,
        )
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
                log_event(
                    logger,
                    "error",
                    "cloud_event_malformed",
                    payload_type=type(event).__name__,
                )
                continue
            assert self._loop is not None
            self._loop.call_soon_threadsafe(self._deliver_event, event)

    def _deliver_event(self, event: dict[str, Any]) -> None:
        request_id = event.get("request_id")
        event_type = event.get("type")
        if event_type == "probe":
            future = self._probe_futures.pop(request_id, None)
            if future is None or future.done():
                log_event(
                    logger,
                    "warning",
                    "cloud_probe_event_orphaned",
                    request_id=request_id,
                )
                return
            if event.get("ok"):
                future.set_result(event["result"])
                log_event(
                    logger,
                    "debug",
                    "cloud_probe_event_delivered",
                    request_id=request_id,
                )
            else:
                future.set_exception(RuntimeError(event.get("error", "probe failed")))
                log_event(
                    logger,
                    "warning",
                    "cloud_probe_event_failed",
                    request_id=request_id,
                )
        elif event_type == "usage":
            future = self._usage_futures.get(request_id)
            if future is not None and not future.done():
                future.set_result(event["usage"])
                log_event(
                    logger,
                    "debug",
                    "cloud_usage_event_delivered",
                    request_id=request_id,
                )
            else:
                log_event(
                    logger,
                    "warning",
                    "cloud_usage_event_orphaned",
                    request_id=request_id,
                )
        else:
            log_event(
                logger,
                "warning",
                "cloud_event_unknown_type",
                request_id=request_id,
                event_type=event_type,
            )


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
                log_event(
                    logger,
                    "error",
                    "cloud_command_unknown_type",
                    command_type=command.get("type"),
                )
                continue
            manifest = command.get("manifest")
            request_id = getattr(manifest, "request_id", None)
            log_event(
                logger,
                "debug",
                "cloud_probe_dequeued",
                request_id=request_id,
            )
            try:
                result = kv_manager.probe(manifest)
                event = {
                    "type": "probe",
                    "request_id": request_id,
                    "ok": True,
                    "result": result,
                }
            except Exception as exc:
                logger.exception(
                    "%s",
                    format_event(
                        "cloud_probe_processing_failed",
                        request_id=request_id,
                        error_type=type(exc).__name__,
                    ),
                )
                event = {
                    "type": "probe",
                    "request_id": request_id,
                    "ok": False,
                    "error": str(exc),
                }
            self.event_queue.put(event)

    def publish_usage(self, request_id: str, usage: UsageInfo) -> None:
        """Complete the matching OpenAI stream in the parent process."""
        log_event(
            logger,
            "debug",
            "cloud_usage_published",
            request_id=request_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=usage.cached_tokens,
        )
        self.event_queue.put({"type": "usage", "request_id": request_id, "usage": usage})


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
        request_id = request.headers.get(HEADER_REQUEST_ID)
        try:
            body = await request.json()
            manifest = PrefixManifest.from_openai_request(request.headers, body)
            # Multi-edge namespace isolation happens entirely on the cloud:
            # the edge only self-reports its edge_id header, and every
            # internal key (probe/usage futures, KV reservations) uses the
            # wrapped form. Responses strip the prefix so the edge stays
            # unaware of the cloud-side namespace.
            raw_request_id = manifest.request_id
            edge_id_header = request.headers.get(HEADER_EDGE_ID)
            if edge_id_header is not None:
                try:
                    edge_id = int(edge_id_header)
                except ValueError as exc:
                    raise ValueError(
                        f"invalid {HEADER_EDGE_ID} header {edge_id_header!r}"
                    ) from exc
                manifest = replace(
                    manifest,
                    request_id=wrap_req_id(edge_id, raw_request_id),
                )
            probe = await bridge.probe(manifest)
        except ValueError as exc:
            log_event(
                logger,
                "warning",
                "cloud_http_request_rejected",
                request_id=request_id,
                error_type=type(exc).__name__,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception(
                "%s",
                format_event(
                    "cloud_http_request_failed",
                    request_id=request_id,
                    error_type=type(exc).__name__,
                ),
            )
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        log_event(
            logger,
            "info",
            "cloud_http_probe_reserved",
            request_id=manifest.request_id,
            instance_id=probe.instance_id,
            prompt_tokens=manifest.prompt_tokens,
            hit_tokens=probe.hit_tokens,
            hit_blocks=probe.hit_blocks,
        )

        model = body.get("model", "edge-cloud-internal")

        async def events():
            try:
                yield ": edge-cloud-prefix-reserved\n\n"
                usage = await bridge.wait_usage(manifest.request_id)
                log_event(
                    logger,
                    "info",
                    "cloud_sse_usage_ready",
                    request_id=manifest.request_id,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cached_tokens=usage.cached_tokens,
                )
                chunk = {
                    "id": raw_request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [],
                    "usage": usage.to_openai_dict(),
                }
                yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                log_event(
                    logger,
                    "warning",
                    "cloud_sse_cancelled",
                    request_id=manifest.request_id,
                )
                raise
            except Exception as exc:
                logger.exception(
                    "%s",
                    format_event(
                        "cloud_sse_failed",
                        request_id=manifest.request_id,
                        error_type=type(exc).__name__,
                    ),
                )
                raise
            finally:
                log_event(
                    logger,
                    "debug",
                    "cloud_sse_closed",
                    request_id=manifest.request_id,
                )

        headers = {
            **probe.to_headers(),
            # Strip the cloud-side namespace prefix: the edge validates that
            # the returned request id matches the one it sent.
            HEADER_REQUEST_ID: raw_request_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    return app


def run_cloud_control_server(
    bridge: CloudControlBridge,
    host: str,
    port: int,
    process: Any,
) -> None:
    """Run Uvicorn until the PassiveEngineCore child exits."""
    import uvicorn

    log_event(
        logger,
        "info",
        "cloud_http_server_starting",
        host=host,
        port=port,
    )

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
        log_event(logger, "info", "cloud_http_server_stopped")
