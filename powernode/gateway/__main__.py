"""
API Gateway Entry Point
Run the gateway server
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from powernode.gateway import create_gateway, APIGateway
from powernode.agent.api_routes import router as agent_router
from powernode.marketplace.api_routes import router as marketplace_router
from powernode.oracle.api_routes import router as oracle_router
from powernode.buildstack.api import router as buildstack_router
from powernode.prostack.api import router as prostack_router

# Import PAIneer module
try:
    from powernode.core.data_model import DataModelManager
    from powernode.core.event_bus import EventBus
    from powernode.paineer.module import PAIneerModule
    paineer_module_available = True
except ImportError as e:
    print(f"Warning: PAIneer module not available: {e}")
    paineer_module_available = False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PowerNode API Gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--db-path", help="Path to database directory")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument("--no-cors", action="store_true", help="Disable CORS")
    parser.add_argument("--cors-origins", nargs="+", help="Allowed CORS origins")
    
    args = parser.parse_args()
    
    # Create gateway
    gateway = create_gateway(
        db_path=args.db_path,
        enable_auth=not args.no_auth,
        enable_cors=not args.no_cors,
        cors_origins=args.cors_origins
    )
    
    # Register modules
    print("Registering modules...")
    
    gateway.register_module(
        module_name="agents",
        base_path="/api/v1/agents",
        router=agent_router
    )
    
    gateway.register_module(
        module_name="marketplace",
        base_path="/api/v1/marketplace",
        router=marketplace_router
    )
    
    gateway.register_module(
        module_name="oracles",
        base_path="/api/v1/oracles",
        router=oracle_router
    )
    
    gateway.register_module(
        module_name="buildstack",
        base_path="/api/v1/buildstack",
        router=buildstack_router
    )
    
    gateway.register_module(
        module_name="prostack",
        base_path="/api/v1/prostack",
        router=prostack_router
    )
    
    # Register PAIneer module
    if paineer_module_available:
        try:
            # Initialize data manager and event bus
            db_path = args.db_path or os.path.expanduser("~/.powernode/data_model.db")
            data_manager = DataModelManager(db_path=db_path)
            event_bus = EventBus(data_manager)
            
            # Create and initialize PAIneer module
            paineer_module = PAIneerModule(
                event_bus=event_bus,
                data_manager=data_manager
            )
            
            # Initialize with configuration
            config = {
                "db_path": db_path,
                "metrics_collection_interval": 30
            }
            if paineer_module.initialize(config):
                gateway.register_module(
                    module_name="paineer",
                    base_path="/api/v1/paineer",
                    router=paineer_module.get_router()
                )
                print("✓ Registered paineer module")
            else:
                print("⚠ Warning: PAIneer module initialization failed")
        except Exception as e:
            print(f"⚠ Warning: Failed to register PAIneer module: {e}")
    else:
        print("⚠ Warning: PAIneer module not available")
    
    print(f"API Gateway starting on {args.host}:{args.port}")
    print(f"API Documentation: http://{args.host}:{args.port}/docs")
    
    # Run gateway
    gateway.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()









