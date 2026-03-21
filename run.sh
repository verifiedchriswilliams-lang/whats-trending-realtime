#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  WhatsTrendingInRealTime.com — Setup & Launch Script
#
#  Usage:
#    chmod +x run.sh
#    ./run.sh
#
#  Requirements: Python 3.8+
# ─────────────────────────────────────────────────────────────

set -e

echo ""
echo "======================================================"
echo "  🔥  WhatsTrendingInRealTime.com"
echo "  Setup & Launch"
echo "======================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 not found. Please install Python 3.8+ from python.org"
  exit 1
fi

PYTHON=$(command -v python3)
echo "✓  Python: $($PYTHON --version)"

# Install dependencies
echo ""
echo "Installing dependencies..."

$PYTHON -m pip install feedparser flask pytrends --quiet --break-system-packages 2>/dev/null \
  || $PYTHON -m pip install feedparser flask pytrends --quiet 2>/dev/null \
  || { echo "  Trying with --user flag..."; $PYTHON -m pip install feedparser flask pytrends --quiet --user; }

echo "✓  Dependencies installed"
echo ""
echo "Starting dashboard at http://localhost:8080"
echo "(browser will open automatically)"
echo ""

# Launch
$PYTHON "$(dirname "$0")/trending_dashboard.py"
