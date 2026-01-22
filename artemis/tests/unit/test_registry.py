"""Tests for module registry."""
import pytest
from artemis.core.registry import ModuleRegistry
from artemis.core.module import ModuleConfig
from artemis.modules.work import WorkModule


@pytest.mark.asyncio
async def test_registry_register_module() -> None:
    """Test registering a module."""
    registry = ModuleRegistry()
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    
    registry.register(module)
    
    assert "work" in registry.list_modules()
    assert registry.get("work") == module


@pytest.mark.asyncio
async def test_registry_unregister_module() -> None:
    """Test unregistering a module."""
    registry = ModuleRegistry()
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    
    registry.register(module)
    assert "work" in registry.list_modules()
    
    registry.unregister("work")
    assert "work" not in registry.list_modules()


@pytest.mark.asyncio
async def test_registry_initialize_all() -> None:
    """Test initializing all modules."""
    registry = ModuleRegistry()
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    
    registry.register(module)
    
    assert not module.is_initialized
    await registry.initialize_all()
    assert module.is_initialized


@pytest.mark.asyncio
async def test_registry_shutdown_all() -> None:
    """Test shutting down all modules."""
    registry = ModuleRegistry()
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    
    registry.register(module)
    await registry.initialize_all()
    
    assert module.is_initialized
    await registry.shutdown_all()
    assert not module.is_initialized


@pytest.mark.asyncio
async def test_registry_get_all_status() -> None:
    """Test getting status of all modules."""
    registry = ModuleRegistry()
    config = ModuleConfig(name="work")
    module = WorkModule(config)
    
    registry.register(module)
    await registry.initialize_all()
    
    statuses = await registry.get_all_status()
    
    assert len(statuses) == 1
    assert statuses[0].name == "work"
    assert statuses[0].healthy is True
