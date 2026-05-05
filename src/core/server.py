"""FastAPI application with Phase 1 auth and protected API routes."""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Set

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from src.agents.orchestrator import TradingOrchestrator
from src.api.auth import auth_router, get_current_user
from src.api.backtest_routes import router as backtest_router
from src.api.middleware.cors import register_cors
from src.api.middleware.rate_limiter import register_rate_limiter
from src.api.routes.history import router as history_router
from src.api.routes.llm_routes import router as llm_router
from src.core.config import settings
from src.core.models import Portfolio, Trade, TradeSignal
from src.db.database import close_db, init_db
from src.notifications.telegram import notifier
from src.risk.engine import risk_engine
from src.utils.logger import get_logger
from src.utils.scheduler import build_scheduler

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.add(ws)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, ws: WebSocket):
        self.active_connections.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active_connections.discard(ws)


ws_manager = ConnectionManager()
orchestrator = TradingOrchestrator()
scheduler = None
protected_api = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


async def on_signal(signal: TradeSignal):
    await ws_manager.broadcast({"type": "signal", "data": signal.model_dump(mode="json")})


async def on_trade(trade: Trade):
    await ws_manager.broadcast({"type": "trade", "data": trade.model_dump(mode="json")})


async def on_portfolio_update(portfolio: Portfolio):
    await ws_manager.broadcast({"type": "portfolio", "data": portfolio.model_dump(mode="json")})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    task = None
    sched_task = None

    if app.state.start_background:
        orchestrator.on_signal(on_signal)
        orchestrator.on_trade(on_trade)
        orchestrator.on_portfolio_update(on_portfolio_update)

        task = asyncio.create_task(orchestrator.start())

        global scheduler
        scheduler = build_scheduler(
            portfolio_agent=orchestrator.portfolio_agent,
            risk_engine=risk_engine,
            notifier=notifier,
            ws_broadcast_fn=ws_manager.broadcast,
        )
        sched_task = asyncio.create_task(scheduler.start())
        logger.info("Trading orchestrator started in background")

        await notifier.alert_system_start(settings.trading_mode, settings.symbol_list)

    yield

    if app.state.start_background:
        await orchestrator.stop()
        if scheduler is not None:
            await scheduler.stop()
        if task is not None:
            task.cancel()
        if sched_task is not None:
            sched_task.cancel()

    await close_db()
    await notifier.close()
    logger.info("Trading orchestrator stopped")


@protected_api.get("/status", tags=["System"])
async def get_status():
    return orchestrator.get_status()


@protected_api.get("/portfolio", tags=["Portfolio"])
async def get_portfolio():
    prices = orchestrator.market_analyst.get_current_prices()
    portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
    return portfolio.model_dump(mode="json")


@protected_api.get("/performance", tags=["Portfolio"])
async def get_performance():
    return orchestrator.portfolio_agent.get_performance_stats()


@protected_api.get("/positions", tags=["Portfolio"])
async def get_positions():
    prices = orchestrator.market_analyst.get_current_prices()
    portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
    return [position.model_dump(mode="json") for position in portfolio.open_positions]


@protected_api.get("/risk", tags=["Risk"])
async def get_risk_status():
    return {
        "is_paused": risk_engine.is_paused,
        "max_position_size_pct": settings.max_position_size_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "max_daily_loss_pct": settings.max_daily_loss_pct,
        "max_drawdown_pct": settings.max_drawdown_pct,
        "max_open_positions": settings.max_open_positions,
    }


@protected_api.post("/risk/resume", tags=["Risk"])
async def resume_trading():
    risk_engine.resume_trading()
    return {"status": "resumed"}


@protected_api.post("/trading/stop", tags=["System"])
async def stop_trading():
    await orchestrator.stop()
    return {"status": "stopped"}


@protected_api.post("/trading/start", tags=["System"])
async def start_trading(background_tasks: BackgroundTasks):
    if not orchestrator.is_running:
        background_tasks.add_task(orchestrator.start)
        return {"status": "started"}
    return {"status": "already_running"}


@protected_api.get("/market/{symbol}", tags=["Market"])
async def get_market_data(symbol: str):
    data = orchestrator.market_analyst.get_cached_market_data(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    return data.model_dump(mode="json")


@protected_api.get("/config", tags=["Config"])
async def get_config():
    return {
        "trading_mode": settings.trading_mode,
        "symbols": settings.symbol_list,
        "scan_interval_seconds": settings.scan_interval_seconds,
        "max_position_size_pct": settings.max_position_size_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "max_open_positions": settings.max_open_positions,
        "initial_capital": settings.initial_capital,
        "base_currency": settings.base_currency,
    }


@protected_api.get("/execution/stats", tags=["System"])
async def get_execution_stats():
    return orchestrator.execution_agent.stats


@protected_api.get("/scheduler/status", tags=["System"])
async def get_scheduler_status():
    return {"message": "Scheduler status available after startup"}


def create_app(start_background: bool = True) -> FastAPI:
    app = FastAPI(
        title="Multi-Agent Crypto Trading System",
        description="AI-powered crypto trading with real-time analysis and risk management",
        version="1.1.0",
        lifespan=lifespan,
    )
    app.state.start_background = start_background

    register_cors(app)
    register_rate_limiter(app)

    app.include_router(auth_router)
    app.include_router(protected_api)
    app.include_router(backtest_router, dependencies=[Depends(get_current_user)])
    app.include_router(history_router, dependencies=[Depends(get_current_user)])
    app.include_router(llm_router, dependencies=[Depends(get_current_user)])

    @app.get("/", tags=["Health"])
    async def root():
        return {"status": "running", "mode": settings.trading_mode, "version": "1.1.0"}

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "mode": settings.trading_mode, "version": "1.1.0"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            prices = orchestrator.market_analyst.get_current_prices()
            portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
            await websocket.send_json(
                {
                    "type": "init",
                    "data": {
                        "status": orchestrator.get_status(),
                        "portfolio": portfolio.model_dump(mode="json"),
                    },
                }
            )

            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    data = json.loads(msg)
                    if data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    await websocket.send_json(
                        {"type": "heartbeat", "timestamp": str(asyncio.get_event_loop().time())}
                    )
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
            logger.info("WebSocket client disconnected")
        except Exception as exc:
            logger.error(f"WebSocket error: {exc}")
            ws_manager.disconnect(websocket)

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception on {request.url}: {type(exc).__name__}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
