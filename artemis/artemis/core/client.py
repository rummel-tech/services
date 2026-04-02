"""HTTP client utilities for backend service communication."""
import logging
import httpx
from typing import Any, Dict, Optional
from fastapi import HTTPException

log = logging.getLogger(__name__)


class ServiceClient:
    """HTTP client for communicating with backend services."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Initialize service client.

        Args:
            base_url: Base URL of the backend service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request to the service.

        Args:
            path: API path (e.g., "/tasks/user123")
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            HTTPException: If request fails
        """
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Backend service error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Backend service unavailable: {str(e)}"
            )

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a POST request to the service.

        Args:
            path: API path
            data: Form data
            json: JSON data

        Returns:
            Response JSON data

        Raises:
            HTTPException: If request fails
        """
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.post(url, data=data, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Backend service error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Backend service unavailable: {str(e)}"
            )

    async def put(self, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
        """Make a PUT request to the service.

        Args:
            path: API path
            json: JSON data

        Returns:
            Response JSON data

        Raises:
            HTTPException: If request fails
        """
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.put(url, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Backend service error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Backend service unavailable: {str(e)}"
            )

    async def delete(self, path: str) -> Optional[Dict[str, Any]]:
        """Make a DELETE request to the service.

        Args:
            path: API path

        Returns:
            Response JSON data if available, None for 204 responses

        Raises:
            HTTPException: If request fails
        """
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.delete(url)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Backend service error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Backend service unavailable: {str(e)}"
            )

    async def health_check(self) -> bool:
        """Check if the backend service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            log.warning("health_check_failed", extra={"base_url": self.base_url, "error": str(e)})
            return False
