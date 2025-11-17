"""
API Gateway
Central entry point for all API requests with authentication, routing, and orchestration
"""

import os
import logging
from typing import Optional, Dict, List
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

from .auth import AuthManager, Permission
from .state import StateManager
from .router import ModuleRouter
from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


class APIGateway:
    """Main API Gateway class"""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        secret_key: Optional[str] = None,
        enable_auth: bool = True,
        enable_cors: bool = True,
        cors_origins: List[str] = None
    ):
        """
        Initialize API Gateway
        
        Args:
            db_path: Path to database directory
            secret_key: Secret key for JWT (generated if not provided)
            enable_auth: Enable authentication middleware
            enable_cors: Enable CORS middleware
            cors_origins: Allowed CORS origins
        """
        self.app = FastAPI(
            title="PowerNode API Gateway",
            description="Centralized API Gateway for PowerNode modules",
            version="1.0.0"
        )
        
        # Initialize components
        self.auth_manager = AuthManager(db_path, secret_key) if enable_auth else None
        self.state_manager = StateManager(db_path)
        self.router = ModuleRouter()
        self.orchestrator = Orchestrator(self.router, self.state_manager)
        
        # Setup middleware
        if enable_cors:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins or ["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        
        if enable_auth:
            self.app.middleware("http")(self._auth_middleware)
        
        # Setup routes
        self._setup_routes()
    
    async def _auth_middleware(self, request: Request, call_next):
        """Authentication middleware"""
        # Skip auth for public endpoints
        public_paths = ["/health", "/api/v1/auth/login", "/api/v1/auth/register", "/docs", "/openapi.json"]
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)
        
        # Check for token in header
        authorization = request.headers.get("Authorization")
        if not authorization:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing authorization header"}
            )
        
        # Extract token
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
        
        # Verify token
        if self.auth_manager:
            user_info = self.auth_manager.verify_token(token)
            if not user_info:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid or expired token"}
                )
            
            # Attach user info to request state
            request.state.user = user_info
        
        response = await call_next(request)
        return response
    
    def _setup_routes(self):
        """Setup gateway routes"""
        
        # Health check
        @self.app.get("/health")
        async def health_check():
            """Gateway health check"""
            module_health = await self.router.check_health()
            return {
                "status": "healthy",
                "gateway": "operational",
                "modules": module_health
            }
        
        # Authentication routes
        if self.auth_manager:
            @self.app.post("/api/v1/auth/login")
            async def login(request: Request, username: str, password: str):
                """Login endpoint"""
                ip_address = request.client.host if request.client else None
                result = self.auth_manager.authenticate(username, password, ip_address)
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid credentials")
                return result
            
            @self.app.post("/api/v1/auth/register")
            async def register(username: str, password: str, email: Optional[str] = None):
                """Register new user"""
                try:
                    user = self.auth_manager.create_user(username, password, email)
                    return {"success": True, "user": user}
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
            
            @self.app.get("/api/v1/auth/me")
            async def get_current_user(request: Request):
                """Get current user info"""
                if not hasattr(request.state, 'user'):
                    raise HTTPException(status_code=401, detail="Not authenticated")
                return {"user": request.state.user}
            
            @self.app.post("/api/v1/auth/api-key")
            async def create_api_key(
                request: Request,
                name: str,
                permissions: Optional[List[str]] = None,
                expires_days: Optional[int] = None
            ):
                """Create API key"""
                if not hasattr(request.state, 'user'):
                    raise HTTPException(status_code=401, detail="Not authenticated")
                
                from .auth import Permission as Perm
                perm_list = [Perm(p) for p in (permissions or [])]
                
                api_key = self.auth_manager.create_api_key(
                    request.state.user['user_id'],
                    name,
                    perm_list,
                    expires_days
                )
                return {"api_key": api_key}
        
        # State management routes
        @self.app.get("/api/v1/state/{key}")
        async def get_state(key: str, namespace: str = "default"):
            """Get state value"""
            value = self.state_manager.get(key, namespace)
            if value is None:
                raise HTTPException(status_code=404, detail="Key not found")
            return {"key": key, "value": value, "namespace": namespace}
        
        @self.app.post("/api/v1/state/{key}")
        async def set_state(
            request: Request,
            key: str,
            value: Dict,
            namespace: str = "default",
            ttl: Optional[int] = None
        ):
            """Set state value"""
            changed_by = None
            if hasattr(request.state, 'user'):
                changed_by = request.state.user.get('username')
            
            self.state_manager.set(key, value, namespace, ttl, changed_by=changed_by)
            return {"success": True, "key": key, "namespace": namespace}
        
        @self.app.delete("/api/v1/state/{key}")
        async def delete_state(request: Request, key: str, namespace: str = "default"):
            """Delete state value"""
            changed_by = None
            if hasattr(request.state, 'user'):
                changed_by = request.state.user.get('username')
            
            self.state_manager.delete(key, namespace, changed_by=changed_by)
            return {"success": True}
        
        @self.app.get("/api/v1/state")
        async def list_state_keys(namespace: str = "default", pattern: Optional[str] = None):
            """List state keys"""
            keys = self.state_manager.list_keys(namespace, pattern)
            return {"keys": keys, "namespace": namespace}
        
        # Orchestration routes
        @self.app.post("/api/v1/workflows")
        async def create_workflow(name: str, steps: List[Dict], workflow_id: Optional[str] = None):
            """Create a workflow"""
            workflow = await self.orchestrator.create_workflow(name, steps, workflow_id)
            return {
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "status": workflow.status.value
            }
        
        @self.app.post("/api/v1/workflows/{workflow_id}/execute")
        async def execute_workflow(workflow_id: str, context: Optional[Dict] = None):
            """Execute a workflow"""
            result = await self.orchestrator.execute_workflow(workflow_id, context)
            return result
        
        @self.app.get("/api/v1/workflows/{workflow_id}")
        async def get_workflow_status(workflow_id: str):
            """Get workflow status"""
            status = self.orchestrator.get_workflow_status(workflow_id)
            if not status:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return status
        
        @self.app.get("/api/v1/workflows")
        async def list_workflows(status: Optional[str] = None):
            """List workflows"""
            from .orchestrator import WorkflowStatus
            status_enum = WorkflowStatus(status) if status else None
            workflows = self.orchestrator.list_workflows(status_enum)
            return {"workflows": workflows}
        
        # Module management routes
        @self.app.get("/api/v1/modules")
        async def list_modules():
            """List registered modules"""
            modules = self.router.list_modules()
            return {"modules": modules}
        
        @self.app.get("/api/v1/modules/health")
        async def check_module_health():
            """Check health of all modules"""
            health = await self.router.check_health()
            return {"health": health}
    
    def register_module(
        self,
        module_name: str,
        base_path: str,
        router=None,
        service_url: Optional[str] = None,
        health_check_endpoint: Optional[str] = None
    ):
        """Register a module with the gateway"""
        self.router.register_module(
            module_name=module_name,
            base_path=base_path,
            router=router,
            service_url=service_url,
            health_check_endpoint=health_check_endpoint
        )
        
        # Include router in main app if provided
        if router:
            self.app.include_router(router)
    
    def run(self, host: str = "0.0.0.0", port: int = 8000, **kwargs):
        """Run the gateway server"""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_gateway(
    db_path: Optional[str] = None,
    secret_key: Optional[str] = None,
    enable_auth: bool = True,
    enable_cors: bool = True,
    cors_origins: List[str] = None
) -> APIGateway:
    """Factory function to create and configure API Gateway"""
    return APIGateway(
        db_path=db_path,
        secret_key=secret_key,
        enable_auth=enable_auth,
        enable_cors=enable_cors,
        cors_origins=cors_origins
    )

