import argparse
import json
import os
import sys
import re
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import anthropic
from volcenginesdkarkruntime import Ark

try:
    from app.streaming import TokenRateProgress, estimate_tokens, stream_text_from_ark_response
    from app.pdfToMarkdown import extract_text_from_pdf
except ModuleNotFoundError:
    # Supports running as a script: `python app/mockpaper.py ...`
    # When executed this way, Python sets sys.path[0] to the `app/` folder,
    # so top-level imports like `import app.*` fail unless we add repo root.
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from app.streaming import TokenRateProgress, estimate_tokens, stream_text_from_ark_response
    from app.pdfToMarkdown import extract_text_from_pdf


def _require_ark_api_key() -> str:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing ARK_API_KEY. Set it in your shell (export ARK_API_KEY=...)."
        )
    return api_key


def _get_mockpaper_provider() -> str:
    provider = str(os.environ.get("MOCKPAPER_PROVIDER") or "minimax").strip().lower()
    if provider not in {"ark", "minimax"}:
        raise RuntimeError("MOCKPAPER_PROVIDER must be 'ark' or 'minimax'")
    return provider


def _require_minimax_api_key() -> str:
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing MINIMAX_API_KEY (or ANTHROPIC_API_KEY). Set it in your shell/.env."
        )
    return api_key


