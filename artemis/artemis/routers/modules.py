"""Module registry endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from artemis.core.auth import validate_token
from artemis.core.registry import registry

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("")
async def list_modules(token: dict = Depends(validate_token)) -> List[Dict[str, Any]]:
    """List all registered modules with their health status."""
    return [
        {
            "id": m.id,
            "healthy": m.healthy,
            "enabled": m.enabled,
            "last_checked": m.last_checked.isoformat() if m.last_checked else None,
            "error": m.error,
            "name": m.manifest.get("module", {}).get("name") if m.manifest else None,
            "version": m.manifest.get("module", {}).get("version") if m.manifest else None,
        }
        for m in registry.list_modules()
    ]


@router.get("/{module_id}")
async def get_module(module_id: str, token: dict = Depends(validate_token)) -> Dict[str, Any]:
    """Get full details for a specific module."""
    mod = registry.get(module_id)
    if not mod:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not registered")
    return mod.to_dict()


@router.get("/{module_id}/manifest")
async def get_module_manifest(module_id: str, token: dict = Depends(validate_token)) -> Dict[str, Any]:
    """Return the cached manifest for a module."""
    mod = registry.get(module_id)
    if not mod:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not registered")
    if not mod.manifest:
        raise HTTPException(status_code=503, detail=f"Manifest for '{module_id}' not available")
    return mod.manifest
