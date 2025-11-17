# PowerNode API Gateway

A centralized, modular, secure, and well-orchestrated API gateway system for PowerNode modules. All modules use the gateway without relying on any cloud services.

## Features

- **Modular Architecture**: Register and route requests to multiple backend modules
- **Authentication & Authorization**: JWT-based authentication with role-based access control
- **State Management**: Centralized state management with persistence and caching
- **Orchestration**: Complex workflow management across multiple services
- **Self-Hosted**: No cloud dependencies - everything runs locally
- **Security**: Built-in authentication middleware and permission system

## Architecture

```
┌─────────────────┐
│   API Gateway   │
│   (FastAPI)     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│ Auth  │ │ State │
│Manager│ │Manager│
└───────┘ └───────┘
    │         │
    └────┬────┘
         │
┌────────▼────────┐
│  Module Router  │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│Orchestrator│ Modules│
└───────────┘ └───────┘
```

## Components

### 1. API Gateway (`gateway.py`)
Main entry point that handles all incoming requests, applies middleware, and routes to modules.

### 2. Authentication (`auth.py`)
- JWT-based token authentication
- Role-based access control (User, Admin, Service, Guest)
- Permission system (Read, Write, Admin, Execute)
- API key support for service-to-service communication
- Session management

### 3. State Management (`state.py`)
- Key-value state storage with namespaces
- In-memory caching with persistence
- TTL support for temporary state
- State history/audit trail
- Thread-safe operations

### 4. Orchestrator (`orchestrator.py`)
- Workflow definition and execution
- Step dependencies and parallel execution
- Retry logic and error handling
- Context passing between steps

### 5. Module Router (`router.py`)
- Dynamic module registration
- Request routing to internal/external services
- Health checking
- Service discovery

## Installation

```bash
pip install -r powernode/gateway/requirements.txt
```

## Usage

### Basic Setup

```python
from powernode.gateway import create_gateway, APIGateway

# Create gateway
gateway = create_gateway(
    db_path="~/.powernode/gateway.db",
    enable_auth=True,
    enable_cors=True
)

# Register modules
gateway.register_module(
    module_name="cabinets",
    base_path="/api/v1/cabinets",
    router=cabinet_router
)

# Run gateway
gateway.run(host="0.0.0.0", port=8000)
```

### Command Line

```bash
# Run gateway with all modules
python -m powernode.gateway --host 0.0.0.0 --port 8000

# Run without authentication (development)
python -m powernode.gateway --no-auth

# Custom CORS origins
python -m powernode.gateway --cors-origins http://localhost:3000 https://app.example.com
```

### Authentication

#### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

#### Using Token
```bash
curl http://localhost:8000/api/v1/modules \
  -H "Authorization: Bearer <token>"
```

#### Create API Key
```bash
curl -X POST http://localhost:8000/api/v1/auth/api-key \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-service", "permissions": ["read", "write"]}'
```

### State Management

#### Set State
```bash
curl -X POST http://localhost:8000/api/v1/state/my-key \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"value": {"data": "example"}, "namespace": "my-namespace", "ttl": 3600}'
```

#### Get State
```bash
curl http://localhost:8000/api/v1/state/my-key?namespace=my-namespace \
  -H "Authorization: Bearer <token>"
```

### Workflow Orchestration

#### Create Workflow
```bash
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "process-document",
    "steps": [
      {
        "name": "upload",
        "service": "cabinets",
        "endpoint": "/api/v1/cabinets/{cabinet_id}/files",
        "method": "POST"
      },
      {
        "name": "analyze",
        "service": "prostack",
        "endpoint": "/api/v1/prostack/documents/analyze",
        "method": "POST",
        "depends_on": ["upload"]
      }
    ]
  }'
```

#### Execute Workflow
```bash
curl -X POST http://localhost:8000/api/v1/workflows/{workflow_id}/execute \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"cabinet_id": "123", "file_path": "/path/to/file"}'
```

## Module Registration

Modules can be registered as:

1. **Internal Modules** (FastAPI routers):
```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/items")
async def list_items():
    return {"items": []}

gateway.register_module(
    module_name="my-module",
    base_path="/api/v1/my-module",
    router=router
)
```

2. **External Services** (HTTP endpoints):
```python
gateway.register_module(
    module_name="external-service",
    base_path="/api/v1/external",
    service_url="http://localhost:9000",
    health_check_endpoint="/health"
)
```

## Security

- **JWT Tokens**: Secure token-based authentication
- **RBAC**: Role-based access control
- **Permissions**: Fine-grained permission system
- **API Keys**: Service-to-service authentication
- **Session Management**: Secure session tracking

## State Management

- **Namespaces**: Organize state by namespace
- **TTL**: Automatic expiration of temporary state
- **Persistence**: SQLite-based persistence
- **Caching**: In-memory caching for performance
- **History**: Audit trail of state changes

## Workflow Orchestration

- **Dependencies**: Define step dependencies
- **Parallel Execution**: Execute independent steps in parallel
- **Retry Logic**: Automatic retry on failure
- **Context Passing**: Share data between steps
- **Error Handling**: Graceful error handling

## API Documentation

Once the gateway is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

### Environment Variables

- `GATEWAY_DB_PATH`: Database path (default: `~/.powernode/gateway.db`)
- `GATEWAY_SECRET_KEY`: JWT secret key (auto-generated if not set)
- `GATEWAY_HOST`: Host to bind to (default: `0.0.0.0`)
- `GATEWAY_PORT`: Port to bind to (default: `8000`)

### Database Schema

The gateway creates SQLite databases for:
- Authentication (`auth.db`): Users, sessions, API keys
- State (`state.db`): State storage and history

## Development

```bash
# Install dependencies
pip install -r powernode/gateway/requirements.txt

# Run tests (when available)
pytest tests/gateway/

# Run gateway in development mode
python -m powernode.gateway --no-auth
```

## Integration with Existing Modules

The gateway automatically integrates with:
- `powernode.agent` - Agent framework
- `powernode.marketplace` - Marketplace
- `powernode.oracle` - Oracle connectors
- `powernode.buildstack` - Build stack
- `powernode.prostack` - Pro stack

All existing module routes are automatically registered when starting the gateway.

## License

See main project license.









