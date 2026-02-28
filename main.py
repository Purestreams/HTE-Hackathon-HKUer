import asyncio
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


# Load env variables from .env file (best-effort)
try:
    load_dotenv()
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parent

DATA_DIR = (REPO_ROOT / "data").resolve()
SESSIONS_DIR = (DATA_DIR / "sessions").resolve()
ACTIVE_SESSION_FILE = (DATA_DIR / "ACTIVE_SESSION").resolve()

SESSION_HEADER = "X-HTE-Session"

# IMPORTANT: We do NOT use the repo-level ./sources folder. All files live under
# data/sessions/<session_id>/sources (and snapshots under data/sessions/<session_id>/snapshots).
DEFAULT_SESSION_ID = "repo"  # historical name; now stored under data/sessions/repo/

# Model catalogs
ARK_LIST_OF_MODELS = [
    "doubao-seed-2-0-pro-260215",
    "doubao-seed-1-8-251228",
    "deepseek-v3-2-251201",
]
ARK_MAIN_MODEL = "doubao-seed-1-8-251228"
ARK_LIST_OF_THINKING_MODELS = [
    "doubao-seed-2-0-pro-260215",
    "deepseek-v3-2-251201",
]
ARK_LIST_OF_IMAGE_MODELS = [
    "doubao-seed-2-0-pro-260215",
    "doubao-seed-1-8-251228",
]

# MiniMax text model
MINIMAX_TEXT_MODELS = ["MiniMax-M2.5"]


def _safe_session_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Empty session id")
    # Keep it conservative: allow timestamp-like, slugs, underscores, dashes.
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
    if not cleaned or cleaned != value:
        raise ValueError("Invalid session id")
    return cleaned


def _ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_meta_path(session_id: str) -> Path:
    return (SESSIONS_DIR / session_id / "session.json").resolve()


def _session_dir(session_id: str) -> Path:
    return (SESSIONS_DIR / session_id).resolve()


