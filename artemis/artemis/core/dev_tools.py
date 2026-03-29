"""Platform self-management tools — GitHub API integration for tracking development."""
import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("artemis.dev_tools")

GITHUB_API = "https://api.github.com"

VALID_REPOS = ["services", "apps", "infrastructure"]
VALID_SERVICES = [
    "auth", "workout-planner", "meal-planner",
    "home-manager", "vehicle-manager", "artemis",
]


class DevTools:
    """GitHub-backed tools for Artemis platform self-management."""

    def __init__(self, token: str, org: str) -> None:
        self._token = token
        self._org = org
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def list_issues(self, repo: str, state: str = "open") -> Dict[str, Any]:
        url = f"{GITHUB_API}/repos/{self._org}/{repo}/issues"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    url,
                    headers=self._headers,
                    params={"state": state, "per_page": 20},
                )
                r.raise_for_status()
                issues = [i for i in r.json() if "pull_request" not in i]
                return {
                    "repo": f"{self._org}/{repo}",
                    "count": len(issues),
                    "issues": [
                        {
                            "number": i["number"],
                            "title": i["title"],
                            "state": i["state"],
                            "labels": [lb["name"] for lb in i.get("labels", [])],
                            "created_at": i["created_at"][:10],
                            "url": i["html_url"],
                        }
                        for i in issues
                    ],
                }
        except Exception as e:
            log.warning("list_issues failed: %s", e)
            return {"error": str(e)}

    async def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        url = f"{GITHUB_API}/repos/{self._org}/{repo}/issues"
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, headers=self._headers, json=payload)
                r.raise_for_status()
                issue = r.json()
                return {
                    "number": issue["number"],
                    "title": issue["title"],
                    "url": issue["html_url"],
                    "state": issue["state"],
                }
        except Exception as e:
            log.warning("create_issue failed: %s", e)
            return {"error": str(e)}

    async def get_deployment_status(self, service: str) -> Dict[str, Any]:
        url = (
            f"{GITHUB_API}/repos/{self._org}/services"
            "/actions/workflows/deploy-services.yml/runs"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    url, headers=self._headers, params={"per_page": 10}
                )
                r.raise_for_status()
                runs = r.json().get("workflow_runs", [])
                relevant = [
                    run for run in runs
                    if service in (run.get("display_title") or run.get("name") or "")
                ] or runs[:3]
                return {
                    "service": service,
                    "recent_runs": [
                        {
                            "status": run["status"],
                            "conclusion": run.get("conclusion"),
                            "created_at": run["created_at"][:16].replace("T", " "),
                            "url": run["html_url"],
                        }
                        for run in relevant[:3]
                    ],
                }
        except Exception as e:
            log.warning("deployment_status failed: %s", e)
            return {"error": str(e)}

    async def trigger_deployment(
        self, service: str, environment: str = "staging"
    ) -> Dict[str, Any]:
        url = (
            f"{GITHUB_API}/repos/{self._org}/services"
            "/actions/workflows/deploy-services.yml/dispatches"
        )
        payload = {
            "ref": "main",
            "inputs": {"service": service, "environment": environment},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, headers=self._headers, json=payload)
                if r.status_code == 204:
                    return {
                        "success": True,
                        "message": f"Deployment of {service} to {environment} triggered.",
                    }
                r.raise_for_status()
                return {"success": True}
        except Exception as e:
            log.warning("trigger_deployment failed: %s", e)
            return {"error": str(e)}


def build_platform_tools() -> List[Dict]:
    """Return Claude tool definitions for platform self-management."""
    return [
        {
            "name": "platform__list_issues",
            "description": (
                "List GitHub issues for an Artemis repository. "
                "Use to check open bugs, feature requests, and in-progress work."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "enum": VALID_REPOS,
                        "description": (
                            "'services' for backend modules, "
                            "'apps' for the mobile app, "
                            "'infrastructure' for Terraform/deployment"
                        ),
                    },
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "Filter by state (default: open)",
                    },
                },
                "required": ["repo"],
            },
        },
        {
            "name": "platform__create_issue",
            "description": (
                "Create a GitHub issue to track a feature, bug, or improvement. "
                "Offer to do this whenever a user mentions something that should be tracked."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "enum": VALID_REPOS,
                        "description": "Target repository",
                    },
                    "title": {
                        "type": "string",
                        "description": "Concise issue title",
                    },
                    "body": {
                        "type": "string",
                        "description": "Detailed description in markdown",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Labels such as 'bug', 'enhancement', "
                            "'module:home-manager', 'voice', 'ux'"
                        ),
                    },
                },
                "required": ["repo", "title", "body"],
            },
        },
        {
            "name": "platform__deployment_status",
            "description": "Check the latest CI/CD deployment status for an Artemis service.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "enum": VALID_SERVICES,
                        "description": "Service to check",
                    },
                },
                "required": ["service"],
            },
        },
        {
            "name": "platform__trigger_deployment",
            "description": (
                "Trigger a deployment via GitHub Actions. "
                "Always confirm with the user before triggering production."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "enum": VALID_SERVICES,
                        "description": "Service to deploy",
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["staging", "production"],
                        "description": "Target environment",
                    },
                },
                "required": ["service", "environment"],
            },
        },
    ]
