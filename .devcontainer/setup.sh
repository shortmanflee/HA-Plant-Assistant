#!/bin/bash
set -e

echo "Cleaning up any existing virtual environment..."
rm -rf .venv

echo "Creating virtual environment..."
python -m venv .venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing Python requirements..."
pip install -r requirements.txt

echo "Installing npm packages..."
npm install

echo "Installing pre-commit..."
pre-commit install

echo "Setting up config directory..."
mkdir -p config
rm -f config/custom_components
ln -sf "$(pwd)/custom_components" config/custom_components

echo "Setup complete!"