def _ensure_session_scaffold(session_id: str, *, name: Optional[str] = None, kind: str = "isolated") -> Dict[str, Any]:
    """Ensure a session directory exists with sources/snapshots and a session.json."""

    _ensure_data_dirs()
    session_id = _safe_session_id(session_id)
    sdir = _ensure_under_dir(_session_dir(session_id), SESSIONS_DIR)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "sources").mkdir(parents=True, exist_ok=True)
    (sdir / "snapshots").mkdir(parents=True, exist_ok=True)

    meta_path = _session_meta_path(session_id)
    if meta_path.exists():
        try:
            obj = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj.get("id") == session_id:
                return obj
        except Exception:
            pass

    meta = {
        "id": session_id,
        "name": str(name or session_id),
        "kind": str(kind or "isolated"),
        "created_at": _now_iso(),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _list_sessions() -> List[Dict[str, Any]]:
    _ensure_data_dirs()
    # Ensure there is always at least one usable session.
    _ensure_session_scaffold(DEFAULT_SESSION_ID, name="Default", kind="isolated")

    sessions: List[Dict[str, Any]] = []
    for d in sorted([p for p in SESSIONS_DIR.iterdir() if p.is_dir()]):
        meta = d / "session.json"
        if not meta.exists():
            # Best-effort: still expose the directory as a session.
            sessions.append({"id": d.name, "name": d.name, "kind": "isolated", "created_at": None})
            continue
        try:
            obj = json.loads(meta.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                continue
            if "id" not in obj:
                obj["id"] = d.name
            obj.setdefault("kind", "isolated")
            sessions.append(obj)
        except Exception:
            continue
    return sessions


def _get_active_session_id() -> str:
    _ensure_data_dirs()
    if ACTIVE_SESSION_FILE.exists():
        try:
            sid = ACTIVE_SESSION_FILE.read_text(encoding="utf-8").strip()
            if sid:
                sid = _safe_session_id(sid)
                if _session_dir(sid).exists():
                    return sid
        except Exception:
            pass

    # If not set (or invalid), prefer the most recently created session.
    newest_id: Optional[str] = None
    newest_ts: Optional[float] = None
    for d in [p for p in SESSIONS_DIR.iterdir() if p.is_dir()]:
        meta = d / "session.json"
        ts: Optional[float] = None
        if meta.exists():
            try:
                obj = json.loads(meta.read_text(encoding="utf-8"))
                created_at = str(obj.get("created_at") or "")
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    ts = dt.timestamp()
            except Exception:
                ts = None
        if ts is None:
            try:
                ts = float(d.stat().st_mtime)
            except Exception:
                ts = None

        if ts is None:
            continue
        if newest_ts is None or ts > newest_ts:
            newest_ts = ts
            newest_id = d.name

    if newest_id:
        try:
            newest_id = _safe_session_id(newest_id)
            _set_active_session_id(newest_id)
            return newest_id
        except Exception:
            pass

    # Guaranteed fallback: create a default session in data/.
    _ensure_session_scaffold(DEFAULT_SESSION_ID, name="Default", kind="isolated")
    _set_active_session_id(DEFAULT_SESSION_ID)
    return DEFAULT_SESSION_ID


def _set_active_session_id(session_id: str) -> None:
    _ensure_data_dirs()
    session_id = _safe_session_id(session_id)
    ACTIVE_SESSION_FILE.write_text(session_id + "\n", encoding="utf-8")


def _resolve_session_dirs(session_id: Optional[str]) -> Tuple[str, Path, Path]:
    """Return (session_id, sources_dir, snapshots_dir) for request."""
    _ensure_data_dirs()
    sid = session_id or _get_active_session_id()
    sid = _safe_session_id(sid)

    sdir = _session_dir(sid)
    # Ensure session dir exists and is inside SESSIONS_DIR
    sdir = _ensure_under_dir(sdir, SESSIONS_DIR)
    if not sdir.exists() or not sdir.is_dir():
        if sid == DEFAULT_SESSION_ID:
            _ensure_session_scaffold(DEFAULT_SESSION_ID, name="Default", kind="isolated")
        else:
            raise ValueError(f"Session not found: {sid}")

    sources_dir = (sdir / "sources").resolve()
    snapshots_dir = (sdir / "snapshots").resolve()
    sources_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    return sid, sources_dir, snapshots_dir


def _request_session_id() -> Optional[str]:
    # Prefer explicit header so frontend can choose per request.
    v = request.headers.get(SESSION_HEADER)
    if v:
        return v.strip()
    return None


def _create_session(name: str) -> Dict[str, Any]:
    _ensure_data_dirs()
    name = str(name or "session").strip()[:80] or "session"
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secure_filename(name)
    sid = _safe_session_id(sid)
    sdir = _session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=False)
    (sdir / "sources").mkdir(parents=True, exist_ok=True)
    (sdir / "snapshots").mkdir(parents=True, exist_ok=True)
    meta = {"id": sid, "name": name, "kind": "isolated", "created_at": _now_iso()}
    _session_meta_path(sid).parent.mkdir(parents=True, exist_ok=True)
    _session_meta_path(sid).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _request_session_id_any() -> Optional[str]:
    """Session selection for endpoints that cannot set headers (iframe/img).

    Priority:
      1) query param session_id
      2) header X-HTE-Session
      3) server active session
    """

    q = (request.args.get("session_id") or "").strip()
    if q:
        return q
    return _request_session_id()


def _resolve_sources_dir_for_request() -> Tuple[str, Path]:
    sid, sources_dir, _ = _resolve_session_dirs(_request_session_id_any())
    return sid, sources_dir


def _resolve_file_under_sources(path_str: str) -> Tuple[str, Path, Path]:
    """Return (session_id, sources_dir, abs_path) for a relative path under session sources."""
    if not path_str:
        raise ValueError("Missing path")
    sid, sources_dir = _resolve_sources_dir_for_request()
    # The path should be relative to sources root.
    rel = Path(path_str)
    if rel.is_absolute():
        raise ValueError("Absolute paths not allowed")
    abs_path = (sources_dir / rel).resolve()
    abs_path = _ensure_under_dir(abs_path, sources_dir)
    return sid, sources_dir, abs_path


def _resolve_path_in_session_sources(path_value: str, sources_dir: Path) -> Path:
    """Resolve a client path strictly under session sources.

    Backward compatibility:
    - Accept legacy relative paths beginning with "sources/" and strip that prefix.
    """

    raw = str(path_value or "").strip()
    if not raw:
        raise ValueError("Missing path")

    p = Path(raw)
    if p.is_absolute():
        return _ensure_under_dir(p, sources_dir)

    normalized = raw.replace("\\", "/")
    if normalized == "sources":
        normalized = "."
    elif normalized.startswith("sources/"):
        normalized = normalized[len("sources/"):]

    resolved = (sources_dir / normalized).resolve()
    return _ensure_under_dir(resolved, sources_dir)


ALLOWED_CATEGORIES = [
    "lectureNote",
    "tutorialNote",
    "assignment",
    "pastPaper",
    "mockpaper",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(message: str, *, status: int = 400, **extra: Any):
    payload = {"ok": False, "error": message, **extra}
    return jsonify(payload), status


def _ensure_under_dir(path: Path, base_dir: Path) -> Path:
    """Resolve a path and ensure it's under base_dir to avoid path traversal."""
    rp = path.expanduser().resolve()
    base = base_dir.expanduser().resolve()
    if rp == base or base in rp.parents:
        return rp
    raise ValueError(f"Path not allowed: {path}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_available_models() -> Dict[str, List[str] | str]:
    # Base catalog (explicit per requirement)
    models = list(ARK_LIST_OF_MODELS)
    thinking_models = list(ARK_LIST_OF_THINKING_MODELS)
    image_models = list(ARK_LIST_OF_IMAGE_MODELS)
    text_models = list(MINIMAX_TEXT_MODELS)
    main_model = ARK_MAIN_MODEL

    # Optional env overrides to extend lists
    raw = str(os.environ.get("AVAILABLE_MODELS") or os.environ.get("MODEL_CHOICES") or "").strip()
    if raw:
        for part in re.split(r"[\n,;]+", raw):
            p = part.strip()
            if p and p not in models:
                models.append(p)

    env_main = str(os.environ.get("MOCKPAPER_MODEL") or os.environ.get("ARK_MODEL") or "").strip()
    if env_main:
        main_model = env_main
        if env_main not in models and env_main not in text_models:
            models.append(env_main)

    return {
        "models": models,
        "thinking_models": thinking_models,
        "image_models": image_models,
        "text_models": text_models,
        "main_model": main_model,
    }


@dataclass
class Job:
    id: str
    type: str
    status: str  # queued|running|done|error
    created_at: str
    updated_at: str
    params: Dict[str, Any]
    started_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    logs: List[str] = None  # type: ignore[assignment]
    progress: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.logs is None:
            self.logs = []
        if self.progress is None:
            self.progress = {}


class JobStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self, job_type: str, params: Dict[str, Any]) -> Job:
        job_id = str(uuid.uuid4())
        now = _now_iso()
        job = Job(
            id=job_id,
            type=job_type,
            status="queued",
            created_at=now,
            updated_at=now,
            params=params,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        started_at: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        log: Optional[str] = None,
        progress: Optional[Dict[str, Any]] = None,
        progress_patch: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if status is not None:
                job.status = status
            if started_at is not None:
                job.started_at = started_at
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            if log is not None:
                job.logs.append(log)
            if progress is not None:
                job.progress = progress
            if progress_patch is not None:
                job.progress.update(progress_patch)
            job.updated_at = _now_iso()


jobs = JobStore()


def _run_job_in_thread(job_id: str, fn: Callable[[], Dict[str, Any]]) -> None:
    def runner():
        now = _now_iso()
        jobs.update(
            job_id,
            status="running",
            started_at=now,
            progress={"stage": "starting", "message": "starting", "elapsed_sec": 0.0},
        )
        try:
            result = fn()
            # Preserve progress but mark stage complete.
            jobs.update(job_id, status="done", result=result, progress_patch={"stage": "done"})
        except Exception as e:
            jobs.update(job_id, status="error", error=str(e))

    t = threading.Thread(target=runner, daemon=True)
    t.start()


app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


@app.get("/health")
async def health():
    return jsonify({"ok": True, "time": _now_iso(), "active_session": _get_active_session_id()})


@app.get("/api/sessions")
async def list_sessions():
    return jsonify({"ok": True, "sessions": _list_sessions(), "active": _get_active_session_id()})


@app.post("/api/sessions")
async def create_session():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "session")
    meta = _create_session(name)
    return jsonify({"ok": True, "session": meta})


@app.post("/api/sessions/<session_id>/activate")
async def activate_session(session_id: str):
    try:
        session_id = _safe_session_id(session_id)
    except Exception:
        return _json_error("Invalid session id", status=400)

    # Ensure default session exists; for others require they were created.
    if session_id == DEFAULT_SESSION_ID:
        _ensure_session_scaffold(DEFAULT_SESSION_ID, name="Default", kind="isolated")
    else:
        sdir = _session_dir(session_id)
        if not sdir.exists() or not sdir.is_dir():
            return _json_error("Session not found", status=404)

    _set_active_session_id(session_id)
    return jsonify({"ok": True, "active": session_id})


@app.delete("/api/sessions/<session_id>")
async def delete_session(session_id: str):
    try:
        session_id = _safe_session_id(session_id)
    except Exception:
        return _json_error("Invalid session id", status=400)

    if session_id == DEFAULT_SESSION_ID:
        return _json_error("Cannot delete default session", status=400)

    sdir = _session_dir(session_id)
    sdir = _ensure_under_dir(sdir, SESSIONS_DIR)
    if not sdir.exists() or not sdir.is_dir():
        return _json_error("Session not found", status=404)

    try:
        import shutil

        shutil.rmtree(sdir)
    except Exception as e:
        return _json_error(str(e), status=500)

    # If we deleted the active session, switch to default
    if _get_active_session_id() == session_id:
        _ensure_session_scaffold(DEFAULT_SESSION_ID, name="Default", kind="isolated")
        _set_active_session_id(DEFAULT_SESSION_ID)

    return jsonify({"ok": True, "deleted": session_id})


@app.get("/api/categories")
async def list_categories():
    return jsonify({"ok": True, "categories": ALLOWED_CATEGORIES})


@app.get("/api/models")
async def list_models():
    return jsonify({"ok": True, **_get_available_models()})


@app.post("/api/upload")
async def upload():
    """Upload a file into session sources and optionally ingest PDFs.

    multipart/form-data:
      - file: uploaded file
      - category: lectureNote|tutorialNote|assignment|pastPaper|mockpaper
      - ingest: optional (1/true) to auto-ingest PDFs (default: true for PDFs)
      - mode/max_pages/dpi/allow_image_heavy/out_name/diag_pages/model: optional ingest params for PDFs
    """

    if "file" not in request.files:
        return _json_error("Missing file field", status=400)
    f = request.files["file"]
    if not f or not f.filename:
        return _json_error("Empty filename", status=400)

    category = (request.form.get("category") or "lectureNote").strip()
    if category not in ALLOWED_CATEGORIES:
        return _json_error("Invalid category", status=400, allowed=ALLOWED_CATEGORIES)

    filename = secure_filename(f.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md", ".markdown", ".txt"}:
        return _json_error("Unsupported file type. Use .pdf/.md/.txt", status=400)
    doc_id = str(uuid.uuid4())
    _, sources_dir, _ = _resolve_session_dirs(_request_session_id())
    out_dir = (sources_dir / category).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_id}_{filename}"
    f.save(str(out_path))

    # If PDF, optionally trigger ingest job
    if suffix == ".pdf":
        ingest_flag = str(request.form.get("ingest") or "").strip().lower()
        auto_ingest = True if ingest_flag == "" else ingest_flag in {"1", "true", "yes", "y"}
        if auto_ingest:
            data: Dict[str, Any] = {
                "pdf_path": str(out_path.relative_to(sources_dir)),
                "category": category,
            }
            if request.form.get("mode"):
                data["mode"] = request.form.get("mode")
            if request.form.get("max_pages"):
                data["max_pages"] = int(request.form.get("max_pages") or 0) or None
            if request.form.get("dpi"):
                data["dpi"] = int(request.form.get("dpi") or 0) or None
            if request.form.get("diag_pages"):
                data["diag_pages"] = int(request.form.get("diag_pages") or 0) or None
            if request.form.get("allow_image_heavy"):
                data["allow_image_heavy"] = str(request.form.get("allow_image_heavy") or "").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "y",
                }
            if request.form.get("model"):
                data["model"] = request.form.get("model")
            else:
                data["model"] = _get_available_models()["main_model"]
            if request.form.get("out_name"):
                data["out_name"] = request.form.get("out_name")

            # Keep session binding for job
            sid = _request_session_id()
            if sid:
                data["session_id"] = sid

            job = jobs.create("pdf_ingest", data)
            _run_job_in_thread(job.id, lambda: _ingest_pdf_job(job.id, data))
            return jsonify(
                {
                    "ok": True,
                    "doc_id": doc_id,
                    "category": category,
                    # Paths are always relative to the session sources root.
                    "path": str(out_path.relative_to(sources_dir)),
                    "bytes": out_path.stat().st_size,
                    "job_id": job.id,
                    "ingest": True,
                }
            )

    return jsonify(
        {
            "ok": True,
            "doc_id": doc_id,
            "category": category,
            # Paths are always relative to the session sources root.
            "path": str(out_path.relative_to(sources_dir)),
            "bytes": out_path.stat().st_size,
        }
    )


@app.get("/api/files/list")
async def list_files():
    """List files under the current session sources directory.

    Query params:
      - dir: relative directory under sources (default: '.')
      - session_id: optional, for clients that can't set headers
    """

    _, sources_dir = _resolve_sources_dir_for_request()
    dir_str = str(request.args.get("dir") or ".").strip() or "."
    rel_dir = Path(dir_str)
    if rel_dir.is_absolute():
        return _json_error("dir must be relative to session sources", status=400)
    abs_dir = (sources_dir / rel_dir).resolve()
    try:
        abs_dir = _ensure_under_dir(abs_dir, sources_dir)
    except Exception:
        return _json_error("dir not allowed", status=400)

    if not abs_dir.exists() or not abs_dir.is_dir():
        return _json_error("dir not found", status=404)

    entries: List[Dict[str, Any]] = []
    for p in sorted(abs_dir.iterdir(), key=lambda x: (0 if x.is_dir() else 1, x.name.lower())):
        try:
            st = p.stat()
            entries.append(
                {
                    "name": p.name,
                    "path": str(p.relative_to(sources_dir)),
                    "type": "dir" if p.is_dir() else "file",
                    "bytes": int(st.st_size) if p.is_file() else None,
                    "mtime": float(st.st_mtime),
                    "ext": p.suffix.lower()[1:] if p.is_file() and p.suffix else "",
                }
            )
        except Exception:
            continue

    return jsonify({"ok": True, "dir": str(abs_dir.relative_to(sources_dir)), "entries": entries})


@app.get("/api/files/stat")
async def stat_file():
    """Stat a file under session sources.

    Query params:
      - path: relative path under sources
      - session_id: optional
    """

    path_str = str(request.args.get("path") or "").strip()
    try:
        _, sources_dir, abs_path = _resolve_file_under_sources(path_str)
    except Exception as e:
        return _json_error(str(e), status=400)

    if not abs_path.exists():
        return jsonify({"ok": True, "exists": False, "path": path_str})

    try:
        st = abs_path.stat()
        return jsonify(
            {
                "ok": True,
                "exists": True,
                "path": str(abs_path.relative_to(sources_dir)),
                "type": "dir" if abs_path.is_dir() else "file",
                "bytes": int(st.st_size) if abs_path.is_file() else None,
                "mtime": float(st.st_mtime),
            }
        )
    except Exception as e:
        return _json_error(str(e), status=500)


@app.get("/api/files/text")
async def get_file_text():
    """Fetch a text file (e.g., .md) under session sources."""

    path_str = str(request.args.get("path") or "").strip()
    try:
        _, sources_dir, abs_path = _resolve_file_under_sources(path_str)
    except Exception as e:
        return _json_error(str(e), status=400)

    if not abs_path.exists() or not abs_path.is_file():
        return _json_error("file not found", status=404)

    # Guardrail: avoid dumping huge binaries.
    max_bytes = int(os.environ.get("MAX_TEXT_FILE_BYTES", str(2 * 1024 * 1024)))
    try:
        if abs_path.stat().st_size > max_bytes:
            return _json_error("file too large", status=413, max_bytes=max_bytes)
        text = abs_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _json_error("file is not valid utf-8 text", status=415)
    except Exception as e:
        return _json_error(str(e), status=500)

    return jsonify({"ok": True, "path": str(abs_path.relative_to(sources_dir)), "text": text})


@app.get("/api/files/raw")
async def get_file_raw():
    """Stream a file under session sources.

    Query params:
      - path: relative path under sources
      - download: 1 to force attachment
      - session_id: optional
    """

    path_str = str(request.args.get("path") or "").strip()
    download = str(request.args.get("download") or "").strip() == "1"

    try:
        _, _, abs_path = _resolve_file_under_sources(path_str)
    except Exception as e:
        return _json_error(str(e), status=400)

    if not abs_path.exists() or not abs_path.is_file():
        return _json_error("file not found", status=404)

    suffix = abs_path.suffix.lower()
    mimetype = None
    if suffix == ".pdf":
        mimetype = "application/pdf"
    elif suffix in {".md", ".markdown"}:
        mimetype = "text/markdown; charset=utf-8"
    elif suffix in {".txt"}:
        mimetype = "text/plain; charset=utf-8"

    return send_file(
        abs_path,
        mimetype=mimetype,
        as_attachment=download,
        download_name=abs_path.name,
        conditional=True,
        etag=True,
        last_modified=abs_path.stat().st_mtime,
    )


@app.delete("/api/files")
async def delete_file():
    """Delete a file under session sources.

    Query params:
      - path: relative path under sources
      - session_id: optional
    """

    path_str = str(request.args.get("path") or "").strip()
    try:
        _, sources_dir, abs_path = _resolve_file_under_sources(path_str)
    except Exception as e:
        return _json_error(str(e), status=400)

    if not abs_path.exists() or not abs_path.is_file():
        return _json_error("file not found", status=404)

    try:
        abs_path.unlink()
    except Exception as e:
        return _json_error(str(e), status=500)

    return jsonify({"ok": True, "path": str(abs_path.relative_to(sources_dir))})


def _extract_text_only_pdf_to_markdown(
    pdf_path: Path,
    out_md_path: Path,
    *,
    max_pages: Optional[int] = None,
    paths_base: Optional[Path] = None,
) -> Dict[str, Any]:
    from app.pdfToMarkdown import extract_text_from_pdf

    texts = extract_text_from_pdf(pdf_path, max_pages=max_pages)
    title = pdf_path.stem
    parts = [f"# {title}\n"]
    for i, t in enumerate(texts, start=1):
        t = (t or "").strip()
        if not t:
            continue
        parts.append(f"\n## Page {i}\n\n{t}\n")
    md = "\n".join(parts).strip() + "\n"
    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.write_text(md, encoding="utf-8")
    base = paths_base or REPO_ROOT
    return {"mode": "text", "markdown_path": str(out_md_path.relative_to(base))}


def _ingest_pdf_job(job_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from app.pdfToMarkdown import convert_pdf_to_markdown, pdf_diagnostics
    import time as _time

    start = _time.monotonic()
    last = {"t": start, "tok": 0}

    def _progress(stage: str, *, message: str = "", total_tokens: Optional[int] = None) -> None:
        now = _time.monotonic()
        elapsed = now - start
        patch: Dict[str, Any] = {"stage": stage, "elapsed_sec": float(elapsed)}
        if message:
            patch["message"] = message
        if total_tokens is not None:
            dt = max(1e-6, now - float(last["t"]))
            d_tok = int(total_tokens) - int(last["tok"])
            if (now - float(last["t"])) >= 0.6:
                patch["tokens"] = int(total_tokens)
                patch["tokens_per_sec"] = float(d_tok / dt)
                last["t"] = now
                last["tok"] = int(total_tokens)
            else:
                patch["tokens"] = int(total_tokens)
        jobs.update(job_id, progress_patch=patch)

    session_id = str(params.get("session_id") or "") or None
    _, sources_dir, _ = _resolve_session_dirs(session_id)

    pdf_path = _resolve_path_in_session_sources(str(params["pdf_path"]), sources_dir)
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    category = str(params.get("category") or "lectureNote")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")

    mode = str(params.get("mode") or "auto")  # auto|text|vision
    max_pages = params.get("max_pages")
    dpi = int(params.get("dpi") or 300)
    model = str(
        params.get("model")
        or _get_available_models()["main_model"]
        or os.environ.get("ARK_MODEL", "doubao-seed-1-8-251228")
    )
    if model not in _get_available_models()["image_models"]:
        raise ValueError("PDF ingest requires a vision-capable model.")
    allow_image_heavy = bool(params.get("allow_image_heavy") or False)

    out_name = str(params.get("out_name") or (pdf_path.stem + ".md"))
    out_dir = (sources_dir / category).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md_path = out_dir / secure_filename(out_name)

    diag_pages = int(params.get("diag_pages") or 3)
    _progress("diagnostics", message="analyzing pdf")
    diag = pdf_diagnostics(pdf_path, max_pages=diag_pages)

    if mode not in {"auto", "text", "vision"}:
        raise ValueError("mode must be one of: auto|text|vision")

    if mode == "auto":
        total_text = int(diag.get("total_text_chars") or 0)
        total_images = diag.get("total_images")
        # Heuristic: if it has plenty of embedded text and not many images, use text path.
        if total_text >= 800 and (total_images is None or int(total_images) <= 2):
            mode = "text"
        else:
            mode = "vision"

    if mode == "text":
        _progress("convert", message="extracting embedded text")
        result = _extract_text_only_pdf_to_markdown(
            pdf_path,
            out_md_path,
            max_pages=max_pages,
            paths_base=sources_dir,
        )
        result["diagnostics"] = diag
        return result

    _progress("convert", message="converting with vision model")
    markdown, image_paths = convert_pdf_to_markdown(
        pdf_path,
        out_md_path,
        model=model,
        max_pages=max_pages,
        dpi=dpi,
        refuse_if_too_image_heavy=not allow_image_heavy,
        on_progress_tokens=lambda tok: _progress("convert", total_tokens=tok),
    )
    return {
        "mode": "vision",
        "markdown_path": str(out_md_path.relative_to(sources_dir)),
        "rendered_images": len(image_paths),
        "images_dir": str((out_md_path.parent / "_pdf_images" / pdf_path.stem).relative_to(sources_dir)),
        "diagnostics": diag,
    }


@app.post("/api/ingest/pdf")
async def ingest_pdf():
    data = request.get_json(silent=True) or {}
    if not data.get("pdf_path"):
        return _json_error("Missing pdf_path", status=400)

    # Allow either header-based session or explicit session_id in payload.
    if not data.get("session_id"):
        sid = _request_session_id()
        if sid:
            data["session_id"] = sid

    job = jobs.create("pdf_ingest", data)
    _run_job_in_thread(job.id, lambda: _ingest_pdf_job(job.id, data))
    return jsonify({"ok": True, "job_id": job.id})


def _mockpaper_job(job_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from app.mockpaper import (
        ExamSpec,
        analyze_style_with_ark,
        default_topic_prompt_from_sample,
        generate_exam_with_ark,
        generate_inline_exam_with_ark,
        load_sample_document_with_manifest,
        parse_ratios,
    )
    import time as _time

    start = _time.monotonic()
    last = {"t": start, "tok": 0}

    def _progress(stage: str, *, message: str = "", total_tokens: Optional[int] = None) -> None:
        now = _time.monotonic()
        elapsed = now - start
        patch: Dict[str, Any] = {"stage": stage, "elapsed_sec": float(elapsed)}
        if message:
            patch["message"] = message
        if total_tokens is not None:
            # throttle TPS calculation to avoid noisy updates
            dt = max(1e-6, now - float(last["t"]))
            d_tok = int(total_tokens) - int(last["tok"])
            if (now - float(last["t"])) >= 0.6:
                patch["tokens"] = int(total_tokens)
                patch["tokens_per_sec"] = float(d_tok / dt)
                last["t"] = now
                last["tok"] = int(total_tokens)
            else:
                patch["tokens"] = int(total_tokens)
        jobs.update(job_id, progress_patch=patch)

    session_id = str(params.get("session_id") or "") or None
    _, sources_dir, _ = _resolve_session_dirs(session_id)

    sample_path = _resolve_path_in_session_sources(str(params["sample"]), sources_dir)

    model = str(
        params.get("model")
        or _get_available_models()["main_model"]
        or os.environ.get("ARK_MODEL", "doubao-seed-1-8-251228")
    )
    max_pages = params.get("max_pages")
    num_questions = int(params.get("num_questions") or 10)
    ratios = str(params.get("ratios") or "mcq:0.3,short:0.4,code:0.3")
    language = str(params.get("language") or "auto")
    temperature = params.get("temperature")
    format_prompt = str(params.get("format_prompt") or "")
    separate = bool(params.get("separate") or False)

    out_dir_raw = str(params.get("out_dir") or "mockpaper")
    out_dir = _resolve_path_in_session_sources(out_dir_raw, sources_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    name = str(params.get("name") or f"mock_{int(time.time())}")

    _progress("load_sample", message="loading sample")
    sample_text, included = load_sample_document_with_manifest(sample_path, max_pages=max_pages)
    if not sample_text.strip():
        raise RuntimeError("Sample contains no extractable text")
    jobs.update(
        job_id,
        progress_patch={
            "sample_files": [str(p.relative_to(sources_dir)) for p in included],
        },
    )

    _progress("style", message="analyzing style")
    style = analyze_style_with_ark(
        sample_text,
        model=model,
        extra_instructions=format_prompt,
        temperature=temperature,
        show_progress=False,
        on_progress_tokens=lambda tok: _progress("style", total_tokens=tok),
    )

    topic_prompt = str(params.get("topic") or "")
    if not topic_prompt.strip():
        topic_prompt = default_topic_prompt_from_sample(sample_text)

    spec = ExamSpec(
        num_questions=num_questions,
        ratios=parse_ratios(ratios),
        language=language,
    )

    if separate:
        _progress("exam", message="generating exam")
        paper_md, answers_md = generate_exam_with_ark(
            model=model,
            style_profile=style,
            topic_prompt=topic_prompt,
            spec=spec,
            custom_format_prompt=format_prompt,
            temperature=temperature,
            show_progress=False,
            on_progress_tokens=lambda tok: _progress("exam", total_tokens=tok),
        )
        paper_path = out_dir / f"{name}_paper.md"
        answers_path = out_dir / f"{name}_answers.md"
        paper_path.write_text(paper_md, encoding="utf-8")
        answers_path.write_text(answers_md, encoding="utf-8")
        return {
            "mode": "separate",
            "paper": str(paper_path.relative_to(sources_dir)),
            "answers": str(answers_path.relative_to(sources_dir)),
            "sample_files": [str(p.relative_to(sources_dir)) for p in included],
        }

    _progress("exam", message="generating exam")
    combined_md = generate_inline_exam_with_ark(
        model=model,
        style_profile=style,
        topic_prompt=topic_prompt,
        spec=spec,
        custom_format_prompt=format_prompt,
        temperature=temperature,
        show_progress=False,
        on_progress_tokens=lambda tok: _progress("exam", total_tokens=tok),
    )
    out_path = out_dir / f"{name}.md"
    out_path.write_text(combined_md, encoding="utf-8")
    return {
        "mode": "combined",
        "markdown": str(out_path.relative_to(sources_dir)),
        "sample_files": [str(p.relative_to(sources_dir)) for p in included],
    }


@app.post("/api/mockpaper")
async def mockpaper():
    data = request.get_json(silent=True) or {}
    if not data.get("sample"):
        return _json_error("Missing sample", status=400)

    if not data.get("session_id"):
        sid = _request_session_id()
        if sid:
            data["session_id"] = sid
    job = jobs.create("mockpaper", data)
    _run_job_in_thread(job.id, lambda: _mockpaper_job(job.id, data))
    return jsonify({"ok": True, "job_id": job.id})


def _validate_job(job_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from app.validate import (
        discover_mock_combined_files,
        discover_mock_pairs,
        iter_markdown_files,
        validate_markdown_file,
        validate_mock_combined,
        validate_mock_pair,
    )

    import time as _time

    start = _time.monotonic()
    last_update_t = start

    def _progress(stage: str, *, message: str = "") -> None:
        nonlocal last_update_t
        now = _time.monotonic()
        if now - last_update_t < 0.7:
            return
        last_update_t = now
        jobs.update(
            job_id,
            progress_patch={
                "stage": stage,
                "message": message,
                "elapsed_sec": float(now - start),
            },
        )

    session_id = str(params.get("session_id") or "") or None
    _, default_sources_dir, _ = _resolve_session_dirs(session_id)
    sources_dir_raw = str(params.get("sources_dir") or ".")
    sources_dir = _resolve_path_in_session_sources(sources_dir_raw, default_sources_dir)

    run_code = bool(params.get("run_code", True))
    run_mock = bool(params.get("mock", True))

    _progress("scan", message="discover markdown files")
    md_files = iter_markdown_files(sources_dir)
    failures: List[Dict[str, Any]] = []
    totals = {"python_blocks": 0, "ok": 0, "failed": 0, "skipped": 0}

    for idx, md in enumerate(md_files, start=1):
        _progress("scan", message=f"validating markdown ({idx})")
        results = validate_markdown_file(md, run_code=run_code)
        for r in results:
            if r.block.language in {"py", "python"}:
                totals["python_blocks"] += 1
                if r.status == "ok":
                    totals["ok"] += 1
                elif r.status == "failed":
                    totals["failed"] += 1
                    failures.append(
                        {
                            "file": str(r.file_path.relative_to(REPO_ROOT)),
                            "lines": [r.block.start_line, r.block.end_line],
                            "stderr": r.stderr,
                            "stdout": r.stdout,
                            "returncode": r.returncode,
                            "note": r.note,
                        }
                    )
                else:
                    totals["skipped"] += 1

    mock_issues: List[Dict[str, Any]] = []
    if run_mock:
        _progress("mock_checks", message="validating mockpaper pairs")
        for base, paper_path, answers_path in discover_mock_pairs(sources_dir):
            check = validate_mock_pair(base, paper_path, answers_path)
            if check.status != "ok":
                mock_issues.append(
                    {
                        "type": "pair",
                        "base": base,
                        "paper": str(paper_path.relative_to(REPO_ROOT)),
                        "answers": str(answers_path.relative_to(REPO_ROOT)),
                        "issues": check.issues,
                    }
                )

        _progress("mock_checks", message="validating combined mockpapers")
        for p in discover_mock_combined_files(sources_dir):
            status, issues = validate_mock_combined(p)
            if status != "ok":
                mock_issues.append(
                    {
                        "type": "combined",
                        "file": str(p.relative_to(REPO_ROOT)),
                        "issues": issues,
                    }
                )

    return {
        "markdown_files": len(md_files),
        "code_summary": totals,
        "code_failures": failures,
        "mock_issues": mock_issues,
    }


@app.post("/api/validate")
async def validate():
    data = request.get_json(silent=True) or {}
    if not data.get("session_id"):
        sid = _request_session_id()
        if sid:
            data["session_id"] = sid
    job = jobs.create("validate", data)
    _run_job_in_thread(job.id, lambda: _validate_job(job.id, data))
    return jsonify({"ok": True, "job_id": job.id})


@app.get("/api/jobs/<job_id>")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return _json_error("Job not found", status=404)
    return jsonify(
        {
            "ok": True,
            "job": {
                "id": job.id,
                "type": job.type,
                "status": job.status,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "started_at": job.started_at,
                "params": job.params,
                "result": job.result,
                "error": job.error,
                "logs": job.logs,
                "progress": job.progress,
            },
        }
    )


def _snapshot_manifest(sources_dir: Path) -> Dict[str, Any]:
    sources_dir = sources_dir.expanduser().resolve()
    files = [p for p in sources_dir.rglob("*") if p.is_file()]
    entries: List[Dict[str, Any]] = []
    for p in sorted(files):
        rel = p.relative_to(REPO_ROOT)
        try:
            st = p.stat()
            entries.append(
                {
                    "path": str(rel),
                    "bytes": int(st.st_size),
                    "mtime": float(st.st_mtime),
                    "sha256": _sha256_file(p),
                }
            )
        except Exception:
            continue
    return {"created_at": _now_iso(), "sources_dir": str(sources_dir.relative_to(REPO_ROOT)), "files": entries}


@app.post("/api/snapshots")
async def create_snapshot():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "snapshot").strip()[:80]
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secure_filename(name)
    _, sources_dir, snapshots_dir = _resolve_session_dirs(_request_session_id())
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = snapshots_dir / snap_id
    snap_dir.mkdir(parents=True, exist_ok=False)

    manifest = _snapshot_manifest(sources_dir)
    (snap_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "snapshot_id": snap_id, "path": str((snap_dir / 'manifest.json').relative_to(REPO_ROOT))})


@app.get("/api/snapshots")
async def list_snapshots():
    _, _, snapshots_dir = _resolve_session_dirs(_request_session_id())
    if not snapshots_dir.exists():
        return jsonify({"ok": True, "snapshots": [], "active": None})
    active_path = snapshots_dir / "ACTIVE"
    active = active_path.read_text(encoding="utf-8").strip() if active_path.exists() else None
    snaps = []
    for p in sorted([d for d in snapshots_dir.iterdir() if d.is_dir()]):
        snaps.append({"id": p.name})
    return jsonify({"ok": True, "snapshots": snaps, "active": active})


@app.post("/api/snapshots/<snap_id>/activate")
async def activate_snapshot(snap_id: str):
    _, _, snapshots_dir = _resolve_session_dirs(_request_session_id())
    snap_dir = snapshots_dir / snap_id
    if not snap_dir.exists() or not snap_dir.is_dir():
        return _json_error("Snapshot not found", status=404)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / "ACTIVE").write_text(snap_id + "\n", encoding="utf-8")
    return jsonify({"ok": True, "active": snap_id})


@app.post("/api/snapshots/<snap_id>/fork")
async def fork_snapshot(snap_id: str):
    data = request.get_json(silent=True) or {}
    new_name = str(data.get("name") or (snap_id + "_fork")).strip()[:80]
    _, _, snapshots_dir = _resolve_session_dirs(_request_session_id())
    src_dir = snapshots_dir / snap_id
    if not src_dir.exists() or not src_dir.is_dir():
        return _json_error("Snapshot not found", status=404)

    dest_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secure_filename(new_name)
    dest_dir = snapshots_dir / dest_id
    dest_dir.mkdir(parents=True, exist_ok=False)

    src_manifest = src_dir / "manifest.json"
    if not src_manifest.exists():
        return _json_error("Snapshot manifest missing", status=500)
    (dest_dir / "manifest.json").write_text(src_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    return jsonify({"ok": True, "snapshot_id": dest_id})


if __name__ == "__main__":
    # Dev server (for production, run under a real WSGI/ASGI server)
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)


