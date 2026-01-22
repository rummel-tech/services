"""Module registry for managing all Artemis modules."""
from typing import Dict, List, Optional
from artemis.core.module import BaseModule, ModuleStatus


class ModuleRegistry:
    """Central registry for all Artemis modules.
    
    Provides a single pane of glass for module management
    and integration across the personal OS.
    """
    
    def __init__(self) -> None:
        """Initialize the module registry."""
        self._modules: Dict[str, BaseModule] = {}
    
    def register(self, module: BaseModule) -> None:
        """Register a module with the registry.
        
        Args:
            module: Module to register
        """
        self._modules[module.name] = module
    
    def unregister(self, name: str) -> None:
        """Unregister a module from the registry.
        
        Args:
            name: Name of the module to unregister
        """
        if name in self._modules:
            del self._modules[name]
    
    def get(self, name: str) -> Optional[BaseModule]:
        """Get a module by name.
        
        Args:
            name: Name of the module
            
        Returns:
            The module if found, None otherwise
        """
        return self._modules.get(name)
    
    def list_modules(self) -> List[str]:
        """List all registered module names.
        
        Returns:
            List of module names
        """
        return list(self._modules.keys())
    
    async def initialize_all(self) -> None:
        """Initialize all registered modules."""
        for module in self._modules.values():
            if module.is_enabled:
                await module.initialize()
    
    async def shutdown_all(self) -> None:
        """Shutdown all registered modules."""
        for module in self._modules.values():
            if module.is_initialized:
                await module.shutdown()
    
    async def get_all_status(self) -> List[ModuleStatus]:
        """Get status of all registered modules.
        
        Returns:
            List of module statuses
        """
        statuses = []
        for module in self._modules.values():
            status = await module.get_status()
            statuses.append(status)
        return statuses


# Global module registry instance
registry = ModuleRegistry()
