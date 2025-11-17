"""
Orchestration Layer
Manages complex workflows and service coordination
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Step:
    """Represents a single step in a workflow"""
    
    def __init__(
        self,
        name: str,
        service: str,
        endpoint: str,
        method: str = "POST",
        params: Optional[Dict] = None,
        depends_on: Optional[List[str]] = None,
        retry_count: int = 0,
        timeout: Optional[int] = None
    ):
        self.name = name
        self.service = service
        self.endpoint = endpoint
        self.method = method
        self.params = params or {}
        self.depends_on = depends_on or []
        self.retry_count = retry_count
        self.timeout = timeout
        self.status = WorkflowStatus.PENDING
        self.result: Optional[Dict] = None
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None


class Workflow:
    """Represents a workflow with multiple steps"""
    
    def __init__(self, workflow_id: str, name: str, steps: List[Step]):
        self.workflow_id = workflow_id
        self.name = name
        self.steps = {step.name: step for step in steps}
        self.status = WorkflowStatus.PENDING
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[Dict] = None
        self.error: Optional[str] = None


class Orchestrator:
    """Orchestrates complex workflows across multiple services"""
    
    def __init__(self, router: 'ModuleRouter', state_manager: 'StateManager'):
        """
        Initialize Orchestrator
        
        Args:
            router: ModuleRouter instance for routing requests
            state_manager: StateManager instance for state management
        """
        self.router = router
        self.state_manager = state_manager
        self.workflows: Dict[str, Workflow] = {}
        self._lock = asyncio.Lock()
    
    async def create_workflow(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        workflow_id: Optional[str] = None
    ) -> Workflow:
        """Create a new workflow"""
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())
        
        workflow_steps = []
        for step_def in steps:
            step = Step(
                name=step_def['name'],
                service=step_def['service'],
                endpoint=step_def['endpoint'],
                method=step_def.get('method', 'POST'),
                params=step_def.get('params', {}),
                depends_on=step_def.get('depends_on', []),
                retry_count=step_def.get('retry_count', 0),
                timeout=step_def.get('timeout')
            )
            workflow_steps.append(step)
        
        workflow = Workflow(workflow_id, name, workflow_steps)
        
        async with self._lock:
            self.workflows[workflow_id] = workflow
        
        # Persist workflow definition
        self.state_manager.set(
            f"workflow:{workflow_id}",
            {
                "name": name,
                "steps": [
                    {
                        "name": s.name,
                        "service": s.service,
                        "endpoint": s.endpoint,
                        "method": s.method,
                        "params": s.params,
                        "depends_on": s.depends_on,
                        "retry_count": s.retry_count,
                        "timeout": s.timeout
                    }
                    for s in workflow_steps
                ]
            },
            namespace="workflows"
        )
        
        return workflow
    
    async def execute_workflow(
        self,
        workflow_id: str,
        initial_context: Optional[Dict] = None
    ) -> Dict:
        """Execute a workflow"""
        async with self._lock:
            workflow = self.workflows.get(workflow_id)
            if not workflow:
                # Try to load from state
                workflow_data = self.state_manager.get(f"workflow:{workflow_id}", namespace="workflows")
                if not workflow_data:
                    raise ValueError(f"Workflow {workflow_id} not found")
                
                # Reconstruct workflow
                steps = []
                for step_def in workflow_data['steps']:
                    step = Step(
                        name=step_def['name'],
                        service=step_def['service'],
                        endpoint=step_def['endpoint'],
                        method=step_def.get('method', 'POST'),
                        params=step_def.get('params', {}),
                        depends_on=step_def.get('depends_on', []),
                        retry_count=step_def.get('retry_count', 0),
                        timeout=step_def.get('timeout')
                    )
                    steps.append(step)
                
                workflow = Workflow(workflow_id, workflow_data['name'], steps)
                self.workflows[workflow_id] = workflow
        
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.utcnow()
        
        context = initial_context or {}
        results = {}
        
        try:
            # Execute steps in dependency order
            executed_steps = set()
            
            while len(executed_steps) < len(workflow.steps):
                # Find steps that can be executed (all dependencies met)
                ready_steps = [
                    step for step in workflow.steps.values()
                    if step.name not in executed_steps
                    and all(dep in executed_steps for dep in step.depends_on)
                ]
                
                if not ready_steps:
                    # Circular dependency or missing step
                    raise ValueError("Cannot resolve step dependencies")
                
                # Execute ready steps in parallel
                tasks = [self._execute_step(step, context, results) for step in ready_steps]
                step_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for step, result in zip(ready_steps, step_results):
                    if isinstance(result, Exception):
                        step.status = WorkflowStatus.FAILED
                        step.error = str(result)
                        workflow.status = WorkflowStatus.FAILED
                        workflow.error = f"Step {step.name} failed: {str(result)}"
                        raise result
                    else:
                        step.status = WorkflowStatus.COMPLETED
                        step.result = result
                        results[step.name] = result
                        executed_steps.add(step.name)
            
            workflow.status = WorkflowStatus.COMPLETED
            workflow.result = results
            
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.error = str(e)
            logger.error(f"Workflow {workflow_id} failed: {e}")
        
        finally:
            workflow.completed_at = datetime.utcnow()
            
            # Persist workflow execution state
            self.state_manager.set(
                f"workflow_execution:{workflow_id}",
                {
                    "status": workflow.status.value,
                    "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
                    "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                    "result": workflow.result,
                    "error": workflow.error
                },
                namespace="workflows"
            )
        
        return {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "result": workflow.result,
            "error": workflow.error
        }
    
    async def _execute_step(
        self,
        step: Step,
        context: Dict,
        previous_results: Dict
    ) -> Dict:
        """Execute a single workflow step"""
        step.started_at = datetime.utcnow()
        step.status = WorkflowStatus.RUNNING
        
        # Merge context and previous results into params
        params = {}
        params.update(context)
        params.update(previous_results)
        params.update(step.params)
        
        # Resolve parameter references (e.g., ${step_name.result})
        resolved_params = self._resolve_params(params, previous_results)
        
        retries = 0
        last_error = None
        
        while retries <= step.retry_count:
            try:
                # Route request through gateway
                response = await self.router.route_request(
                    service=step.service,
                    endpoint=step.endpoint,
                    method=step.method,
                    params=resolved_params,
                    timeout=step.timeout
                )
                
                step.completed_at = datetime.utcnow()
                return response
                
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= step.retry_count:
                    await asyncio.sleep(1 * retries)  # Exponential backoff
                else:
                    raise
        
        raise last_error
    
    def _resolve_params(self, params: Dict, results: Dict) -> Dict:
        """Resolve parameter references in params"""
        resolved = {}
        
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # Reference to previous step result
                ref = value[2:-1]
                if "." in ref:
                    step_name, result_key = ref.split(".", 1)
                    if step_name in results:
                        resolved[key] = results[step_name].get(result_key)
                    else:
                        resolved[key] = value  # Keep unresolved
                else:
                    resolved[key] = value
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, results)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_params(item, results) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                resolved[key] = value
        
        return resolved
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow execution status"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            return {
                "workflow_id": workflow_id,
                "name": workflow.name,
                "status": workflow.status.value,
                "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                "result": workflow.result,
                "error": workflow.error
            }
        
        # Try to load from state
        execution_data = self.state_manager.get(f"workflow_execution:{workflow_id}", namespace="workflows")
        return execution_data
    
    def list_workflows(self, status: Optional[WorkflowStatus] = None) -> List[Dict]:
        """List all workflows"""
        workflows = []
        
        for workflow_id, workflow in self.workflows.items():
            if status is None or workflow.status == status:
                workflows.append({
                    "workflow_id": workflow_id,
                    "name": workflow.name,
                    "status": workflow.status.value,
                    "created_at": workflow.created_at.isoformat()
                })
        
        return workflows

