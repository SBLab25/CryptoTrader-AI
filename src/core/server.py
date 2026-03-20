# File: src/core/server.py
"""
FastAPI Main Application
REST API + WebSocket for real-time dashboard updates
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agents.orchestrator import TradingOrchestrator
from src.core.models import TradeSignal, Trade, Portfolio
from src.risk.engine import risk_engine
from src.core.config import settings
from src.utils.logger import get_logger
from src.db.database import init_db, close_db, get_session
from src.notifications.telegram import notifier
from src.api.backtest_routes import router as backtest_router
from src.api.routes.history import router as history_router
from src.api.routes.llm_routes import router as llm_router
from src.utils.scheduler import build_scheduler

logger = get_logger(__name__)

# ---- WebSocket Connection Manager ----
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


# ---- Event Callbacks (for live broadcasting) ----
async def on_signal(signal: TradeSignal):
    await ws_manager.broadcast({
        "type": "signal",
        "data": signal.model_dump(mode="json"),
    })


async def on_trade(trade: Trade):
    await ws_manager.broadcast({
        "type": "trade",
        "data": trade.model_dump(mode="json"),
    })


async def on_portfolio_update(portfolio: Portfolio):
    await ws_manager.broadcast({
        "type": "portfolio",
        "data": portfolio.model_dump(mode="json"),
    })


# ---- App Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init database
    await init_db()

    # Register callbacks
    orchestrator.on_signal(on_signal)
    orchestrator.on_trade(on_trade)
    orchestrator.on_portfolio_update(on_portfolio_update)

    # Start trading loop in background
    task = asyncio.create_task(orchestrator.start())

    # Start daily scheduler
    scheduler = build_scheduler(
        portfolio_agent=orchestrator.portfolio_agent,
        risk_engine=risk_engine,
        notifier=notifier,
        ws_broadcast_fn=ws_manager.broadcast,
    )
    sched_task = asyncio.create_task(scheduler.start())
    logger.info("✅ Trading orchestrator started in background")

    # Notify system start
    await notifier.alert_system_start(
        settings.trading_mode,
        settings.symbol_list,
    )
    yield
    # Shutdown
    await orchestrator.stop()
    await scheduler.stop()
    task.cancel()
    sched_task.cancel()
    await close_db()
    await notifier.close()
    logger.info("🛑 Trading orchestrator stopped")


# ---- FastAPI App ----
app = FastAPI(
    title="Multi-Agent Crypto Trading System",
    description="AI-powered crypto trading with real-time analysis and risk management",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest_router)
app.include_router(history_router)
app.include_router(llm_router)


# ---- REST Endpoints ----

@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "running",
        "mode": settings.trading_mode,
        "version": "1.0.0",
    }


@app.get("/api/status", tags=["System"])
async def get_status():
    """Get current system status"""
    return orchestrator.get_status()


@app.get("/api/portfolio", tags=["Portfolio"])
async def get_portfolio():
    """Get current portfolio snapshot"""
    prices = orchestrator.market_analyst.get_current_prices()
    portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
    return portfolio.model_dump(mode="json")


@app.get("/api/performance", tags=["Portfolio"])
async def get_performance():
    """Get trading performance statistics"""
    return orchestrator.portfolio_agent.get_performance_stats()


@app.get("/api/positions", tags=["Portfolio"])
async def get_positions():
    """Get open positions"""
    prices = orchestrator.market_analyst.get_current_prices()
    portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
    return [p.model_dump(mode="json") for p in portfolio.open_positions]


@app.get("/api/risk", tags=["Risk"])
async def get_risk_status():
    """Get risk engine status"""
    return {
        "is_paused": risk_engine.is_paused,
        "max_position_size_pct": settings.max_position_size_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "max_daily_loss_pct": settings.max_daily_loss_pct,
        "max_drawdown_pct": settings.max_drawdown_pct,
        "max_open_positions": settings.max_open_positions,
    }


@app.post("/api/risk/resume", tags=["Risk"])
async def resume_trading():
    """Manually resume trading if paused"""
    risk_engine.resume_trading()
    return {"status": "resumed"}


@app.post("/api/trading/stop", tags=["System"])
async def stop_trading():
    """Stop the trading loop"""
    await orchestrator.stop()
    return {"status": "stopped"}


@app.post("/api/trading/start", tags=["System"])
async def start_trading(background_tasks: BackgroundTasks):
    """Start the trading loop if not running"""
    if not orchestrator.is_running:
        background_tasks.add_task(orchestrator.start)
        return {"status": "started"}
    return {"status": "already_running"}


@app.get("/api/market/{symbol}", tags=["Market"])
async def get_market_data(symbol: str):
    """Get cached market data for a symbol"""
    data = orchestrator.market_analyst.get_cached_market_data(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    return data.model_dump(mode="json")


@app.get("/api/config", tags=["Config"])
async def get_config():
    """Get current trading configuration (safe — no secrets)"""
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


@app.get("/api/execution/stats", tags=["System"])
async def get_execution_stats():
    """Get execution agent order statistics"""
    return orchestrator.execution_agent.stats


@app.get("/api/scheduler/status", tags=["System"])
async def get_scheduler_status():
    """Get daily scheduler task status"""
    # scheduler is module-level after lifespan init
    return {"message": "Scheduler status available after startup"}


# ---- WebSocket ----

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket feed.
    Broadcasts: signals, trades, portfolio updates
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial state
        prices = orchestrator.market_analyst.get_current_prices()
        portfolio = orchestrator.portfolio_agent.get_portfolio_snapshot(prices)
        await websocket.send_json({
            "type": "init",
            "data": {
                "status": orchestrator.get_status(),
                "portfolio": portfolio.model_dump(mode="json"),
            }
        })

        # Keep alive & handle client messages
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat", "timestamp": str(asyncio.get_event_loop().time())})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
