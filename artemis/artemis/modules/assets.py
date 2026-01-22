"""Asset management module for Artemis personal OS."""
from datetime import date, timedelta
from typing import Any, Dict
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction
from artemis.core.client import ServiceClient
from artemis.core.settings import settings


class AssetsModule(BaseModule):
    """Module for managing physical assets like home, car, and motorcycle.

    Proxies requests to home-manager and vehicle-manager backend services.

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
        self.home_client = ServiceClient(settings.services.home_manager_url)
        self.vehicle_client = ServiceClient(settings.services.vehicle_manager_url)

    async def initialize(self) -> None:
        """Initialize the assets module."""
        # Check both backend services
        home_healthy = await self.home_client.health_check()
        vehicle_healthy = await self.vehicle_client.health_check()
        self._initialized = home_healthy or vehicle_healthy

    async def shutdown(self) -> None:
        """Shutdown the assets module."""
        await self.home_client.close()
        await self.vehicle_client.close()
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the assets module."""
        user_id = settings.default_user_id

        home_healthy = await self.home_client.health_check()
        vehicle_healthy = await self.vehicle_client.health_check()

        try:
            # Get counts from both services
            home_assets = await self.home_client.get(f"/assets/{user_id}")
            home_count = len(home_assets) if isinstance(home_assets, list) else 0

            vehicles = await self.vehicle_client.get(f"/vehicles/{user_id}")
            vehicle_count = len(vehicles) if isinstance(vehicles, list) else 0

            total_assets = home_count + vehicle_count
        except:
            total_assets = 0

        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=home_healthy and vehicle_healthy,
            message=f"Managing {total_assets} assets ({home_count} home, {vehicle_count} vehicles)"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assets module actions."""
        user_id = data.get("user_id", settings.default_user_id)
        asset_type = data.get("asset_type", "home")

        if action == "add_asset":
            # Route to appropriate service based on asset_type
            if asset_type == "vehicle":
                # Create vehicle via vehicle-manager
                vehicle_data = {
                    "user_id": user_id,
                    "name": data.get("name", "Vehicle"),
                    "description": data.get("description"),
                    "asset_type": "vehicle",
                    "category": data.get("category", "car"),
                    "manufacturer": data.get("manufacturer"),
                    "model_number": data.get("model"),
                    "vin": data.get("vin"),
                    "purchase_date": data.get("purchase_date"),
                    "purchase_price": data.get("purchase_price"),
                    "condition": data.get("condition", "good"),
                    "location": data.get("location"),
                    "notes": data.get("notes"),
                }
                result = await self.vehicle_client.post("/vehicles", json=vehicle_data)
                return {"status": "success", "asset": result}
            else:
                # Create home asset via home-manager
                asset_data = {
                    "user_id": user_id,
                    "name": data.get("name", "Asset"),
                    "description": data.get("description"),
                    "asset_type": asset_type,
                    "category": data.get("category"),
                    "manufacturer": data.get("manufacturer"),
                    "model_number": data.get("model"),
                    "serial_number": data.get("serial_number"),
                    "purchase_date": data.get("purchase_date"),
                    "purchase_price": data.get("purchase_price"),
                    "condition": data.get("condition", "good"),
                    "location": data.get("location"),
                    "notes": data.get("notes"),
                }
                result = await self.home_client.post("/assets", json=asset_data)
                return {"status": "success", "asset": result}

        elif action == "list_assets":
            # Get assets from both services
            home_assets = await self.home_client.get(f"/assets/{user_id}")
            vehicles = await self.vehicle_client.get(f"/vehicles/{user_id}")

            all_assets = []
            if isinstance(home_assets, list):
                all_assets.extend(home_assets)
            if isinstance(vehicles, list):
                all_assets.extend(vehicles)

            return {"assets": all_assets}

        elif action == "list_vehicles":
            # Get only vehicles
            vehicles = await self.vehicle_client.get(f"/vehicles/{user_id}")
            return {"vehicles": vehicles}

        elif action == "list_home_assets":
            # Get only home assets
            assets = await self.home_client.get(f"/assets/{user_id}")
            return {"assets": assets}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the assets module."""
        user_id = settings.default_user_id

        home_healthy = await self.home_client.health_check()
        vehicle_healthy = await self.vehicle_client.health_check()
        healthy = home_healthy and vehicle_healthy

        try:
            # Get assets from both services
            home_assets = await self.home_client.get(f"/assets/{user_id}")
            home_count = len(home_assets) if isinstance(home_assets, list) else 0

            vehicles = await self.vehicle_client.get(f"/vehicles/{user_id}")
            vehicle_count = len(vehicles) if isinstance(vehicles, list) else 0

            # Combine and get recent assets
            all_assets = []
            if isinstance(home_assets, list):
                all_assets.extend(home_assets)
            if isinstance(vehicles, list):
                all_assets.extend(vehicles)

            # Sort by created_at and take top 5
            recent_assets = sorted(
                all_assets,
                key=lambda x: x.get("created_at", ""),
                reverse=True
            )[:5]

        except:
            home_count = 0
            vehicle_count = 0
            recent_assets = []

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=healthy,
            stats={
                "total_assets": home_count + vehicle_count,
                "home_assets": home_count,
                "vehicles": vehicle_count,
            },
            recent_items=[{"type": "asset", **a} for a in recent_assets],
            quick_actions=[
                QuickAction(id="add_asset", label="Add Asset", action="add_asset", icon="home"),
                QuickAction(id="list_assets", label="List All Assets", action="list_assets", icon="list"),
            ],
        )
