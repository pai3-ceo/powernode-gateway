"""
Module Router
Handles routing requests to registered modules
"""

import asyncio
import httpx
from typing import Dict, Optional, List, Callable, Any
from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute
import logging

logger = logging.getLogger(__name__)


class ModuleRegistration:
    """Represents a registered module"""
    
    def __init__(
        self,
        module_name: str,
        base_path: str,
        router: Optional[APIRouter] = None,
        service_url: Optional[str] = None,
        health_check_endpoint: Optional[str] = None
    ):
        """
        Initialize module registration
        
        Args:
            module_name: Unique name for the module
            base_path: Base path prefix for routes (e.g., "/api/v1/cabinets")
            router: FastAPI router instance (for internal modules)
            service_url: URL for external service (for external modules)
            health_check_endpoint: Endpoint to check service health
        """
        self.module_name = module_name
        self.base_path = base_path
        self.router = router
        self.service_url = service_url
        self.health_check_endpoint = health_check_endpoint
        self.healthy = True
        self.last_health_check = None


class ModuleRouter:
    """Routes requests to registered modules"""
    
    def __init__(self):
        """Initialize ModuleRouter"""
        self.modules: Dict[str, ModuleRegistration] = {}
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    def register_module(
        self,
        module_name: str,
        base_path: str,
        router: Optional[APIRouter] = None,
        service_url: Optional[str] = None,
        health_check_endpoint: Optional[str] = None
    ):
        """Register a module"""
        registration = ModuleRegistration(
            module_name=module_name,
            base_path=base_path,
            router=router,
            service_url=service_url,
            health_check_endpoint=health_check_endpoint
        )
        
        self.modules[module_name] = registration
        logger.info(f"Registered module: {module_name} at {base_path}")
    
    def unregister_module(self, module_name: str):
        """Unregister a module"""
        if module_name in self.modules:
            del self.modules[module_name]
            logger.info(f"Unregistered module: {module_name}")
    
    def get_module_by_path(self, path: str) -> Optional[ModuleRegistration]:
        """Find module by matching path"""
        for module in self.modules.values():
            if path.startswith(module.base_path):
                return module
        return None
    
    def get_module(self, module_name: str) -> Optional[ModuleRegistration]:
        """Get module by name"""
        return self.modules.get(module_name)
    
    async def route_request(
        self,
        service: str,
        endpoint: str,
        method: str = "POST",
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict:
        """
        Route a request to a service
        
        Args:
            service: Service/module name
            endpoint: Endpoint path (relative to base_path)
            method: HTTP method
            params: Request parameters
            headers: Additional headers
            timeout: Request timeout in seconds
        
        Returns:
            Response dictionary
        """
        module = self.get_module(service)
        if not module:
            raise ValueError(f"Service {service} not found")
        
        if module.router:
            # Internal module - route through FastAPI router
            return await self._route_internal(module, endpoint, method, params, headers)
        elif module.service_url:
            # External service - make HTTP request
            return await self._route_external(module, endpoint, method, params, headers, timeout)
        else:
            raise ValueError(f"Module {service} has no router or service_url configured")
    
    async def _route_internal(
        self,
        module: ModuleRegistration,
        endpoint: str,
        method: str,
        params: Optional[Dict],
        headers: Optional[Dict]
    ) -> Dict:
        """Route to internal FastAPI router"""
        # For internal routing, we need to simulate a request
        # This is a simplified version - in production, you'd use TestClient
        # or directly call the route handlers
        
        # Build full path
        full_path = f"{module.base_path.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # Find matching route
        for route in module.router.routes:
            if isinstance(route, APIRoute):
                # Check if route matches
                if self._route_matches(route, full_path, method):
                    # Extract path parameters
                    path_params = self._extract_path_params(route.path, full_path)
                    
                    # Merge params
                    request_params = params or {}
                    request_params.update(path_params)
                    
                    # Call route handler
                    try:
                        if method.upper() == "GET":
                            result = await route.endpoint(**request_params)
                        else:
                            result = await route.endpoint(**request_params)
                        
                        # Convert to dict if needed
                        if hasattr(result, 'dict'):
                            return result.dict()
                        elif isinstance(result, dict):
                            return result
                        else:
                            return {"result": result}
                    except Exception as e:
                        logger.error(f"Error routing to {full_path}: {e}")
                        raise
        
        raise ValueError(f"No route found for {full_path} with method {method}")
    
    def _route_matches(self, route: APIRoute, path: str, method: str) -> bool:
        """Check if route matches path and method"""
        # Simplified matching - in production, use proper path matching
        if method.upper() not in route.methods:
            return False
        
        # Basic path matching (simplified)
        route_path = route.path.replace("{", "").replace("}", "")
        return path.startswith(route_path.rstrip("/"))
    
    def _extract_path_params(self, route_path: str, request_path: str) -> Dict:
        """Extract path parameters from route"""
        # Simplified - in production, use proper path parameter extraction
        # This is a placeholder - actual implementation would parse route patterns
        return {}
    
    async def _route_external(
        self,
        module: ModuleRegistration,
        endpoint: str,
        method: str,
        params: Optional[Dict],
        headers: Optional[Dict],
        timeout: Optional[int]
    ) -> Dict:
        """Route to external service via HTTP"""
        url = f"{module.service_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        request_headers = headers or {}
        
        try:
            if method.upper() == "GET":
                response = await self.http_client.get(
                    url,
                    params=params,
                    headers=request_headers,
                    timeout=timeout
                )
            elif method.upper() == "POST":
                response = await self.http_client.post(
                    url,
                    json=params,
                    headers=request_headers,
                    timeout=timeout
                )
            elif method.upper() == "PUT":
                response = await self.http_client.put(
                    url,
                    json=params,
                    headers=request_headers,
                    timeout=timeout
                )
            elif method.upper() == "DELETE":
                response = await self.http_client.delete(
                    url,
                    params=params,
                    headers=request_headers,
                    timeout=timeout
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error routing to {url}: {e}")
            raise
    
    async def check_health(self, module_name: Optional[str] = None) -> Dict[str, bool]:
        """Check health of modules"""
        results = {}
        
        modules_to_check = [self.modules[module_name]] if module_name else self.modules.values()
        
        for module in modules_to_check:
            if module.router:
                # Internal modules are always healthy if registered
                module.healthy = True
                results[module.module_name] = True
            elif module.service_url and module.health_check_endpoint:
                # Check external service
                try:
                    url = f"{module.service_url.rstrip('/')}/{module.health_check_endpoint.lstrip('/')}"
                    response = await self.http_client.get(url, timeout=5.0)
                    module.healthy = response.status_code == 200
                    results[module.module_name] = module.healthy
                except Exception as e:
                    logger.warning(f"Health check failed for {module.module_name}: {e}")
                    module.healthy = False
                    results[module.module_name] = False
            else:
                # No health check configured
                results[module.module_name] = True
        
        return results
    
    def list_modules(self) -> List[Dict]:
        """List all registered modules"""
        return [
            {
                "name": module.module_name,
                "base_path": module.base_path,
                "healthy": module.healthy,
                "type": "internal" if module.router else "external"
            }
            for module in self.modules.values()
        ]

