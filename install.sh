#!/bin/bash
# Installation script for media sorting utility (Arch Linux)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "=========================================="
echo "Media Sorting Utility - Installation"
echo "=========================================="
echo

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Install it with: sudo pacman -S python"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo
echo "To run the utility, use: ./run.sh"
echo "Or activate manually: source venv/bin/activate && python main.py"

