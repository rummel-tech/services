"""Base module interface for all Artemis modules."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ModuleConfig(BaseModel):
    """Base configuration for all modules."""

    name: str
    enabled: bool = True
    settings: Dict[str, Any] = {}


class ModuleStatus(BaseModel):
    """Status information for a module."""

    name: str
    enabled: bool
    healthy: bool
    message: Optional[str] = None


class QuickAction(BaseModel):
    """Quick action that can be performed from the dashboard."""

    id: str
    label: str
    action: str
    icon: Optional[str] = None


class ModuleSummary(BaseModel):
    """Summary information for dashboard display."""

    name: str
    enabled: bool
    healthy: bool
    stats: Dict[str, Any] = {}
    recent_items: List[Dict[str, Any]] = []
    quick_actions: List[QuickAction] = []


class BaseModule(ABC):
    """Base class for all Artemis modules.
    
    Each module represents a key area of personal management:
    - Work
    - Fitness
    - Nutrition
    - Entrepreneurship
    - Finance
    - Assets
    
    Modules are integrated to provide a single pane of glass solution.
    """
    
    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the module with configuration.
        
        Args:
            config: Module configuration
        """
        self.config = config
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the module.
        
        This method should set up any required resources,
        connections, or state for the module.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the module.
        
        This method should clean up resources and prepare
        the module for termination.
        """
        pass
    
    @abstractmethod
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the module.
        
        Returns:
            Current module status
        """
        pass
    
    @abstractmethod
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a module-specific action.

        Args:
            action: The action to perform
            data: Action parameters

        Returns:
            Result of the action
        """
        pass

    @abstractmethod
    async def get_summary(self) -> ModuleSummary:
        """Get summary information for dashboard display.

        Returns:
            ModuleSummary with stats, recent items, and quick actions
        """
        pass

    @property
    def name(self) -> str:
        """Get the module name."""
        return self.config.name
    
    @property
    def is_enabled(self) -> bool:
        """Check if the module is enabled."""
        return self.config.enabled
    
    @property
    def is_initialized(self) -> bool:
        """Check if the module is initialized."""
        return self._initialized
