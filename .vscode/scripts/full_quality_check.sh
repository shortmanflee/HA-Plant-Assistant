#!/bin/bash

# Full Quality Check Script
# This script runs all quality checks in sequence

set -e  # Exit on any error

echo "=== Starting Full Quality Check ==="

# Activate virtual environment
source "${WORKSPACE_FOLDER}/.venv/bin/activate"

echo "=== Running Ruff ==="
ruff --config .linter/ruff.toml format .
ruff --config .linter/ruff.toml check . --fix

echo "=== Running MyPy ==="
mypy --config-file .linter/mypy.ini custom_components/

echo "=== Running Bandit ==="
bandit -r custom_components/

echo "=== Running YAML Lint ==="
yamllint --config-file .linter/yamllint .

echo "=== Running CSpell ==="
npm run spell:check

echo "=== Running Markdown Lint ==="
npm run lint:markdown:fix

echo "=== All quality checks complete! ==="
