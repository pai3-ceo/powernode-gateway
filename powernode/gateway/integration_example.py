"""
Integration Example
Shows how to integrate the API Gateway with all PowerNode modules
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from powernode.gateway import create_gateway, APIGateway

# Import module routers
try:
    from powernode.agent.api_routes import router as agent_router
except ImportError:
    agent_router = None
    print("Warning: Agent router not available")

try:
    from powernode.marketplace.api_routes import router as marketplace_router
except ImportError:
    marketplace_router = None
    print("Warning: Marketplace router not available")

try:
    from powernode.oracle.api_routes import router as oracle_router
except ImportError:
    oracle_router = None
    print("Warning: Oracle router not available")

try:
    from powernode.buildstack.api import router as buildstack_router
except ImportError:
    buildstack_router = None
    print("Warning: Buildstack router not available")

try:
    from powernode.prostack.api import router as prostack_router
except ImportError:
    prostack_router = None
    print("Warning: Prostack router not available")


def create_integrated_gateway(
    db_path: str = None,
    enable_auth: bool = True,
    enable_cors: bool = True
) -> APIGateway:
    """
    Create an API Gateway with all modules integrated
    
    Args:
        db_path: Path to database directory
        enable_auth: Enable authentication
        enable_cors: Enable CORS
    
    Returns:
        Configured APIGateway instance
    """
    # Create gateway
    gateway = create_gateway(
        db_path=db_path,
        enable_auth=enable_auth,
        enable_cors=enable_cors
    )
    
    # Register all available modules
    if agent_router:
        gateway.register_module(
            module_name="agents",
            base_path="/api/v1/agents",
            router=agent_router
        )
        print("✓ Registered agents module")
    
    if marketplace_router:
        gateway.register_module(
            module_name="marketplace",
            base_path="/api/v1/marketplace",
            router=marketplace_router
        )
        print("✓ Registered marketplace module")
    
    if oracle_router:
        gateway.register_module(
            module_name="oracles",
            base_path="/api/v1/oracles",
            router=oracle_router
        )
        print("✓ Registered oracles module")
    
    if buildstack_router:
        gateway.register_module(
            module_name="buildstack",
            base_path="/api/v1/buildstack",
            router=buildstack_router
        )
        print("✓ Registered buildstack module")
    
    if prostack_router:
        gateway.register_module(
            module_name="prostack",
            base_path="/api/v1/prostack",
            router=prostack_router
        )
        print("✓ Registered prostack module")
    
    # Register cabinet module (needs special handling since it's a full app)
    # We'll create a router from the cabinet endpoints
    try:
        from fastapi import APIRouter
        from powernode.cabinet.api import app as cabinet_app
        
        # Extract routes from cabinet app
        cabinet_router = APIRouter()
        for route in cabinet_app.routes:
            if hasattr(route, 'path') and route.path.startswith('/api'):
                # Add route to router
                cabinet_router.routes.append(route)
        
        gateway.register_module(
            module_name="cabinets",
            base_path="/api/v1/cabinets",
            router=cabinet_router
        )
        print("✓ Registered cabinets module")
    except Exception as e:
        print(f"Warning: Could not register cabinets module: {e}")
    
    return gateway


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PowerNode API Gateway with all modules")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--db-path", help="Path to database directory")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument("--no-cors", action="store_true", help="Disable CORS")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("PowerNode API Gateway - Integrated Setup")
    print("=" * 60)
    
    # Create integrated gateway
    gateway = create_integrated_gateway(
        db_path=args.db_path,
        enable_auth=not args.no_auth,
        enable_cors=not args.no_cors
    )
    
    print("\n" + "=" * 60)
    print(f"Starting API Gateway on {args.host}:{args.port}")
    print(f"API Documentation: http://{args.host}:{args.port}/docs")
    print(f"Health Check: http://{args.host}:{args.port}/health")
    print("=" * 60 + "\n")
    
    # Run gateway
    gateway.run(host=args.host, port=args.port)









