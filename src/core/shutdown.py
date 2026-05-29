"""Graceful shutdown orchestration."""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass

from src.utils.logger import get_logger

log = get_logger(__name__)

SHUTDOWN_TIMEOUT_SECONDS = 30


@dataclass
class SimpleAuditEvent:
    event_type: str
    metadata: dict


class ShutdownHandler:
    def __init__(self, redis_consumer=None, graph_task=None, approval_queue=None, audit=None, broadcaster=None) -> None:
        self._consumer = redis_consumer
        self._graph_task = graph_task
        self._approvals = approval_queue
        self._audit = audit
        self._broadcaster = broadcaster
        self._shutdown_event = asyncio.Event()
        self._started_at = time.time()

    def register_signals(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._on_signal(s)))
                except NotImplementedError:
                    continue
            log.info("shutdown_signals_registered")
        except RuntimeError:
            pass

    async def _on_signal(self, sig: signal.Signals) -> None:
        log.warning("shutdown_signal_received", signal=sig.name)
        self._shutdown_event.set()
        await self.shutdown()

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_event.is_set()

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        await self._step_stop_consumer()
        await self._step_drain_graph()
        await self._step_cancel_approvals()
        await self._step_notify_clients()
        await self._step_audit_shutdown()
        log.warning("shutdown_sequence_complete")

    async def _step_stop_consumer(self) -> None:
        if self._consumer is None:
            return
        try:
            if hasattr(self._consumer, "stop"):
                await self._consumer.stop()
            elif hasattr(self._consumer, "close"):
                await self._consumer.close()
        except Exception as exc:
            log.warning("shutdown_consumer_stop_failed", error=str(exc))

    async def _step_drain_graph(self) -> None:
        if self._graph_task is None or self._graph_task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._graph_task), timeout=SHUTDOWN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self._graph_task.cancel()
            try:
                await self._graph_task
            except Exception:
                pass
        except Exception as exc:
            log.warning("shutdown_graph_task_failed", error=str(exc))

    async def _step_cancel_approvals(self) -> None:
        if self._approvals is None:
            return
        try:
            if hasattr(self._approvals, "expire_all_pending"):
                await self._approvals.expire_all_pending(reason="system_shutdown")
        except Exception as exc:
            log.warning("shutdown_approvals_cancel_failed", error=str(exc))

    async def _step_notify_clients(self) -> None:
        if self._broadcaster is None:
            return
        try:
            await self._broadcaster.emit("system", {"type": "shutdown", "message": "Server shutting down"})
        except Exception as exc:
            log.warning("shutdown_broadcast_failed", error=str(exc))

    async def _step_audit_shutdown(self) -> None:
        if self._audit is None:
            return
        try:
            event = SimpleAuditEvent(
                event_type="SYSTEM_SHUTDOWN",
                metadata={"uptime_seconds": round(time.time() - self._started_at)},
            )
            await self._audit.log(event)
        except AttributeError:
            try:
                result = self._audit(
                    event_type="SYSTEM_SHUTDOWN",
                    entity_id="system",
                    entity_type="System",
                    actor="system",
                    details={"uptime_seconds": round(time.time() - self._started_at)},
                )
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                log.warning("shutdown_audit_failed", error=str(exc))
        except Exception as exc:
            log.warning("shutdown_audit_failed", error=str(exc))
