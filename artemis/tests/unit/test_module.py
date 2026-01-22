"""Tests for core module functionality."""
import pytest
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus
from typing import Any, Dict


class TestModule(BaseModule):
    """Test implementation of BaseModule."""
    
    async def initialize(self) -> None:
        """Initialize test module."""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown test module."""
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get status of test module."""
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            message="Test module"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle test action."""
        return {"action": action, "data": data}


@pytest.mark.asyncio
async def test_module_initialization() -> None:
    """Test module initialization."""
    config = ModuleConfig(name="test")
    module = TestModule(config)
    
    assert not module.is_initialized
    await module.initialize()
    assert module.is_initialized


@pytest.mark.asyncio
async def test_module_shutdown() -> None:
    """Test module shutdown."""
    config = ModuleConfig(name="test")
    module = TestModule(config)
    
    await module.initialize()
    assert module.is_initialized
    
    await module.shutdown()
    assert not module.is_initialized


@pytest.mark.asyncio
async def test_module_status() -> None:
    """Test module status."""
    config = ModuleConfig(name="test")
    module = TestModule(config)
    
    await module.initialize()
    status = await module.get_status()
    
    assert status.name == "test"
    assert status.enabled is True
    assert status.healthy is True


@pytest.mark.asyncio
async def test_module_action() -> None:
    """Test module action handling."""
    config = ModuleConfig(name="test")
    module = TestModule(config)
    
    result = await module.handle_action("test_action", {"key": "value"})
    
    assert result["action"] == "test_action"
    assert result["data"]["key"] == "value"


def test_module_config() -> None:
    """Test module configuration."""
    config = ModuleConfig(name="test", enabled=True, settings={"key": "value"})
    
    assert config.name == "test"
    assert config.enabled is True
    assert config.settings["key"] == "value"


def test_module_properties() -> None:
    """Test module properties."""
    config = ModuleConfig(name="test_module", enabled=False)
    module = TestModule(config)
    
    assert module.name == "test_module"
    assert not module.is_enabled
    assert not module.is_initialized
