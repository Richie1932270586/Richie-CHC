from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


HOST = env("EDITOR_API_HOST", "127.0.0.1")
PORT = int(env("EDITOR_API_PORT", "8787"))
GITHUB_TOKEN = env("GITHUB_TOKEN")
GITHUB_OWNER = env("GITHUB_OWNER")
GITHUB_REPO = env("GITHUB_REPO")
GITHUB_BRANCH = env("GITHUB_BRANCH", "main")
CONTENT_PATH = env("EDITOR_CONTENT_PATH", "data/site-content.json")
EDITOR_PASSWORD = env("EDITOR_PASSWORD")
EDITOR_PASSWORD_HASH = env("EDITOR_PASSWORD_HASH")
EDITOR_TOKEN_SECRET = env("EDITOR_TOKEN_SECRET")
EDITOR_TOKEN_TTL_SECONDS = int(env("EDITOR_TOKEN_TTL_SECONDS", "43200"))
ALLOWED_ORIGINS = [origin.strip() for origin in env("EDITOR_ALLOWED_ORIGINS", "*").split(",") if origin.strip()]


def require_config() -> None:
    missing = []
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not GITHUB_OWNER:
        missing.append("GITHUB_OWNER")
    if not GITHUB_REPO:
        missing.append("GITHUB_REPO")
    if not (EDITOR_PASSWORD or EDITOR_PASSWORD_HASH):
        missing.append("EDITOR_PASSWORD or EDITOR_PASSWORD_HASH")
    if not EDITOR_TOKEN_SECRET:
        missing.append("EDITOR_TOKEN_SECRET")

    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_is_valid(password: str) -> bool:
    if EDITOR_PASSWORD_HASH:
        return hmac.compare_digest(sha256_hex(password), EDITOR_PASSWORD_HASH)
    return hmac.compare_digest(password, EDITOR_PASSWORD)


def normalize_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_project(project: dict) -> dict:
    tags = project.get("tags") if isinstance(project.get("tags"), list) else []
    return {
        "id": normalize_text(project.get("id")),
        "name": normalize_text(project.get("name")),
        "summary": normalize_text(project.get("summary")),
        "focus": normalize_text(project.get("focus") or project.get("summary")),
        "tags": [normalize_text(tag) for tag in tags if normalize_text(tag)][:4],
        "link": normalize_text(project.get("link")),
        "meta": normalize_text(project.get("meta")),
        "featured": bool(project.get("featured")),
        "custom": bool(project.get("custom")),
    }


def normalize_experience(experience: dict) -> dict:
    return {
        "id": normalize_text(experience.get("id")),
        "time": normalize_text(experience.get("time")),
        "title": normalize_text(experience.get("title")),
        "summary": normalize_text(experience.get("summary")),
        "custom": bool(experience.get("custom")),
    }


