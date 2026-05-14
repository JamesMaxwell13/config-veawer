from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
import re
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class GitLabAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitLabNotFoundError(GitLabAPIError):
    pass


class GitLabAuthError(GitLabAPIError):
    pass


@dataclass(frozen=True)
class GitLabFileMetadata:
    file_path: str
    last_commit_id: str
    blob_id: str = ""
    commit_id: str = ""


class GitLabPathBuilder:
    DEFAULT_ROOT_PATH = "configs"
    DEFAULT_PATTERN = "{root_path}/{site_slug}/{location_slug}/{rack_slug}/{device_name}.yaml"
    FALLBACKS = {
        "site": "no-site",
        "site_slug": "no-site",
        "location": "no-location",
        "location_slug": "no-location",
        "rack": "no-rack",
        "rack_slug": "no-rack",
        "role": "no-role",
        "role_slug": "no-role",
        "platform": "no-platform",
        "manufacturer": "no-manufacturer",
    }
    PLACEHOLDERS = {
        "root_path",
        "site",
        "site_slug",
        "location",
        "location_slug",
        "rack",
        "rack_slug",
        "device",
        "device_name",
        "device_id",
        "role",
        "role_slug",
        "platform",
        "manufacturer",
    }

    @classmethod
    def normalize_segment(cls, value: Any, fallback: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            raw = fallback
        raw = raw.replace("\\", "/").split("/")[-1]
        raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-_").lower()
        if not raw or raw in {".", ".."}:
            raw = fallback
        return raw

    @classmethod
    def _first_attr(cls, obj: Any, *names: str) -> Any:
        if obj is None:
            return None
        for name in names:
            value = getattr(obj, name, None)
            if value:
                return value
        return None

    @classmethod
    def values_for_device(cls, device: Any, root_path: str | None = None) -> dict[str, str]:
        site = getattr(device, "site", None)
        location = getattr(device, "location", None)
        rack = getattr(device, "rack", None)
        role = getattr(device, "role", None)
        platform = getattr(device, "platform", None)
        device_type = getattr(device, "device_type", None)
        manufacturer = getattr(device_type, "manufacturer", None)

        root = cls.normalize_path(root_path or cls.DEFAULT_ROOT_PATH)
        values = {
            "root_path": root,
            "site": cls.normalize_segment(cls._first_attr(site, "name", "slug"), cls.FALLBACKS["site"]),
            "site_slug": cls.normalize_segment(cls._first_attr(site, "slug", "name"), cls.FALLBACKS["site_slug"]),
            "location": cls.normalize_segment(cls._first_attr(location, "name", "slug"), cls.FALLBACKS["location"]),
            "location_slug": cls.normalize_segment(cls._first_attr(location, "slug", "name"), cls.FALLBACKS["location_slug"]),
            "rack": cls.normalize_segment(cls._first_attr(rack, "name", "slug"), cls.FALLBACKS["rack"]),
            "rack_slug": cls.normalize_segment(cls._first_attr(rack, "slug", "name"), cls.FALLBACKS["rack_slug"]),
            "device": cls.normalize_segment(getattr(device, "name", None), "device"),
            "device_name": cls.normalize_segment(getattr(device, "name", None), "device"),
            "device_id": cls.normalize_segment(getattr(device, "pk", None), "device"),
            "role": cls.normalize_segment(cls._first_attr(role, "name", "slug"), cls.FALLBACKS["role"]),
            "role_slug": cls.normalize_segment(cls._first_attr(role, "slug", "name"), cls.FALLBACKS["role_slug"]),
            "platform": cls.normalize_segment(cls._first_attr(platform, "slug", "name"), cls.FALLBACKS["platform"]),
            "manufacturer": cls.normalize_segment(cls._first_attr(manufacturer, "slug", "name"), cls.FALLBACKS["manufacturer"]),
        }
        return values

    @classmethod
    def normalize_path(cls, value: str) -> str:
        parts = []
        for raw_part in str(value or "").split("/"):
            part = cls.normalize_segment(raw_part, "")
            if part:
                parts.append(part)
        return "/".join(parts) or cls.DEFAULT_ROOT_PATH

    @classmethod
    def build(cls, device: Any, root_path: str | None = None, pattern: str | None = None) -> str:
        template = pattern or cls.DEFAULT_PATTERN
        values = cls.values_for_device(device, root_path=root_path)

        def replace(match: re.Match) -> str:
            name = match.group(1)
            if name not in cls.PLACEHOLDERS:
                return cls.normalize_segment("", "unknown")
            return values.get(name) or cls.normalize_segment("", cls.FALLBACKS.get(name, "unknown"))

        rendered = re.sub(r"{([A-Za-z_][A-Za-z0-9_]*)}", replace, template)
        rendered = cls.normalize_path(rendered)
        if not rendered.endswith(".yaml"):
            rendered = f"{rendered}.yaml"
        return rendered


class GitLabClient:
    def __init__(self, gitlab_url: str, access_token: str, timeout: int = 20):
        self.gitlab_url = gitlab_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    @staticmethod
    def _quote_path(value: str) -> str:
        return quote(value, safe="")

    def _project_url(self, project_id: str, suffix: str, query: dict[str, str] | None = None) -> str:
        encoded_project = self._quote_path(project_id)
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project}{suffix}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    def _request(
        self,
        method: str,
        project_id: str,
        suffix: str,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        expect_json: bool = False,
    ) -> Any:
        data = None
        headers = {
            "PRIVATE-TOKEN": self.access_token,
            "Accept": "application/json",
            "User-Agent": "netbox-config-weaver",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self._project_url(project_id, suffix, query=query),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            message = self._read_error(exc)
            if exc.code == 404:
                raise GitLabNotFoundError(message, status_code=exc.code) from exc
            if exc.code in {401, 403}:
                raise GitLabAuthError(message, status_code=exc.code) from exc
            raise GitLabAPIError(message, status_code=exc.code) from exc
        except (URLError, socket.timeout) as exc:
            raise GitLabAPIError(f"GitLab network error: {exc}") from exc

        if "application/json" in content_type:
            try:
                return json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise GitLabAPIError("GitLab returned invalid JSON from the API.") from exc

        text = body.decode("utf-8", errors="replace")
        if expect_json:
            raise GitLabAPIError(self._unexpected_response_message(text, content_type))
        return text

    @classmethod
    def _read_error(cls, exc: HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if body:
            try:
                parsed = json.loads(body)
                message = parsed.get("message") or parsed.get("error") or body
                return str(message)
            except json.JSONDecodeError:
                return cls._unexpected_response_message(body, exc.headers.get("Content-Type", ""))
        return f"GitLab API error HTTP {exc.code}"

    @staticmethod
    def _plain_text(value: str, max_length: int = 500) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_length:
            return f"{text[:max_length].rstrip()}..."
        return text

    @classmethod
    def _unexpected_response_message(cls, body: str, content_type: str = "") -> str:
        lowered = body.lower()
        if "challenges.cloudflare.com" in lowered or "cf_chl" in lowered or "just a moment" in lowered:
            return (
                "GitLab returned a Cloudflare challenge instead of an API response. "
                "Check that gitlab_url is the GitLab base URL, the token can access the project API, "
                "and the GitLab instance allows server-side API requests."
            )
        if "/users/sign_in" in lowered or "sign in" in lowered:
            return (
                "GitLab returned an HTML sign-in page instead of an API response. "
                "Check gitlab_url, project_id, and access token permissions."
            )
        text = cls._plain_text(body)
        if text:
            return f"GitLab returned a non-API response ({content_type or 'unknown content type'}): {text}"
        return f"GitLab returned a non-API response ({content_type or 'unknown content type'})."

    def get_raw_file(self, project_id: str, file_path: str, ref: str) -> str:
        suffix = f"/repository/files/{self._quote_path(file_path)}/raw"
        return self._request("GET", project_id, suffix, query={"ref": ref})

    def get_file_metadata(self, project_id: str, file_path: str, ref: str) -> GitLabFileMetadata:
        suffix = f"/repository/files/{self._quote_path(file_path)}"
        data = self._request("GET", project_id, suffix, query={"ref": ref}, expect_json=True)
        return GitLabFileMetadata(
            file_path=data.get("file_path", file_path),
            last_commit_id=data.get("last_commit_id", ""),
            blob_id=data.get("blob_id", ""),
            commit_id=data.get("commit_id", ""),
        )

    def create_file(
        self,
        project_id: str,
        file_path: str,
        branch: str,
        content: str,
        commit_message: str,
    ) -> dict[str, Any]:
        suffix = f"/repository/files/{self._quote_path(file_path)}"
        return self._request(
            "POST",
            project_id,
            suffix,
            payload={"branch": branch, "content": content, "commit_message": commit_message},
            expect_json=True,
        )

    def update_file(
        self,
        project_id: str,
        file_path: str,
        branch: str,
        content: str,
        commit_message: str,
        last_commit_id: str | None = None,
    ) -> dict[str, Any]:
        suffix = f"/repository/files/{self._quote_path(file_path)}"
        payload = {"branch": branch, "content": content, "commit_message": commit_message}
        if last_commit_id:
            payload["last_commit_id"] = last_commit_id
        return self._request("PUT", project_id, suffix, payload=payload, expect_json=True)

    def test_connection(self, project_id: str, branch: str) -> bool:
        self._request("GET", project_id, "/repository/branches/" + self._quote_path(branch), expect_json=True)
        return True
