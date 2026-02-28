import asyncio
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename


# Load env variables from .env file (best-effort)
try:
    load_dotenv()
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parent
SOURCES_DIR = (REPO_ROOT / "sources").resolve()
SNAPSHOTS_DIR = (REPO_ROOT / "snapshots").resolve()


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


@dataclass
class Job:
    id: str
    type: str
    status: str  # queued|running|done|error
    created_at: str
    updated_at: str
    params: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    logs: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.logs is None:
            self.logs = []


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
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        log: Optional[str] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if status is not None:
                job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            if log is not None:
                job.logs.append(log)
            job.updated_at = _now_iso()


jobs = JobStore()


def _run_job_in_thread(job_id: str, fn: Callable[[], Dict[str, Any]]) -> None:
    def runner():
        jobs.update(job_id, status="running")
        try:
            result = fn()
            jobs.update(job_id, status="done", result=result)
        except Exception as e:
            jobs.update(job_id, status="error", error=str(e))

    t = threading.Thread(target=runner, daemon=True)
    t.start()


app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


@app.get("/health")
async def health():
    return jsonify({"ok": True, "time": _now_iso()})


@app.get("/api/categories")
async def list_categories():
    return jsonify({"ok": True, "categories": ALLOWED_CATEGORIES})


@app.post("/api/upload")
async def upload():
    """Upload a file into sources/<category>/.

    multipart/form-data:
      - file: uploaded file
      - category: lectureNote|tutorialNote|assignment|pastPaper|mockpaper
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
    doc_id = str(uuid.uuid4())
    out_dir = (SOURCES_DIR / category).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_id}_{filename}"
    f.save(str(out_path))

    return jsonify(
        {
            "ok": True,
            "doc_id": doc_id,
            "category": category,
            "path": str(out_path.relative_to(REPO_ROOT)),
            "bytes": out_path.stat().st_size,
        }
    )


def _extract_text_only_pdf_to_markdown(pdf_path: Path, out_md_path: Path, *, max_pages: Optional[int] = None) -> Dict[str, Any]:
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
    return {"mode": "text", "markdown_path": str(out_md_path.relative_to(REPO_ROOT))}


def _ingest_pdf_job(params: Dict[str, Any]) -> Dict[str, Any]:
    from app.pdfToMarkdown import convert_pdf_to_markdown, pdf_diagnostics

    pdf_path = Path(params["pdf_path"])
    if not pdf_path.is_absolute():
        pdf_path = (REPO_ROOT / pdf_path)
    pdf_path = _ensure_under_dir(pdf_path, REPO_ROOT)
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    category = str(params.get("category") or "lectureNote")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")

    mode = str(params.get("mode") or "auto")  # auto|text|vision
    max_pages = params.get("max_pages")
    dpi = int(params.get("dpi") or 300)
    model = str(params.get("model") or os.environ.get("ARK_MODEL", "doubao-seed-1-8-251228"))
    allow_image_heavy = bool(params.get("allow_image_heavy") or False)

    out_name = str(params.get("out_name") or (pdf_path.stem + ".md"))
    out_dir = (SOURCES_DIR / category).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md_path = out_dir / secure_filename(out_name)

    diag_pages = int(params.get("diag_pages") or 3)
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
        result = _extract_text_only_pdf_to_markdown(pdf_path, out_md_path, max_pages=max_pages)
        result["diagnostics"] = diag
        return result

    markdown, image_paths = convert_pdf_to_markdown(
        pdf_path,
        out_md_path,
        model=model,
        max_pages=max_pages,
        dpi=dpi,
        refuse_if_too_image_heavy=not allow_image_heavy,
    )
    return {
        "mode": "vision",
        "markdown_path": str(out_md_path.relative_to(REPO_ROOT)),
        "rendered_images": len(image_paths),
        "images_dir": str((out_md_path.parent / "_pdf_images" / pdf_path.stem).relative_to(REPO_ROOT)),
        "diagnostics": diag,
    }


@app.post("/api/ingest/pdf")
async def ingest_pdf():
    data = request.get_json(silent=True) or {}
    if not data.get("pdf_path"):
        return _json_error("Missing pdf_path", status=400)

    job = jobs.create("pdf_ingest", data)
    _run_job_in_thread(job.id, lambda: _ingest_pdf_job(data))
    return jsonify({"ok": True, "job_id": job.id})


def _mockpaper_job(params: Dict[str, Any]) -> Dict[str, Any]:
    from app.mockpaper import (
        ExamSpec,
        analyze_style_with_ark,
        default_topic_prompt_from_sample,
        generate_exam_with_ark,
        generate_inline_exam_with_ark,
        load_sample_document_with_manifest,
        parse_ratios,
    )

    sample_path = Path(params["sample"])
    if not sample_path.is_absolute():
        sample_path = (REPO_ROOT / sample_path)
    sample_path = _ensure_under_dir(sample_path, REPO_ROOT)

    model = str(params.get("model") or os.environ.get("ARK_MODEL", "doubao-seed-1-8-251228"))
    max_pages = params.get("max_pages")
    num_questions = int(params.get("num_questions") or 10)
    ratios = str(params.get("ratios") or "mcq:0.3,short:0.4,code:0.3")
    language = str(params.get("language") or "auto")
    temperature = params.get("temperature")
    format_prompt = str(params.get("format_prompt") or "")
    separate = bool(params.get("separate") or False)

    out_dir = Path(params.get("out_dir") or (SOURCES_DIR / "mockpaper"))
    if not out_dir.is_absolute():
        out_dir = (REPO_ROOT / out_dir)
    out_dir = _ensure_under_dir(out_dir, REPO_ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)

    name = str(params.get("name") or f"mock_{int(time.time())}")

    sample_text, included = load_sample_document_with_manifest(sample_path, max_pages=max_pages)
    if not sample_text.strip():
        raise RuntimeError("Sample contains no extractable text")

    style = analyze_style_with_ark(
        sample_text,
        model=model,
        extra_instructions=format_prompt,
        temperature=temperature,
        show_progress=False,
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
        paper_md, answers_md = generate_exam_with_ark(
            model=model,
            style_profile=style,
            topic_prompt=topic_prompt,
            spec=spec,
            custom_format_prompt=format_prompt,
            temperature=temperature,
            show_progress=False,
        )
        paper_path = out_dir / f"{name}_paper.md"
        answers_path = out_dir / f"{name}_answers.md"
        paper_path.write_text(paper_md, encoding="utf-8")
        answers_path.write_text(answers_md, encoding="utf-8")
        return {
            "mode": "separate",
            "paper": str(paper_path.relative_to(REPO_ROOT)),
            "answers": str(answers_path.relative_to(REPO_ROOT)),
            "sample_files": [str(p.relative_to(REPO_ROOT)) for p in included],
        }

    combined_md = generate_inline_exam_with_ark(
        model=model,
        style_profile=style,
        topic_prompt=topic_prompt,
        spec=spec,
        custom_format_prompt=format_prompt,
        temperature=temperature,
        show_progress=False,
    )
    out_path = out_dir / f"{name}.md"
    out_path.write_text(combined_md, encoding="utf-8")
    return {
        "mode": "combined",
        "markdown": str(out_path.relative_to(REPO_ROOT)),
        "sample_files": [str(p.relative_to(REPO_ROOT)) for p in included],
    }


@app.post("/api/mockpaper")
async def mockpaper():
    data = request.get_json(silent=True) or {}
    if not data.get("sample"):
        return _json_error("Missing sample", status=400)
    job = jobs.create("mockpaper", data)
    _run_job_in_thread(job.id, lambda: _mockpaper_job(data))
    return jsonify({"ok": True, "job_id": job.id})


def _validate_job(params: Dict[str, Any]) -> Dict[str, Any]:
    from app.validate import (
        discover_mock_combined_files,
        discover_mock_pairs,
        iter_markdown_files,
        validate_markdown_file,
        validate_mock_combined,
        validate_mock_pair,
    )

    sources_dir = Path(params.get("sources_dir") or SOURCES_DIR)
    if not sources_dir.is_absolute():
        sources_dir = (REPO_ROOT / sources_dir)
    sources_dir = _ensure_under_dir(sources_dir, REPO_ROOT)

    run_code = bool(params.get("run_code", True))
    run_mock = bool(params.get("mock", True))

    md_files = iter_markdown_files(sources_dir)
    failures: List[Dict[str, Any]] = []
    totals = {"python_blocks": 0, "ok": 0, "failed": 0, "skipped": 0}

    for md in md_files:
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
    job = jobs.create("validate", data)
    _run_job_in_thread(job.id, lambda: _validate_job(data))
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
                "params": job.params,
                "result": job.result,
                "error": job.error,
                "logs": job.logs,
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
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snap_dir = SNAPSHOTS_DIR / snap_id
    snap_dir.mkdir(parents=True, exist_ok=False)

    manifest = _snapshot_manifest(SOURCES_DIR)
    (snap_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "snapshot_id": snap_id, "path": str((snap_dir / 'manifest.json').relative_to(REPO_ROOT))})


@app.get("/api/snapshots")
async def list_snapshots():
    if not SNAPSHOTS_DIR.exists():
        return jsonify({"ok": True, "snapshots": [], "active": None})
    active_path = SNAPSHOTS_DIR / "ACTIVE"
    active = active_path.read_text(encoding="utf-8").strip() if active_path.exists() else None
    snaps = []
    for p in sorted([d for d in SNAPSHOTS_DIR.iterdir() if d.is_dir()]):
        snaps.append({"id": p.name})
    return jsonify({"ok": True, "snapshots": snaps, "active": active})


@app.post("/api/snapshots/<snap_id>/activate")
async def activate_snapshot(snap_id: str):
    snap_dir = SNAPSHOTS_DIR / snap_id
    if not snap_dir.exists() or not snap_dir.is_dir():
        return _json_error("Snapshot not found", status=404)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS_DIR / "ACTIVE").write_text(snap_id + "\n", encoding="utf-8")
    return jsonify({"ok": True, "active": snap_id})


@app.post("/api/snapshots/<snap_id>/fork")
async def fork_snapshot(snap_id: str):
    data = request.get_json(silent=True) or {}
    new_name = str(data.get("name") or (snap_id + "_fork")).strip()[:80]
    src_dir = SNAPSHOTS_DIR / snap_id
    if not src_dir.exists() or not src_dir.is_dir():
        return _json_error("Snapshot not found", status=404)

    dest_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secure_filename(new_name)
    dest_dir = SNAPSHOTS_DIR / dest_id
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


