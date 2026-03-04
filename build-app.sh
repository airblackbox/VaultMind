#!/bin/bash
# ─────────────────────────────────────────────
#  VaultMind — Build Mac App (.dmg)
#  Run: bash build-app.sh
# ─────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "🔒 VaultMind — Building Mac App"
echo "────────────────────────────────────────"

# ── Check Node.js ──────────────────────────────────────────────
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌  Node.js not found.${NC}"
    echo ""
    echo "Install it via Homebrew:  brew install node"
    echo "or download from:         https://nodejs.org"
    exit 1
fi
echo -e "${GREEN}✓${NC}  Node.js $(node --version)"

# ── Install Electron dependencies ──────────────────────────────
if [ ! -d "node_modules" ]; then
    echo "   Installing Electron (first time, ~200 MB)..."
    npm install
else
    echo -e "${GREEN}✓${NC}  Node modules ready"
fi

# ── Build the .dmg ─────────────────────────────────────────────
echo "   Building VaultMind.dmg..."
npm run build

echo ""
echo -e "${GREEN}✅  Done!${NC}"
echo "────────────────────────────────────────"
echo ""
echo "Your installer is in:  dist/VaultMind-*.dmg"
echo ""
echo "To test without building:  npm start"
echo ""
