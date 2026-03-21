#!/bin/bash

# Quick Setup Script for Chrome Profile Manager
# This script helps you get started quickly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════╗"
echo "║  Chrome Profile Manager - Quick Setup           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Step 1: Check if Node.js is installed
echo "Step 1: Checking Node.js installation..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v)
echo "✓ Node.js installed: $NODE_VERSION"
echo ""

# Step 2: Check if npm is installed
echo "Step 2: Checking npm installation..."
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed"
    exit 1
fi

NPM_VERSION=$(npm -v)
echo "✓ npm installed: $NPM_VERSION"
echo ""

# Step 3: Install dependencies
echo "Step 3: Installing dependencies..."
if [ ! -d "node_modules" ]; then
    echo "Installing Playwright and dependencies..."
    npm install
    echo "✓ Dependencies installed"
else
    echo "✓ Dependencies already installed"
fi
echo ""

# Step 4: Make shell script executable
echo "Step 4: Setting up shell script..."
chmod +x chrome-profile-manager.sh
echo "✓ Shell script is now executable"
echo ""

# Step 5: Check Chrome installation
echo "Step 5: Checking Chrome installation..."
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -f "$CHROME_PATH" ]; then
    echo "✓ Chrome found at: $CHROME_PATH"
else
    echo "⚠️  Chrome not found at default location"
    echo "   You may need to update CHROME_PATH in chrome-profile-manager.sh"
fi
echo ""

# Step 6: Create a test profile
echo "Step 6: Creating test profile..."
if [ ! -d "chrome-profiles/profile1" ]; then
    ./chrome-profile-manager.sh create profile1 9222
    echo "✓ Test profile 'profile1' created"
else
    echo "✓ Test profile 'profile1' already exists"
fi
echo ""

# Step 7: Instructions
echo "╔══════════════════════════════════════════════════╗"
echo "║  Setup Complete! 🎉                              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Quick Start Guide:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Start Chrome with the test profile:"
echo "   ./chrome-profile-manager.sh start profile1"
echo ""
echo "2. In another terminal, run the examples:"
echo "   npm run example"
echo ""
echo "3. Or run the test suite:"
echo "   npm test"
echo ""
echo "Available commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ./chrome-profile-manager.sh list       - List all profiles"
echo "  ./chrome-profile-manager.sh status     - Check profile status"
echo "  ./chrome-profile-manager.sh stop profile1  - Stop profile"
echo "  ./chrome-profile-manager.sh create <n> [port]  - Create new profile"
echo ""
echo "Documentation:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  README.md - Full documentation"
echo "  example.js - Usage examples"
echo "  test.js - Test suite"
echo ""
echo "Next steps:"
echo "  1. Run: ./chrome-profile-manager.sh start profile1"
echo "  2. Then: npm run example"
echo ""
