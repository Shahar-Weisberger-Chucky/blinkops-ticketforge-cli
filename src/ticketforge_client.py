import base64
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://integrations-assignment-ticketforge.vercel.app"
VALID_STAGES = {"open", "in_progress", "review", "closed"}


def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _parse_ratelimit_reset(reset_value: Optional[str]) -> Optional[float]:
    if not reset_value:
        return None
    try:
        dt = datetime.fromisoformat(reset_value.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


@dataclass
class TicketForgeConfig:
    base_url: str
    username: str
    password: str


class TicketForgeClient:
    def __init__(self, config: TicketForgeConfig, timeout_s: int = 15) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": _basic_auth_header(config.username, config.password),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
    ) -> Any:
        url = self.config.base_url.rstrip("/") + path

        for _ in range(3):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout_s,
                )
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Network error: {e}")

            if resp.status_code == 429:
                reset_ts = _parse_ratelimit_reset(resp.headers.get("x-ratelimit-reset"))
                if reset_ts:
                    sleep_s = max(0.0, reset_ts - time.time()) + 1.0
                    time.sleep(min(sleep_s, 30.0))
                    continue
                time.sleep(2.0)
                continue

            if 200 <= resp.status_code < 300:
                if not resp.content:
                    return None
                return resp.json()

            try:
                err = resp.json()
            except Exception:
                err = {"error": resp.text}

            raise RuntimeError(f"API error {resp.status_code}: {err}")

        raise RuntimeError("Rate limit exceeded. Please retry.")

    def health_check(self) -> bool:
        self.list_workitems(limit=1)
        return True

    def list_workitems(
        self,
        limit: int = 5,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = self._request("GET", "/api/tforge/workitems/mine", params=params)
        return data.get("workitems", []), data.get("pagination", {})

    def list_all_workitems(
        self,
        batch_size: int = 50,
        max_batches: int = 50,
    ) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        for _ in range(max_batches):
            items, pagination = self.list_workitems(limit=batch_size, cursor=cursor)
            all_items.extend(items)

            if not pagination.get("hasMore"):
                break

            cursor = pagination.get("nextCursor")
            if not cursor:
                break

        return all_items

    def create_workitem(
        self,
        title: str,
        description: str,
        depends_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"title": title, "description": description}
        if depends_on:
            payload["dependsOn"] = depends_on

        data = self._request("POST", "/api/tforge/workitem/publish", json_body=payload)
        return data.get("workitem", data)

    def get_workitem_deep(self, ref: str) -> Dict[str, Any]:
        data = self._request("GET", f"/api/tforge/workitem/{ref}", params={"view": "deep"})
        if isinstance(data, dict) and "workitem" in data and isinstance(data["workitem"], dict):
            return data["workitem"]
        return data

    def update_workitem(
        self,
        ref: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        stage: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        custom_fields: Optional[Dict[str, str]] = None,
    ) -> Any:
        current = self.get_workitem_deep(ref)

        # Build a "full" payload from current (because PUT likely validates required fields)
        payload: Dict[str, Any] = {
            "title": current.get("title") or "",
            "description": current.get("description"),
            "stage": current.get("stage"),
            "dependsOn": current.get("dependsOn") or [],
            "customFields": current.get("customFields") or {},
        }

        # Apply overrides
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if depends_on is not None:
            payload["dependsOn"] = depends_on
        if custom_fields is not None:
            payload["customFields"] = custom_fields

        # Stage handling: must be valid
        if stage is not None:
            if stage not in VALID_STAGES:
                raise RuntimeError("Invalid stage. Use: open | in_progress | review | closed")
            payload["stage"] = stage

        # Validate required fields before sending
        if not isinstance(payload.get("title"), str) or not payload["title"].strip():
            raise RuntimeError("Title is required and must be non-empty")
        if payload.get("stage") not in VALID_STAGES:
            raise RuntimeError("Stage is required and must be one of: open, in_progress, review, closed")

        return self._request("PUT", f"/api/tforge/workitem/{ref}", json_body=payload)
