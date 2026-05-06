"""Shared runtime objects for Phase 3 graph execution."""

from src.agents.execution_agent import ExecutionAgent
from src.agents.market_analyst import MarketAnalystAgent
from src.agents.portfolio_agent import PortfolioAgent
from src.exchange.paper_engine import PaperTradingEngine

market_analyst = MarketAnalystAgent()
portfolio_agent = PortfolioAgent()
paper_engine = PaperTradingEngine()
execution_agent = ExecutionAgent(paper_engine)
