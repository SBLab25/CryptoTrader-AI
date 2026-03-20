#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# start.sh — Launch the crypto trading agent locally
# ─────────────────────────────────────────────────────
set -e

RESET='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'

echo -e "${BLUE}"
echo "  ██████╗ ██████╗ ██╗   ██╗██████╗ ████████╗ ██████╗"
echo " ██╔════╝ ██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝██╔═══██╗"
echo " ██║      ██████╔╝ ╚████╔╝ ██████╔╝   ██║   ██║   ██║"
echo " ██║      ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   ██║   ██║"
echo " ╚██████╗ ██║  ██║   ██║   ██║        ██║   ╚██████╔╝"
echo "  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝    ╚═════╝"
echo "  Multi-Agent Crypto Trading System"
echo -e "${RESET}"

# Check .env
if [ ! -f ".env" ]; then
  echo -e "${YELLOW}⚠️  .env not found. Copying from .env.example...${RESET}"
  cp .env.example .env
  echo -e "${RED}❗ Please edit .env and add your API keys, then run this script again.${RESET}"
  exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
  echo -e "${RED}❌ Python 3 not found. Install Python 3.12+${RESET}"
  exit 1
fi

# Create virtualenv if needed
if [ ! -d "venv" ]; then
  echo -e "${GREEN}📦 Creating virtual environment...${RESET}"
  python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo -e "${GREEN}📦 Installing dependencies...${RESET}"
pip install -q -r requirements.txt

# Run tests
echo -e "${GREEN}🧪 Running unit tests...${RESET}"
python -m pytest tests/unit -q --tb=short 2>&1 | tail -20 || echo -e "${YELLOW}⚠️  Some tests failed — check above${RESET}"

# Start backend
echo -e "${GREEN}🚀 Starting trading backend on http://localhost:8000${RESET}"
echo -e "${GREEN}📊 Dashboard: open frontend/index.html in your browser${RESET}"
echo -e "${YELLOW}📄 Mode: PAPER TRADING (safe simulation)${RESET}"
echo ""
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
