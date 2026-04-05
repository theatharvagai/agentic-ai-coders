from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class File(BaseModel):
    path: str = Field(description="File path to create/modify")
    purpose: str = Field(description="Purpose of the file")
    
class Plan(BaseModel):
    name: str = Field(description="Name of the app")
    description: str = Field(description="Description of the app")
    techstack: str = Field(description="Tech stack used")
    features: List[str] = Field(description="Features list")
    files: List[File] = Field(description="List of files to manage")

class ImplementationTask(BaseModel):
    filepath: str = Field(description="Target file path")
    task_description: str = Field(description="Detailed step by step task")

class TaskPlan(BaseModel):
    implementation_steps: List[ImplementationTask] = Field(description="List of steps")
    model_config = ConfigDict(extra="allow")

# We add api_key here to pass through state
class AppState(BaseModel):
    user_prompt: str
    api_key: Optional[str] = None
    plan: Optional[Plan] = None
    task_plan: Optional[TaskPlan] = None
    current_step_idx: int = 0
    status: str = "PENDING"
    logs: List[str] = Field(default_factory=list)