def normalize_content(content: dict) -> dict:
    projects = content.get("projects") if isinstance(content.get("projects"), list) else []
    experiences = content.get("experiences") if isinstance(content.get("experiences"), list) else []
    return {
        "projects": [project for project in (normalize_project(item) for item in projects) if project["id"] and project["name"]],
        "experiences": [experience for experience in (normalize_experience(item) for item in experiences) if experience["id"] and experience["title"]],
    }


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_session_token() -> tuple[str, int]:
    expires_at = int(time.time()) + EDITOR_TOKEN_TTL_SECONDS
    payload = b64url_encode(json.dumps({"exp": expires_at}, separators=(",", ":")).encode("utf-8"))
    signature = b64url_encode(hmac.new(EDITOR_TOKEN_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest())
    return payload + "." + signature, expires_at


def validate_session_token(token: str) -> bool:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError:
        return False

    expected_signature = b64url_encode(
        hmac.new(EDITOR_TOKEN_SECRET.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature_part, expected_signature):
        return False

    try:
        payload = json.loads(b64url_decode(payload_part).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return False

    return int(payload.get("exp", 0)) > int(time.time())


def github_request(method: str, path: str, body: dict | None = None) -> dict:
    url = "https://api.github.com" + path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "portfolio-editor-sync",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("message") or "GitHub request failed"
        except Exception:
            message = "GitHub request failed"
        raise RuntimeError(message) from error


def read_repo_content() -> tuple[dict, str]:
    encoded_path = urllib.parse.quote(CONTENT_PATH, safe="/")
    payload = github_request("GET", f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{encoded_path}?ref={urllib.parse.quote(GITHUB_BRANCH, safe='')}")
    raw_content = payload.get("content", "").replace("\n", "")
    decoded = base64.b64decode(raw_content).decode("utf-8")
    return normalize_content(json.loads(decoded)), payload["sha"]


def write_repo_content(content: dict, sha: str, message: str) -> None:
    encoded_path = urllib.parse.quote(CONTENT_PATH, safe="/")
    content_bytes = json.dumps(normalize_content(content), ensure_ascii=False, indent=2).encode("utf-8")
    github_request(
        "PUT",
        f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{encoded_path}",
        {
            "message": message,
            "branch": GITHUB_BRANCH,
            "sha": sha,
            "content": base64.b64encode(content_bytes).decode("utf-8"),
        },
    )


class EditorApiHandler(BaseHTTPRequestHandler):
    server_version = "PortfolioEditorAPI/1.0"

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        return "*" in ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if "*" in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def _send_json(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _require_authorization(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._send_json(401, {"error": "Missing editor token."})
            return False

        token = auth_header.split(" ", 1)[1].strip()
        if not validate_session_token(token):
            self._send_json(401, {"error": "Invalid or expired editor token."})
            return False

        return True

    def _upsert_project(self, project: dict) -> dict:
        next_project = normalize_project(project)
        if not next_project["id"] or not next_project["name"] or not next_project["summary"] or not next_project["link"]:
            raise ValueError("Project id, name, summary, and link are required.")

        content, sha = read_repo_content()
        existing_index = next((index for index, item in enumerate(content["projects"]) if item["id"] == next_project["id"]), -1)
        if existing_index >= 0:
            content["projects"][existing_index] = next_project
        else:
            content["projects"].append(next_project)

        write_repo_content(content, sha, f"Update project {next_project['name']} via portfolio editor")
        updated_content, _ = read_repo_content()
        return updated_content

    def _delete_project(self, project_id: str) -> dict:
        content, sha = read_repo_content()
        removed = next((project for project in content["projects"] if project["id"] == project_id), None)
        if not removed:
            raise LookupError("Project not found.")

        content["projects"] = [project for project in content["projects"] if project["id"] != project_id]
        write_repo_content(content, sha, f"Delete project {removed['name']} via portfolio editor")
        updated_content, _ = read_repo_content()
        return updated_content

    def _upsert_experience(self, experience: dict) -> dict:
        next_experience = normalize_experience(experience)
        if not next_experience["id"] or not next_experience["time"] or not next_experience["title"] or not next_experience["summary"]:
            raise ValueError("Experience id, time, title, and summary are required.")

        content, sha = read_repo_content()
        existing_index = next((index for index, item in enumerate(content["experiences"]) if item["id"] == next_experience["id"]), -1)
        if existing_index >= 0:
            content["experiences"][existing_index] = next_experience
        else:
            content["experiences"].append(next_experience)

        write_repo_content(content, sha, f"Update experience {next_experience['title']} via portfolio editor")
        updated_content, _ = read_repo_content()
        return updated_content

    def _delete_experience(self, experience_id: str) -> dict:
        content, sha = read_repo_content()
        removed = next((experience for experience in content["experiences"] if experience["id"] == experience_id), None)
        if not removed:
            raise LookupError("Experience not found.")

        content["experiences"] = [experience for experience in content["experiences"] if experience["id"] != experience_id]
        write_repo_content(content, sha, f"Delete experience {removed['title']} via portfolio editor")
        updated_content, _ = read_repo_content()
        return updated_content

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        if self.path == "/api/health":
            self._send_json(200, {"ok": True, "branch": GITHUB_BRANCH, "contentPath": CONTENT_PATH})
            return

        if self.path == "/api/content":
            try:
                content, _ = read_repo_content()
            except Exception as error:
                self._send_json(500, {"error": str(error)})
                return
            self._send_json(200, {"ok": True, "content": content})
            return

        self._send_json(404, {"error": "Route not found."})

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        try:
            body = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body."})
            return

        if self.path == "/api/auth/verify":
            password = normalize_text(body.get("password"))
            if not password or not password_is_valid(password):
                self._send_json(401, {"error": "密码不正确。"})
                return

            token, expires_at = create_session_token()
            self._send_json(200, {"ok": True, "token": token, "expiresAt": expires_at})
            return

        if not self._require_authorization():
            return

        try:
            if self.path == "/api/projects":
                content = self._upsert_project(body.get("project") or {})
                self._send_json(200, {"ok": True, "content": content})
                return

            if self.path == "/api/experiences":
                content = self._upsert_experience(body.get("experience") or {})
                self._send_json(200, {"ok": True, "content": content})
                return
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        except Exception as error:
            self._send_json(500, {"error": str(error)})
            return

        self._send_json(404, {"error": "Route not found."})

    def do_DELETE(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        if not self._require_authorization():
            return

        try:
            if self.path.startswith("/api/projects/"):
                project_id = urllib.parse.unquote(self.path.split("/api/projects/", 1)[1])
                content = self._delete_project(project_id)
                self._send_json(200, {"ok": True, "content": content})
                return

            if self.path.startswith("/api/experiences/"):
                experience_id = urllib.parse.unquote(self.path.split("/api/experiences/", 1)[1])
                content = self._delete_experience(experience_id)
                self._send_json(200, {"ok": True, "content": content})
                return
        except LookupError as error:
            self._send_json(404, {"error": str(error)})
            return
        except Exception as error:
            self._send_json(500, {"error": str(error)})
            return

        self._send_json(404, {"error": "Route not found."})


def main() -> None:
    require_config()
    server = ThreadingHTTPServer((HOST, PORT), EditorApiHandler)
    print(f"Portfolio editor API listening on http://{HOST}:{PORT}")
    print(f"Sync target: {GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_BRANCH} -> {CONTENT_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
