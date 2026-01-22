"""Tests for Work module."""
import pytest
from artemis.core.module import ModuleConfig
from artemis.modules.work import WorkModule


@pytest.mark.asyncio
async def test_work_module_create_task() -> None:
    """Test creating a task."""
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    await module.initialize()
    
    result = await module.handle_action("create_task", {
        "id": "task_1",
        "title": "Test task",
        "description": "Test description"
    })
    
    assert result["status"] == "success"
    assert result["task_id"] == "task_1"
    assert "task_1" in module.tasks


@pytest.mark.asyncio
async def test_work_module_list_tasks() -> None:
    """Test listing tasks."""
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    await module.initialize()
    
    await module.handle_action("create_task", {"id": "task_1", "title": "Task 1"})
    await module.handle_action("create_task", {"id": "task_2", "title": "Task 2"})
    
    result = await module.handle_action("list_tasks", {})
    
    assert len(result["tasks"]) == 2


@pytest.mark.asyncio
async def test_work_module_create_project() -> None:
    """Test creating a project."""
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    await module.initialize()
    
    result = await module.handle_action("create_project", {
        "id": "project_1",
        "name": "Test Project"
    })
    
    assert result["status"] == "success"
    assert result["project_id"] == "project_1"
