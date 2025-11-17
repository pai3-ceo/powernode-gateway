# API Gateway Quick Start

## Installation

```bash
# Install dependencies
pip install -r powernode/gateway/requirements.txt
```

## Start the Gateway

### Option 1: Using the integration script (recommended)
```bash
python -m powernode.gateway.integration_example
```

### Option 2: Using the shell script
```bash
./powernode/gateway/start_gateway.sh
```

### Option 3: Programmatically
```python
from powernode.gateway.integration_example import create_integrated_gateway

gateway = create_integrated_gateway()
gateway.run(host="0.0.0.0", port=8000)
```

## Access the Gateway

- **API Gateway**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Default Credentials

On first run, a default admin user is created:
- **Username**: `admin`
- **Password**: `admin123`

**⚠️ Change this password immediately in production!**

## Basic Usage

### 1. Login and Get Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

Response:
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "...",
    "username": "admin",
    "role": "admin"
  }
}
```

### 2. Use Token for Authenticated Requests

```bash
TOKEN="your-token-here"

curl http://localhost:8000/api/v1/modules \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Create a User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "password": "securepassword",
    "email": "user@example.com"
  }'
```

### 4. Store State

```bash
curl -X POST http://localhost:8000/api/v1/state/my-key \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": {"data": "example"},
    "namespace": "my-namespace",
    "ttl": 3600
  }'
```

### 5. Retrieve State

```bash
curl http://localhost:8000/api/v1/state/my-key?namespace=my-namespace \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Create and Execute a Workflow

```bash
# Create workflow
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "process-document",
    "steps": [
      {
        "name": "analyze",
        "service": "prostack",
        "endpoint": "/api/v1/prostack/documents/analyze",
        "method": "POST"
      }
    ]
  }'

# Execute workflow
curl -X POST http://localhost:8000/api/v1/workflows/{workflow_id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/file"}'
```

## Module Endpoints

All registered modules are accessible through the gateway:

- **Agents**: `/api/v1/agents/*`
- **Marketplace**: `/api/v1/marketplace/*`
- **Oracles**: `/api/v1/oracles/*`
- **Buildstack**: `/api/v1/buildstack/*`
- **Prostack**: `/api/v1/prostack/*`
- **Cabinets**: `/api/v1/cabinets/*` (if integrated)

## Configuration

### Environment Variables

```bash
export GATEWAY_HOST=0.0.0.0
export GATEWAY_PORT=8000
export GATEWAY_DB_PATH=~/.powernode/gateway.db
```

### Command Line Options

```bash
python -m powernode.gateway.integration_example \
  --host 0.0.0.0 \
  --port 8000 \
  --db-path ~/.powernode/gateway.db \
  --no-auth  # Disable authentication (development only)
  --no-cors  # Disable CORS
```

## Development Mode

For development without authentication:

```bash
python -m powernode.gateway.integration_example --no-auth
```

## Troubleshooting

### Module Not Found
If a module fails to register, check:
1. Module dependencies are installed
2. Module router is properly exported
3. Check logs for import errors

### Authentication Errors
- Verify token is valid and not expired
- Check token format: `Bearer <token>`
- Ensure user account is active

### State Not Persisting
- Check database path permissions
- Verify database directory exists
- Check disk space

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Explore the API documentation at `/docs`
- Check module health at `/api/v1/modules/health`
- Review workflow examples in the orchestrator documentation