def _build_client() -> Tuple[str, Any]:
    provider = _get_mockpaper_provider()
    if provider == "ark":
        api_key = _require_ark_api_key()
        return provider, Ark(api_key=api_key)

    # minimax via Anthropic-compatible endpoint
    api_key = _require_minimax_api_key()
    base_url = str(os.environ.get("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic")
    return provider, anthropic.Anthropic(api_key=api_key, base_url=base_url)


def _messages_to_anthropic(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    system_parts: List[str] = []
    out_messages: List[Dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "")
        if role == "system":
            system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            continue
        out_messages.append({"role": role, "content": content})
    system = "\n\n".join([p for p in system_parts if p.strip()]).strip()
    return system, out_messages


def _chat_complete_text(
    *,
    provider: str,
    client: Any,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    show_progress: bool = False,
    progress_label: str = "llm",
    on_progress_tokens: Optional[Callable[[int], None]] = None,
) -> str:
    if provider == "ark":
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature

        if show_progress or on_progress_tokens is not None:
            progress = TokenRateProgress(label=progress_label) if show_progress else None
            if progress:
                progress.start()
            stream = client.chat.completions.create(**payload, stream=True)
            content_parts: List[str] = []
            total_tok = 0
            for chunk in stream:
                delta_text = stream_text_from_ark_response([chunk])
                if not delta_text:
                    continue
                content_parts.append(delta_text)
                total_tok = estimate_tokens("".join(content_parts))
                if progress:
                    progress.update(total_tok)
                if on_progress_tokens is not None:
                    on_progress_tokens(total_tok)
            content = "".join(content_parts)
            if progress:
                progress.finish(estimate_tokens(content))
            return content

        resp = client.chat.completions.create(**payload)
        return resp.choices[0].message.content or ""  # type: ignore[attr-defined]

    # minimax (Anthropic-compatible)
    system, amsg = _messages_to_anthropic(messages)
    payload2: Dict[str, Any] = {
        "model": model,
        "max_tokens": 8192,
        "system": system,
        "messages": amsg,
    }
    if temperature is not None:
        payload2["temperature"] = temperature

    msg = client.messages.create(**payload2)
    parts: List[str] = []
    for block in (msg.content or []):
        t = getattr(block, "type", None)
        if t == "text":
            parts.append(getattr(block, "text", "") or "")
    content = "".join(parts)
    if on_progress_tokens is not None:
        on_progress_tokens(estimate_tokens(content))
    return content


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_sample_document_with_manifest(
    sample_path: Path, *, max_pages: Optional[int] = None
) -> Tuple[str, List[Path]]:
    """Like load_sample_document(), but also returns which files were included."""

    sample_path = sample_path.expanduser().resolve()

    if sample_path.is_dir():
        parts: List[str] = []
        included: List[Path] = []
        candidates: List[Path] = []
        for ext in ("*.md", "*.txt", "*.pdf"):
            candidates.extend(sorted(sample_path.rglob(ext)))
        # If a PDF has already been converted to Markdown (same basename), ignore the PDF.
        md_stems = {p.stem for p in candidates if p.suffix.lower() in {".md", ".markdown"}}
        candidates = [p for p in candidates if not (p.suffix.lower() == ".pdf" and p.stem in md_stems)]
        if not candidates:
            raise ValueError(f"No .md/.txt/.pdf found under sample directory: {sample_path}")

        for p in candidates:
            try:
                doc = load_sample_document(p, max_pages=max_pages)
            except Exception:
                continue
            if not doc.strip():
                continue
            included.append(p)
            parts.append(f"\n\n===== SAMPLE FILE: {p.name} =====\n\n{doc}")

        combined = "".join(parts).strip()
        return combined, included

    # Single file
    return load_sample_document(sample_path, max_pages=max_pages), [sample_path]


def load_sample_document(sample_path: Path, *, max_pages: Optional[int] = None) -> str:
    """Load a sample paper for style cloning.

    Supported:
    - .pdf: extract embedded text (not OCR)
    - .md/.txt: read as text

    If your PDF is scanned (little/no embedded text), convert it to Markdown first
    with `app/pdfToMarkdown.py` and pass that Markdown as the sample.
    """

    sample_path = sample_path.expanduser().resolve()

    if sample_path.is_dir():
        parts: List[str] = []
        candidates = []
        for ext in ("*.md", "*.txt", "*.pdf"):
            candidates.extend(sorted(sample_path.rglob(ext)))
        # If a PDF has already been converted to Markdown (same basename), ignore the PDF.
        md_stems = {p.stem for p in candidates if p.suffix.lower() in {".md", ".markdown"}}
        candidates = [p for p in candidates if not (p.suffix.lower() == ".pdf" and p.stem in md_stems)]
        if not candidates:
            raise ValueError(f"No .md/.txt/.pdf found under sample directory: {sample_path}")

        for p in candidates:
            try:
                doc = load_sample_document(p, max_pages=max_pages)
            except Exception:
                continue
            if not doc.strip():
                continue
            parts.append(f"\n\n===== SAMPLE FILE: {p.name} =====\n\n{doc}")

        combined = "".join(parts).strip()
        return combined

    suffix = sample_path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return _read_text_file(sample_path)

    if suffix == ".pdf":
        # Prefer a sibling markdown if this PDF was already converted.
        md_path = sample_path.with_suffix(".md")
        if md_path.exists():
            return _read_text_file(md_path)
        texts = extract_text_from_pdf(sample_path, max_pages=max_pages)
        combined = "\n\n".join([t for t in texts if t])
        return combined.strip()

    raise ValueError(f"Unsupported sample type: {suffix}. Use .pdf, .md, or .txt")


def default_topic_prompt_from_sample(sample_text: str) -> str:
    sample_text = sample_text.strip()
    if not sample_text:
        return "Generate a new mock exam/assignment aligned with the same course topics and difficulty as the provided sample."
    # Keep a compact hint from the first part of the sample.
    head = sample_text[:1500]
    return (
        "Generate a new mock exam/assignment aligned with the same course (same topic coverage, difficulty, and expectations) as the provided sample. "
        "Do not reuse identical questions; create new ones in the same style.\n\n"
        "Sample excerpt (for topic alignment only):\n"
        + head
    )


@dataclass(frozen=True)
class ExamSpec:
    num_questions: int
    ratios: Dict[str, float]
    language: str = "auto"


def parse_ratios(ratios_str: str) -> Dict[str, float]:
    """Parse ratios from strings like 'mcq:0.3,short:0.4,code:0.3'."""
    ratios: Dict[str, float] = {}
    for part in ratios_str.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError("Invalid ratios format. Expected key:value pairs.")
        k, v = part.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        ratios[k] = float(v)

    if not ratios:
        raise ValueError("No ratios provided")

    total = sum(ratios.values())
    if total <= 0:
        raise ValueError("Ratios must sum to > 0")

    # Normalize to sum=1
    return {k: (val / total) for k, val in ratios.items()}


def _safe_json_loads(s: str) -> Dict[str, Any]:
    """Best-effort JSON object parsing.

    Models sometimes:
    - wrap JSON in ```json fences
    - prepend/append short commentary
    - return multiple blocks; we want the first JSON object
    """

    s = (s or "").strip().lstrip("\ufeff")
    if not s:
        raise ValueError("empty json")

    # If fenced, prefer the fenced content.
    if "```" in s:
        m = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.IGNORECASE | re.DOTALL)
        if m:
            s = (m.group(1) or "").strip()

    # Remove a leading language token line like: json\n{...}
    lines = s.splitlines()
    if lines and lines[0].strip().lower() in {"json"}:
        s = "\n".join(lines[1:]).strip()

    # 1) direct parse
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("json is not an object")
        return obj
    except Exception:
        pass

    # 2) raw_decode starting at first '{'
    start = s.find("{")
    if start >= 0:
        dec = json.JSONDecoder()
        obj, _end = dec.raw_decode(s[start:])
        if not isinstance(obj, dict):
            raise ValueError("json is not an object")
        return obj

    raise ValueError("unable to parse json")


def _repair_json_with_ark(
    provider: str,
    client: Any,
    *,
    model: str,
    bad_text: str,
    temperature: Optional[float] = None,
) -> str:
    """Ask the model to rewrite an output into strict JSON only."""

    system = "You fix and normalize JSON. Output STRICT JSON only, no markdown, no commentary."
    user = (
        "Rewrite the following content into a single STRICT JSON object. "
        "Do not add any keys that are not present unless required to make valid JSON.\n\n"
        "[CONTENT START]\n" + (bad_text or "") + "\n[CONTENT END]"
    )

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _chat_complete_text(
        provider=provider,
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        show_progress=False,
    )


def _parse_or_repair_json(
    *,
    provider: str,
    client: Any,
    model: str,
    content: str,
    required_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parse JSON robustly and retry once with repair prompt if needed."""

    required_keys = required_keys or []

    # 1) direct parse
    try:
        obj = _safe_json_loads(content)
        if all(k in obj for k in required_keys):
            return obj
    except Exception:
        pass

    # 2) one repair round-trip
    fixed = _repair_json_with_ark(provider, client, model=model, bad_text=content, temperature=0.0)
    obj = _safe_json_loads(fixed)
    return obj


def _coerce_exam_json_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common key variations returned by different models."""
    out = dict(obj)

    if "paper_md" not in out:
        for k in ("paper", "exam", "exam_md", "questions_md"):
            if k in out and str(out.get(k) or "").strip():
                out["paper_md"] = out[k]
                break

    if "answers_md" not in out:
        for k in ("answers", "answer", "solution", "solutions_md", "answer_key"):
            if k in out and str(out.get(k) or "").strip():
                out["answers_md"] = out[k]
                break

    if "combined_md" not in out:
        for k in ("combined", "markdown", "md", "exam_markdown"):
            if k in out and str(out.get(k) or "").strip():
                out["combined_md"] = out[k]
                break

    return out


def analyze_style_with_ark(
    sample_text: str,
    *,
    model: str,
    extra_instructions: str = "",
    temperature: Optional[float] = None,
    show_progress: bool = False,
    on_progress_tokens: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    provider, client = _build_client()

    system = (
        "You are an exam-paper style analyzer. "
        "Given a sample exam/assignment paper, infer its formatting and structure. "
        "Return STRICT JSON only (no markdown, no commentary). "
        "Your output must be valid RFC8259 JSON: double-quoted keys/strings, no trailing commas, no comments, no code fences."
    )

    user = (
        "Analyze this sample paper and return a JSON object with keys:\n"
        "- language: 'zh'|'en'|'mixed'|'auto'\n"
        "- heading_style: e.g. '### Section A' or 'Part I'\n"
        "- numbering_style: e.g. '1.', 'Q1', '(1)'\n"
        "- question_types: array of objects: {type, cues, typical_points} where type in ['mcq','short','code','analysis','fill']\n"
        "- typical_sections: array of section titles in order\n"
        "- tone: brief description\n"
        "- constraints: array of constraints (e.g., time limit, allowed materials, formatting rules)\n"
        "- formatting_notes: array of short bullet-like notes\n"
        "\nIf the sample is not an exam (or too incomplete), still return best-effort JSON.\n"
        "\nJSON output rules (MANDATORY):\n"
        "1) Output ONE JSON object only.\n"
        "2) No prose before/after JSON.\n"
        "3) No markdown fences.\n"
        "4) Escape internal newlines as \\n inside string values.\n"
        "5) Ensure all required keys exist; use empty string/array when unknown.\n"
        "6) Before finalizing, self-validate that JSON parses with a standard parser.\n"
    )
    if extra_instructions.strip():
        user += "\nAdditional user format instructions:\n" + extra_instructions.strip() + "\n"

    # Keep sample bounded
    if len(sample_text) > 30000:
        sample_text = sample_text[:30000] + "\n...(truncated)"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user + "\n\n[SAMPLE START]\n" + sample_text + "\n[SAMPLE END]"},
    ]

    content = _chat_complete_text(
        provider=provider,
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        show_progress=show_progress,
        progress_label="style",
        on_progress_tokens=on_progress_tokens,
    )
    try:
        return _safe_json_loads(content)
    except Exception as e:
        # Retry once by asking the model to repair/normalize the JSON.
        try:
            fixed = _repair_json_with_ark(provider, client, model=model, bad_text=content, temperature=0.0)
            return _safe_json_loads(fixed)
        except Exception:
            head = (content or "").strip().replace("\n", " ")[:300]
            raise RuntimeError(
                "Style analysis did not return valid JSON. "
                "Consider reducing sample length, adding format constraints, or using a different model. "
                f"Model output head: {head}"
            ) from e


def generate_exam_with_ark(
    *,
    model: str,
    style_profile: Dict[str, Any],
    topic_prompt: str,
    spec: ExamSpec,
    custom_format_prompt: str = "",
    temperature: Optional[float] = None,
    show_progress: bool = False,
    on_progress_tokens: Optional[Callable[[int], None]] = None,
) -> Tuple[str, str]:
    """Return (paper_markdown, answers_markdown)."""

    provider, client = _build_client()

    system = (
        "You are a professor-simulator that generates high-quality mock exams. "
        "You MUST follow the provided style profile. "
        "Output STRICT JSON only with keys: paper_md, answers_md. "
        "Your output must be valid RFC8259 JSON with double quotes, no trailing commas, no comments, and no markdown fences."
    )

    ratio_lines = "\n".join([f"- {k}: {v:.2%}" for k, v in spec.ratios.items()])

    user = (
        "Generate a mock exam and a separate standard answer key.\n"
        "Requirements:\n"
        "- Few-shot style cloning: match the sample's structure, wording, and difficulty.\n"
        "- Fine-grained control: follow the question-type ratios and total question count.\n"
        "- Double independent output: return paper and answers as separate markdown strings.\n"
        "- Answers MUST be step-by-step and must not skip algebraic/probabilistic/statistical steps.\n"
        "- If you use a theorem/lemma/result (e.g., Yule–Walker, invertibility/stationarity conditions, Slutsky, CLT, etc.), state it and briefly explain why it applies.\n"
        "- Keep answers complete and unambiguous. If the sample style is terse, you may keep prose concise, but never omit essential steps.\n"
        "- For MCQ: give the correct option plus a short step-by-step justification (1–4 bullets).\n"
        "\nExam spec:\n"
        f"- num_questions: {spec.num_questions}\n"
        f"- ratios:\n{ratio_lines}\n"
        f"- language: {spec.language}\n"
        "\nTopic/syllabus prompt (authoritative):\n"
        f"{topic_prompt.strip()}\n"
        "\nStyle profile JSON (authoritative):\n"
        f"{json.dumps(style_profile, ensure_ascii=False)}\n"
    )

    if custom_format_prompt.strip():
        user += "\nUser custom format instructions (override defaults when conflicting):\n" + custom_format_prompt.strip() + "\n"

    user += (
        "\nOutput format:\n"
        "Return STRICT JSON only:\n"
        "{\n"
        "  \"paper_md\": \"...GitHub-flavored Markdown...\",\n"
        "  \"answers_md\": \"...GitHub-flavored Markdown...\"\n"
        "}\n"
        "Do not wrap in code fences.\n"
        "JSON output rules (MANDATORY):\n"
        "- Output ONE JSON object only, no extra text.\n"
        "- Escape all internal newlines inside strings as \\n.\n"
        "- If unsure, still emit valid JSON using empty strings rather than malformed output.\n"
        "- Before finalizing, self-check that json.loads(output) would succeed."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    content = _chat_complete_text(
        provider=provider,
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        show_progress=show_progress,
        progress_label="exam",
        on_progress_tokens=on_progress_tokens,
    )

    try:
        obj = _parse_or_repair_json(
            provider=provider,
            client=client,
            model=model,
            content=content,
            required_keys=["paper_md", "answers_md"],
        )
        obj = _coerce_exam_json_keys(obj)
    except Exception as e:
        head = (content or "").strip().replace("\n", " ")[:300]
        raise RuntimeError(
            "Exam generation did not return valid JSON. "
            "Consider lowering temperature or simplifying the prompt. "
            f"Model output head: {head}"
        ) from e

    paper_md = str(obj.get("paper_md", ""))
    answers_md = str(obj.get("answers_md", ""))
    if not paper_md.strip() or not answers_md.strip():
        raise RuntimeError("Model returned empty paper_md or answers_md")

    return paper_md, answers_md


def generate_inline_exam_with_ark(
    *,
    model: str,
    style_profile: Dict[str, Any],
    topic_prompt: str,
    spec: ExamSpec,
    custom_format_prompt: str = "",
    temperature: Optional[float] = None,
    show_progress: bool = False,
    on_progress_tokens: Optional[Callable[[int], None]] = None,
) -> str:
    """Return a single Markdown string with answers immediately after each question."""

    provider, client = _build_client()

    system = (
        "You are a professor-simulator that generates high-quality mock exams. "
        "You MUST follow the provided style profile. "
        "Output the final exam as GitHub-flavored Markdown only. "
        "Do not output JSON, code fences, XML, or commentary."
    )

    ratio_lines = "\n".join([f"- {k}: {v:.2%}" for k, v in spec.ratios.items()])

    user = (
        "Generate a mock exam in GitHub-flavored Markdown with INLINE ANSWERS.\n"
        "Requirements:\n"
        "- Few-shot style cloning: match the sample's structure, wording, and difficulty.\n"
        "- Fine-grained control: follow the question-type ratios and total question count.\n"
        "- Single output: one markdown string only.\n"
        "- IMPORTANT: Put the answer immediately after each question.\n"
        "  Use a consistent marker like '**Answer:**' and then a '**Solution (step-by-step):**' section.\n"
        "- Solutions MUST be step-by-step and must not skip steps (show intermediate equations and reasoning).\n"
        "- If you use a theorem/lemma/result, state it and briefly explain why it applies (only when necessary, but do not omit).\n"
        "- For MCQ: still include a brief step-by-step justification (1–4 bullets) right after '**Answer:**'.\n"
        "- Keep answers complete and unambiguous. If the sample style is terse, you may keep prose concise, but never omit essential steps.\n"
        "\nExam spec:\n"
        f"- num_questions: {spec.num_questions}\n"
        f"- ratios:\n{ratio_lines}\n"
        f"- language: {spec.language}\n"
        "\nTopic/syllabus prompt (authoritative):\n"
        f"{topic_prompt.strip()}\n"
        "\nStyle profile JSON (authoritative):\n"
        f"{json.dumps(style_profile, ensure_ascii=False)}\n"
    )

    if custom_format_prompt.strip():
        user += "\nUser custom format instructions (override defaults when conflicting):\n" + custom_format_prompt.strip() + "\n"

    user += (
        "\nOutput format (MANDATORY):\n"
        "- Output GitHub-flavored Markdown directly (plain text).\n"
        "- NO JSON.\n"
        "- NO code fences like ```markdown.\n"
        "- NO preface or explanation text.\n"
        "- Start immediately with the exam title/heading."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    content = _chat_complete_text(
        provider=provider,
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        show_progress=show_progress,
        progress_label="exam",
        on_progress_tokens=on_progress_tokens,
    )

    combined_md = (content or "").strip()

    # If the model wrapped markdown in a code fence, unwrap it.
    if combined_md.startswith("```"):
        lines = combined_md.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        combined_md = "\n".join(lines).strip()

    if not combined_md.strip():
        raise RuntimeError("Model returned empty combined_md")

    return combined_md


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Professor simulator: learn style from a sample paper and generate a mock exam + answer key."
    )
    parser.add_argument(
        "--sample",
        required=True,
        help="Path to sample paper (.pdf/.md/.txt) used for few-shot style cloning",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Topic/syllabus prompt for the exam content (optional; defaults to inferred from sample)",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--name",
        default="mock_exam",
        help="Base filename (creates <name>_paper.md and <name>_answers.md)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MOCKPAPER_MODEL", "MiniMax-M2.5"),
        help="Model name for selected provider (default: env MOCKPAPER_MODEL or MiniMax-M2.5)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Only consider the first N pages of the sample when sample is a PDF",
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        default=True,
        help="Print which sample files were read/included (useful when --sample is a directory).",
    )
    parser.add_argument(
        "--num-questions",
        type=int,
        default=10,
        help="Total number of questions",
    )
    parser.add_argument(
        "--ratios",
        default="mcq:0.3,short:0.4,code:0.3",
        help="Question type ratios, e.g. 'mcq:0.3,short:0.4,code:0.3'",
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="Desired language: zh/en/mixed/auto",
    )
    parser.add_argument(
        "--format-prompt",
        default="",
        help="Optional custom formatting instructions to override the cloned style",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional model temperature",
    )
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="Only analyze and print the inferred style profile (no exam generation)",
    )
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Write two files (<name>_paper.md and <name>_answers.md) instead of a single combined markdown.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        default=True,
        help="Show a live progress bar with estimated tokens/sec while receiving model output (requires streaming).",
    )

    args = parser.parse_args()

    sample_path = Path(args.sample)
    sample_text, included_files = load_sample_document_with_manifest(
        sample_path, max_pages=args.max_pages
    )
    if args.show_files:
        print("Sample files included:")
        for p in included_files:
            try:
                size = p.stat().st_size
                print(f"- {p} ({size} bytes)")
            except Exception:
                print(f"- {p}")
    if not sample_text.strip():
        raise RuntimeError(
            "Sample contains no extractable text. If it's a scanned PDF, convert it to Markdown first using app/pdfToMarkdown.py and pass the .md file."
        )

    style = analyze_style_with_ark(
        sample_text,
        model=args.model,
        extra_instructions=args.format_prompt,
        temperature=args.temperature,
        show_progress=args.progress,
    )

    if args.style_only:
        print(json.dumps(style, ensure_ascii=False, indent=2))
        return 0

    topic_prompt = args.topic if args.topic is not None else default_topic_prompt_from_sample(sample_text)

    spec = ExamSpec(
        num_questions=int(args.num_questions),
        ratios=parse_ratios(args.ratios),
        language=str(args.language),
    )

    paper_md, answers_md = generate_exam_with_ark(
        model=args.model,
        style_profile=style,
        topic_prompt=topic_prompt,
        spec=spec,
        custom_format_prompt=args.format_prompt,
        temperature=args.temperature,
        show_progress=args.progress,
    ) if args.separate else ("", "")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.separate:
        paper_path = out_dir / f"{args.name}_paper.md"
        answers_path = out_dir / f"{args.name}_answers.md"

        paper_path.write_text(paper_md, encoding="utf-8")
        answers_path.write_text(answers_md, encoding="utf-8")

        print(
            json.dumps(
                {"paper": str(paper_path), "answers": str(answers_path)},
                ensure_ascii=False,
            )
        )
        return 0

    combined_md = generate_inline_exam_with_ark(
        model=args.model,
        style_profile=style,
        topic_prompt=topic_prompt,
        spec=spec,
        custom_format_prompt=args.format_prompt,
        temperature=args.temperature,
        show_progress=args.progress,
    )

    out_path = out_dir / f"{args.name}.md"
    out_path.write_text(combined_md, encoding="utf-8")
    print(json.dumps({"markdown": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
