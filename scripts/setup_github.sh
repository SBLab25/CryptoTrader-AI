#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  setup_github.sh
#  One-command GitHub repository initialisation and push.
#
#  Usage:
#    chmod +x scripts/setup_github.sh
#    ./scripts/setup_github.sh
#
#  What it does:
#    1. Initialises a local git repo (if not already one)
#    2. Stages all project files
#    3. Makes the initial commit
#    4. Guides you to create the GitHub repo
#    5. Pushes to origin/main
# ─────────────────────────────────────────────────────────────
set -e

RESET='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'

echo -e "${BLUE}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║      CryptoTrader AI — GitHub Setup          ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Check git is installed ────────────────────────────────────
if ! command -v git &>/dev/null; then
  echo -e "${RED}❌ git is not installed. Install it first.${RESET}"
  exit 1
fi

# ── Confirm .env is NOT committed ────────────────────────────
if [ -f ".env" ]; then
  if ! grep -q "^\.env$" .gitignore 2>/dev/null; then
    echo -e "${RED}❌ .env is not in .gitignore — STOP. This would expose API keys.${RESET}"
    exit 1
  fi
  echo -e "${GREEN}✅ .env is protected by .gitignore${RESET}"
fi

# ── Init repo if needed ───────────────────────────────────────
if [ ! -d ".git" ]; then
  git init
  echo -e "${GREEN}✅ Initialised new git repository${RESET}"
else
  echo -e "${GREEN}✅ Git repository already initialised${RESET}"
fi

# ── Set default branch to main ────────────────────────────────
git checkout -b main 2>/dev/null || git checkout main 2>/dev/null || true
git branch -M main

# ── Configure git identity if not set ────────────────────────
if [ -z "$(git config user.email)" ]; then
  echo ""
  echo -e "${YELLOW}Git identity not configured. Enter your details:${RESET}"
  read -p "  Name:  " GIT_NAME
  read -p "  Email: " GIT_EMAIL
  git config user.name  "$GIT_NAME"
  git config user.email "$GIT_EMAIL"
fi

# ── Stage all files ───────────────────────────────────────────
echo ""
echo -e "${BLUE}Staging all project files...${RESET}"
git add .

# Show what's being committed
echo ""
echo -e "${BLUE}Files to be committed:${RESET}"
git status --short | head -60

# ── Initial commit ────────────────────────────────────────────
echo ""
COMMIT_MSG="feat: initial commit — CryptoTrader AI multi-agent trading system

- 5 specialized AI agents (Orchestrator, Market Analyst, Signal, Execution, Portfolio)
- Claude AI-powered signal generation with TA indicators (RSI, MACD, BB, EMA, ATR)
- 3 trading strategies: Momentum, Mean Reversion, Breakout + Auto-select
- 8-layer risk engine with stop-loss, take-profit, drawdown protection
- Paper trading mode (default ON) for safe testing
- Full backtesting engine with Sharpe ratio, profit factor, equity curve
- Real-time WebSocket dashboard with 6 tabs
- Telegram trade notifications
- SQLAlchemy async DB with Alembic migrations
- CCXT adapter for 100+ exchanges
- 35+ unit and integration tests
- Docker Compose deployment
- CLI management tool"

git commit -m "$COMMIT_MSG"
echo -e "${GREEN}✅ Initial commit created${RESET}"

# ── GitHub repo creation instructions ────────────────────────
echo ""
echo -e "${YELLOW}${BOLD}══════════════════════════════════════════════${RESET}"
echo -e "${YELLOW}${BOLD}  Next: Create your GitHub repository${RESET}"
echo -e "${YELLOW}${BOLD}══════════════════════════════════════════════${RESET}"
echo ""
echo -e "  1. Go to ${BLUE}https://github.com/new${RESET}"
echo -e "  2. Repository name: ${BOLD}cryptotrader-ai${RESET}"
echo -e "  3. Description: ${BOLD}Multi-agent AI crypto trading system powered by Claude${RESET}"
echo -e "  4. Set to ${BOLD}Public${RESET} or ${BOLD}Private${RESET} (your choice)"
echo -e "  5. ${RED}Do NOT initialise with README, .gitignore, or licence${RESET}"
echo -e "     (we already have these)"
echo -e "  6. Click ${BOLD}Create repository${RESET}"
echo ""
echo -e "${YELLOW}Then come back here and enter your repository URL.${RESET}"
echo ""

# ── Get repo URL from user ────────────────────────────────────
read -p "  Paste your GitHub repo URL (e.g. https://github.com/username/cryptotrader-ai): " REPO_URL

if [ -z "$REPO_URL" ]; then
  echo ""
  echo -e "${YELLOW}No URL entered. Run these commands manually when ready:${RESET}"
  echo ""
  echo "  git remote add origin https://github.com/YOUR_USERNAME/cryptotrader-ai.git"
  echo "  git push -u origin main"
  echo ""
  exit 0
fi

# ── Add remote and push ───────────────────────────────────────
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"

echo ""
echo -e "${BLUE}Pushing to GitHub...${RESET}"
git push -u origin main

echo ""
echo -e "${GREEN}${BOLD}✅ Successfully pushed to GitHub!${RESET}"
echo ""
echo -e "  Your repo: ${BLUE}${BOLD}$REPO_URL${RESET}"
echo ""
echo -e "${YELLOW}${BOLD}Recommended next steps:${RESET}"
echo "  1. Add topics to your repo: crypto, trading, ai, python, fastapi, anthropic"
echo "  2. Star the repo to help others find it ⭐"
echo "  3. Add a description and website URL in GitHub settings"
echo "  4. Enable GitHub Actions (CI will run automatically on push)"
echo ""
