#!/bin/bash
# Start PowerNode API Gateway with all modules

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Set Python path
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run gateway
python -m powernode.gateway.integration_example \
    --host "${GATEWAY_HOST:-0.0.0.0}" \
    --port "${GATEWAY_PORT:-8000}" \
    --db-path "${GATEWAY_DB_PATH:-}" \
    "${@}"









