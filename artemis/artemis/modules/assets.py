"""Asset management module for Artemis personal OS."""
from datetime import date, timedelta
from typing import Any, Dict
from uuid import uuid4
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction


class AssetsModule(BaseModule):
    """Module for managing physical assets like home, car, and motorcycle.
    
    Features:
    - Asset tracking (home, car, motorcycle, etc.)
    - Maintenance scheduling
    - Service history
    - Document storage
    - Insurance tracking
    """
    
    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the assets module."""
        super().__init__(config)
        self.assets: Dict[str, Any] = {}
        self.maintenance: Dict[str, Any] = {}
        self.documents: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize the assets module."""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the assets module."""
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the assets module."""
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            message=f"Managing {len(self.assets)} assets with {len(self.maintenance)} maintenance records"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assets module actions."""
        if action == "add_asset":
            asset_id = data.get("id", f"asset_{uuid4().hex[:8]}")
            self.assets[asset_id] = data
            return {"status": "success", "asset_id": asset_id}
        
        elif action == "log_maintenance":
            maintenance_id = data.get("id", f"maintenance_{uuid4().hex[:8]}")
            self.maintenance[maintenance_id] = data
            return {"status": "success", "maintenance_id": maintenance_id}
        
        elif action == "add_document":
            document_id = data.get("id", f"document_{uuid4().hex[:8]}")
            self.documents[document_id] = data
            return {"status": "success", "document_id": document_id}
        
        elif action == "list_assets":
            return {"assets": list(self.assets.values())}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the assets module."""
        today = date.today()
        upcoming_date = (today + timedelta(days=30)).isoformat()

        upcoming_maintenance = sum(
            1 for m in self.maintenance.values()
            if m.get("scheduled_date", "") <= upcoming_date and m.get("status") != "completed"
        )

        recent_assets = sorted(
            self.assets.values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )[:5]

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            stats={
                "asset_count": len(self.assets),
                "upcoming_maintenance": upcoming_maintenance,
                "documents_count": len(self.documents),
            },
            recent_items=[{"type": "asset", **a} for a in recent_assets],
            quick_actions=[
                QuickAction(id="add_asset", label="Add Asset", action="add_asset", icon="home"),
                QuickAction(id="log_maintenance", label="Log Maintenance", action="log_maintenance", icon="build"),
            ],
        )
