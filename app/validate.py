import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import anthropic
from volcenginesdkarkruntime import Ark

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


DEFAULT_PRIMARY_MODEL = "deepseek-v3-2-251201"
DEFAULT_SECONDARY_MODEL = "doubao-seed-2-0-pro-260215"

MINIMAX_TEXT_MODELS = ["MiniMax-M2.5"]


@dataclass(frozen=True)
class CodeBlock:
    language: str
    code: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ValidationResult:
    file_path: Path
    block: CodeBlock
    status: str  # ok|failed|skipped
    stdout: str
    stderr: str
    returncode: Optional[int]
    note: str = ""


@dataclass(frozen=True)
class MockPaperCheck:
    base_name: str
    paper_path: Path
    answers_path: Path
    status: str  # ok|failed
    issues: List[str]


def _require_ark_api_key() -> str:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing ARK_API_KEY. Set it in your shell (export ARK_API_KEY=...)."
        )
    return api_key


def _require_minimax_api_key() -> str:
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing MINIMAX_API_KEY (or ANTHROPIC_API_KEY). Set it in your shell (or .env)."
        )
    return api_key


def _provider_for_model(model: str) -> str:
    m = str(model or "").strip()
    if m in MINIMAX_TEXT_MODELS:
        return "minimax"
    return "ark"


def _build_client_for_model(model: str):
    provider = _provider_for_model(model)
    if provider == "ark":
        return provider, Ark(api_key=_require_ark_api_key())
    api_key = _require_minimax_api_key()
    base_url = str(os.environ.get("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic").strip()
    return provider, anthropic.Anthropic(api_key=api_key, base_url=base_url)


def _complete_text(
    *,
    provider: str,
    client,
    model: str,
    system: str,
    user: str,
    temperature: Optional[float] = None,
) -> str:
    if provider == "ark":
        payload: Dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        resp = client.chat.completions.create(**payload)
        return resp.choices[0].message.content or ""  # type: ignore[attr-defined]

    payload2: Dict[str, object] = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if temperature is not None:
        payload2["temperature"] = temperature
    msg = client.messages.create(**payload2)
    parts: List[str] = []
    for block in (msg.content or []):
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def _safe_json_loads(s: str) -> Dict[str, object]:
    s = (s or "").strip().lstrip("\ufeff")
    if not s:
        raise ValueError("empty json")

    if "```" in s:
        m = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.IGNORECASE | re.DOTALL)
        if m:
            s = (m.group(1) or "").strip()

    lines = s.splitlines()
    if lines and lines[0].strip().lower() in {"json"}:
        s = "\n".join(lines[1:]).strip()

    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("json is not an object")
        return obj
    except Exception:
        pass

    start = s.find("{")
    if start >= 0:
        dec = json.JSONDecoder()
        obj, _end = dec.raw_decode(s[start:])
        if not isinstance(obj, dict):
            raise ValueError("json is not an object")
        return obj

    raise ValueError("unable to parse json")


def _coerce_verdict(v: object) -> str:
    vv = str(v or "").strip().lower()
    if vv in {"correct", "ok", "pass", "true"}:
        return "correct"
    if vv in {"incorrect", "wrong", "fail", "false"}:
        return "incorrect"
    return "uncertain"


def _truncate_text(s: str, *, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars]


def llm_review_mock_pair(
    *,
    base: str,
    paper_path: Path,
    answers_path: Path,
    main_model: str,
    sub_model: str,
    temperature: Optional[float] = None,
    max_context_chars: int = 60_000,
    write_revisions: bool = True,
) -> Dict[str, object]:
    paper = paper_path.read_text(encoding="utf-8", errors="ignore")
    answers = answers_path.read_text(encoding="utf-8", errors="ignore")

    paper = _truncate_text(paper, max_chars=max_context_chars)
    answers = _truncate_text(answers, max_chars=max_context_chars)

    system = (
        "You are a rigorous exam validator and editor. "
        "Given an exam paper and an answer key, verify that the answers match the questions and are internally consistent. "
        "If something cannot be verified from the given text, mark it as uncertain (do not guess)."
    )
    user = (
        "Return STRICT JSON only (no markdown, no commentary).\n"
        "Keys: verdict (correct|incorrect|uncertain), issues (array of strings), revised_paper_md (string), revised_answers_md (string).\n"
        "- If verdict is correct, revised_* can be empty strings.\n"
        "- If verdict is incorrect, provide corrected revised_* markdown.\n\n"
        f"[PAPER START]\n{paper}\n[PAPER END]\n\n"
        f"[ANSWERS START]\n{answers}\n[ANSWERS END]\n"
    )

    main_provider, main_client = _build_client_for_model(main_model)
    main_raw = _complete_text(
        provider=main_provider,
        client=main_client,
        model=main_model,
        system=system,
        user=user,
        temperature=temperature,
    )
    try:
        main_obj = _safe_json_loads(main_raw)
    except Exception:
        main_obj = {
            "verdict": "uncertain",
            "issues": ["main model did not return valid JSON"],
            "revised_paper_md": "",
            "revised_answers_md": "",
            "raw": main_raw,
        }

    verdict = _coerce_verdict(main_obj.get("verdict"))

    sub_obj: Dict[str, object] = {}
    consensus_obj: Dict[str, object] = dict(main_obj)

    if verdict != "correct" and sub_model:
        sub_provider, sub_client = _build_client_for_model(sub_model)
        sub_system = (
            "You are the challenger validator. Your job is to critique the main validator's findings and proposed revisions. "
            "Identify mistakes, missing cases, and propose a better revision if needed."
        )
        sub_user = (
            "Return STRICT JSON only.\n"
            "Keys: disagreements (array of strings), improved_revised_paper_md (string), improved_revised_answers_md (string).\n\n"
            f"Main validator JSON:\n{json.dumps(main_obj, ensure_ascii=False)}\n\n"
            f"[PAPER START]\n{paper}\n[PAPER END]\n\n"
            f"[ANSWERS START]\n{answers}\n[ANSWERS END]\n"
        )
        sub_raw = _complete_text(
            provider=sub_provider,
            client=sub_client,
            model=sub_model,
            system=sub_system,
            user=sub_user,
            temperature=temperature,
        )
        try:
            sub_obj = _safe_json_loads(sub_raw)
        except Exception:
            sub_obj = {"disagreements": ["sub model did not return valid JSON"], "raw": sub_raw}

        consensus_system = (
            "You are the final consensus validator. Reconcile main + challenger outputs and produce a final decision and final revised markdown. "
            "If something cannot be verified, choose verdict=uncertain."
        )
        consensus_user = (
            "Return STRICT JSON only.\n"
            "Keys: verdict (correct|incorrect|uncertain), issues (array of strings), revised_paper_md (string), revised_answers_md (string), summary (string).\n\n"
            f"Main validator JSON:\n{json.dumps(main_obj, ensure_ascii=False)}\n\n"
            f"Challenger JSON:\n{json.dumps(sub_obj, ensure_ascii=False)}\n\n"
            f"[PAPER START]\n{paper}\n[PAPER END]\n\n"
            f"[ANSWERS START]\n{answers}\n[ANSWERS END]\n"
        )
        consensus_raw = _complete_text(
            provider=main_provider,
            client=main_client,
            model=main_model,
            system=consensus_system,
            user=consensus_user,
            temperature=temperature,
        )
        try:
            consensus_obj = _safe_json_loads(consensus_raw)
        except Exception:
            consensus_obj = dict(main_obj)
            _existing_issues = consensus_obj.get("issues")
            if isinstance(_existing_issues, list):
                _issues_list = [str(x) for x in _existing_issues]
            else:
                _issues_list = []
            consensus_obj["issues"] = _issues_list + ["consensus did not return valid JSON"]
            consensus_obj["raw"] = consensus_raw

    revised_paper = str(consensus_obj.get("revised_paper_md") or "")
    revised_answers = str(consensus_obj.get("revised_answers_md") or "")
    revised_paths: Dict[str, str] = {}
    if write_revisions and (revised_paper.strip() or revised_answers.strip()):
        out_dir = paper_path.parent / "validate_revisions"
        out_dir.mkdir(parents=True, exist_ok=True)
        if revised_paper.strip():
            rp = out_dir / f"{base}_paper_revised.md"
            rp.write_text(revised_paper, encoding="utf-8")
            revised_paths["paper"] = str(rp)
        if revised_answers.strip():
            ra = out_dir / f"{base}_answers_revised.md"
            ra.write_text(revised_answers, encoding="utf-8")
            revised_paths["answers"] = str(ra)

    return {
        "type": "pair",
        "base": base,
        "paper": str(paper_path),
        "answers": str(answers_path),
        "main_model": main_model,
        "sub_model": sub_model,
        "verdict": _coerce_verdict(consensus_obj.get("verdict")),
        "issues": consensus_obj.get("issues") or [],
        "summary": consensus_obj.get("summary") or "",
        "revisions": revised_paths,
        "main": main_obj,
        "sub": sub_obj,
    }


def llm_review_mock_combined(
    *,
    md_path: Path,
    main_model: str,
    sub_model: str,
    temperature: Optional[float] = None,
    max_context_chars: int = 60_000,
    write_revisions: bool = True,
) -> Dict[str, object]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    text = _truncate_text(text, max_chars=max_context_chars)

    system = (
        "You are a rigorous mockpaper validator and editor. "
        "The document contains questions and inline answers. Verify correctness and internal consistency. "
        "If you cannot verify from the text, mark uncertain and avoid guessing."
    )
    user = (
        "Return STRICT JSON only.\n"
        "Keys: verdict (correct|incorrect|uncertain), issues (array of strings), revised_markdown (string).\n"
        "- If verdict is correct, revised_markdown can be empty.\n"
        "- If incorrect, provide a full revised_markdown.\n\n"
        f"[DOC START]\n{text}\n[DOC END]\n"
    )

    main_provider, main_client = _build_client_for_model(main_model)
    main_raw = _complete_text(
        provider=main_provider,
        client=main_client,
        model=main_model,
        system=system,
        user=user,
        temperature=temperature,
    )
    try:
        main_obj = _safe_json_loads(main_raw)
    except Exception:
        main_obj = {
            "verdict": "uncertain",
            "issues": ["main model did not return valid JSON"],
            "revised_markdown": "",
            "raw": main_raw,
        }

    verdict = _coerce_verdict(main_obj.get("verdict"))
    sub_obj: Dict[str, object] = {}
    consensus_obj: Dict[str, object] = dict(main_obj)

    if verdict != "correct" and sub_model:
        sub_provider, sub_client = _build_client_for_model(sub_model)
        sub_system = (
            "You are the challenger validator. Critique the main validator's findings and proposed revision. "
            "Propose a better revision if needed."
        )
        sub_user = (
            "Return STRICT JSON only.\n"
            "Keys: disagreements (array of strings), improved_revised_markdown (string).\n\n"
            f"Main validator JSON:\n{json.dumps(main_obj, ensure_ascii=False)}\n\n"
            f"[DOC START]\n{text}\n[DOC END]\n"
        )
        sub_raw = _complete_text(
            provider=sub_provider,
            client=sub_client,
            model=sub_model,
            system=sub_system,
            user=sub_user,
            temperature=temperature,
        )
        try:
            sub_obj = _safe_json_loads(sub_raw)
        except Exception:
            sub_obj = {"disagreements": ["sub model did not return valid JSON"], "raw": sub_raw}

        consensus_system = (
            "You are the final consensus validator. Reconcile main + challenger outputs and produce a final decision and final revised markdown. "
            "If something cannot be verified, choose verdict=uncertain."
        )
        consensus_user = (
            "Return STRICT JSON only.\n"
            "Keys: verdict (correct|incorrect|uncertain), issues (array of strings), revised_markdown (string), summary (string).\n\n"
            f"Main validator JSON:\n{json.dumps(main_obj, ensure_ascii=False)}\n\n"
            f"Challenger JSON:\n{json.dumps(sub_obj, ensure_ascii=False)}\n\n"
            f"[DOC START]\n{text}\n[DOC END]\n"
        )
        consensus_raw = _complete_text(
            provider=main_provider,
            client=main_client,
            model=main_model,
            system=consensus_system,
            user=consensus_user,
            temperature=temperature,
        )
        try:
            consensus_obj = _safe_json_loads(consensus_raw)
        except Exception:
            consensus_obj = dict(main_obj)
            _existing_issues = consensus_obj.get("issues")
            if isinstance(_existing_issues, list):
                _issues_list = [str(x) for x in _existing_issues]
            else:
                _issues_list = []
            consensus_obj["issues"] = _issues_list + ["consensus did not return valid JSON"]
            consensus_obj["raw"] = consensus_raw

    revised_md = str(consensus_obj.get("revised_markdown") or "")
    revised_path: Optional[str] = None
    if write_revisions and revised_md.strip():
        out_dir = md_path.parent / "validate_revisions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{md_path.stem}_revised.md"
        out_path.write_text(revised_md, encoding="utf-8")
        revised_path = str(out_path)

    return {
        "type": "combined",
        "file": str(md_path),
        "main_model": main_model,
        "sub_model": sub_model,
        "verdict": _coerce_verdict(consensus_obj.get("verdict")),
        "issues": consensus_obj.get("issues") or [],
        "summary": consensus_obj.get("summary") or "",
        "revision": revised_path,
        "main": main_obj,
        "sub": sub_obj,
    }


def iter_markdown_files(sources_dir: Path) -> List[Path]:
    sources_dir = sources_dir.expanduser().resolve()
    if not sources_dir.exists():
        raise FileNotFoundError(str(sources_dir))
    files = sorted([p for p in sources_dir.rglob("*.md") if p.is_file()])
    return files


def discover_mock_pairs(sources_dir: Path) -> List[Tuple[str, Path, Path]]:
    """Discover pairs like <name>_paper.md and <name>_answers.md."""
    sources_dir = sources_dir.expanduser().resolve()
    papers = sorted(sources_dir.rglob("*_paper.md"))
    pairs: List[Tuple[str, Path, Path]] = []
    for paper in papers:
        base = paper.name[: -len("_paper.md")]
        answers = paper.with_name(base + "_answers.md")
        if answers.exists() and answers.is_file():
            pairs.append((base, paper, answers))
    return pairs


def discover_mock_combined_files(sources_dir: Path) -> List[Path]:
    """Discover single-file mock outputs under sources/mockpaper/ (excluding *_paper/_answers)."""
    sources_dir = sources_dir.expanduser().resolve()
    mock_dir = sources_dir / "mockpaper"
    if not mock_dir.exists():
        return []
    files = []
    for p in sorted(mock_dir.rglob("*.md")):
        name = p.name
        if name.endswith("_paper.md") or name.endswith("_answers.md"):
            continue
        files.append(p)
    return files


_FENCE_RE = re.compile(
    r"^```(?P<lang>[a-zA-Z0-9_+-]*)\s*$|^```\s*$", re.MULTILINE
)


def extract_fenced_code_blocks(markdown_text: str) -> List[CodeBlock]:
    """Extract fenced code blocks and approximate line ranges."""
    lines = markdown_text.splitlines()
    blocks: List[CodeBlock] = []

    in_block = False
    lang = ""
    buf: List[str] = []
    start_line = 0

    for idx, line in enumerate(lines, start=1):
        if not in_block:
            m = re.match(r"^```\s*([a-zA-Z0-9_+-]*)\s*$", line)
            if m:
                in_block = True
                lang = (m.group(1) or "").strip().lower()
                buf = []
                start_line = idx
            continue

        # in block
        if re.match(r"^```\s*$", line):
            code = "\n".join(buf).rstrip() + "\n" if buf else ""
            blocks.append(
                CodeBlock(language=lang, code=code, start_line=start_line, end_line=idx)
            )
            in_block = False
            lang = ""
            buf = []
            start_line = 0
        else:
            buf.append(line)

    return blocks


_QUESTION_RE = re.compile(r"^\s*(?P<n>\d{1,3})\.\s+", re.MULTILINE)


def extract_numbered_items(md_text: str) -> List[int]:
    return [int(m.group("n")) for m in _QUESTION_RE.finditer(md_text)]


def find_fullwidth_digits(md_text: str) -> List[str]:
    """Flag fullwidth digits which frequently break LaTeX (e.g., theta_２)."""
    fullwidth = set("０１２３４５６７８９")
    hits: List[str] = []
    for i, line in enumerate(md_text.splitlines(), start=1):
        if any(ch in fullwidth for ch in line):
            # Keep it short
            snippet = line.strip()
            if len(snippet) > 120:
                snippet = snippet[:120] + "…"
            hits.append(f"line {i}: contains fullwidth digit(s): {snippet}")
    return hits


def validate_mock_pair(base: str, paper_path: Path, answers_path: Path) -> MockPaperCheck:
    paper = paper_path.read_text(encoding="utf-8", errors="ignore")
    answers = answers_path.read_text(encoding="utf-8", errors="ignore")

    issues: List[str] = []

    paper_qs = extract_numbered_items(paper)
    ans_qs = extract_numbered_items(answers)

    if not paper_qs:
        issues.append("paper: no numbered questions detected (expected '1. ...')")
    if not ans_qs:
        issues.append("answers: no numbered items detected (expected '1. ...')")

    paper_set = set(paper_qs)
    ans_set = set(ans_qs)

    missing = sorted(paper_set - ans_set)
    extra = sorted(ans_set - paper_set)
    if missing:
        issues.append(f"answers missing question numbers: {missing}")
    if extra:
        issues.append(f"answers contains extra question numbers not in paper: {extra}")

    if paper_qs:
        expected = list(range(1, max(paper_qs) + 1))
        if sorted(paper_set) != expected:
            issues.append(
                f"paper question numbering not contiguous from 1..{max(paper_qs)}: found {sorted(paper_set)}"
            )

    # Minimal MCQ sanity: for the first 3 questions, ensure A-D options exist.
    for q in (1, 2, 3):
        if f"{q}." in paper:
            for opt in ("A.", "B.", "C.", "D."):
                if opt not in paper:
                    issues.append(f"paper: missing MCQ option marker '{opt}' (global check)")
                    break

    # LaTeX/unicode issues
    fw_paper = find_fullwidth_digits(paper)
    fw_answers = find_fullwidth_digits(answers)
    if fw_paper:
        issues.append("paper: fullwidth digits found (may break LaTeX): " + fw_paper[0])
    if fw_answers:
        issues.append("answers: fullwidth digits found (may break LaTeX): " + fw_answers[0])

    status = "ok" if not issues else "failed"
    return MockPaperCheck(
        base_name=base,
        paper_path=paper_path,
        answers_path=answers_path,
        status=status,
        issues=issues,
    )


def validate_mock_combined(md_path: Path) -> Tuple[str, List[str]]:
    """Return (status, issues) for a combined mock markdown with inline answers."""
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    issues: List[str] = []

    q_nums = extract_numbered_items(text)
    if not q_nums:
        issues.append("no numbered questions detected (expected '1. ...')")
        return ("failed", issues)

    # Simple inline answer check: for each question, look for an Answer marker before the next question.
    lines = text.splitlines()
    q_line_idx: Dict[int, int] = {}
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(\d{1,3})\.\s+", line)
        if m:
            n = int(m.group(1))
            if n not in q_line_idx:
                q_line_idx[n] = i

    for n in sorted(q_line_idx.keys()):
        start = q_line_idx[n]
        # Search until next question or limited window
        next_starts = [idx for k, idx in q_line_idx.items() if k > n]
        end = min(next_starts) if next_starts else len(lines)
        end = min(end, start + 80)  # cap the scan

        window = "\n".join(lines[start:end]).lower()
        if "**answer:**" not in window and "answer:" not in window:
            issues.append(f"question {n}: missing inline answer marker ('Answer:') soon after question")

    fw = find_fullwidth_digits(text)
    if fw:
        issues.append("fullwidth digits found (may break LaTeX): " + fw[0])

    return ("ok" if not issues else "failed", issues)


def _build_runner(snippet_path: Path) -> str:
    """Return a runner program that sets rlimits then execs the snippet."""
    return textwrap.dedent(
        f"""
        import os
        import resource
        import runpy
        import sys

        # Resource limits (best-effort; may vary by platform)
        try:
            # CPU seconds
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        except Exception:
            pass

        try:
            # Address space (bytes) ~ 512MB
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except Exception:
            pass

        # Reduce environment exposure
        os.environ.clear()
        os.environ["PYTHONHASHSEED"] = "0"

        runpy.run_path({snippet_path!r}, run_name="__main__")
        """
    ).lstrip()


def run_python_in_sandbox(code: str, *, timeout_s: int = 8) -> Tuple[int, str, str]:
    """Run Python code in a temp dir with isolation-ish settings."""
    with tempfile.TemporaryDirectory(prefix="validate_sandbox_") as td:
        td_path = Path(td)
        snippet_path = td_path / "snippet.py"
        runner_path = td_path / "runner.py"

        snippet_path.write_text(code, encoding="utf-8")
        runner_path.write_text(_build_runner(snippet_path), encoding="utf-8")

        cmd = [
            sys.executable,
            "-I",  # isolated mode
            "-S",  # no 'site' import
            "-B",  # no .pyc
            str(runner_path),
        ]

        proc = subprocess.run(
            cmd,
            cwd=str(td_path),
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
        return proc.returncode, proc.stdout, proc.stderr


def _coerce_text(val: object) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, str):
        return val
    return str(val)


def build_memory_objects(md_text: str, *, max_chars: int = 8000) -> List[str]:
    """Create numbered memory snippets the debate loop can cite."""
    text = md_text.strip()
    if len(text) <= max_chars:
        return [text]

    # Chunk by headings first; fall back to fixed windows.
    parts: List[str] = []
    current: List[str] = []

    for line in text.splitlines():
        if line.startswith("#") and current:
            parts.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("\n".join(current).strip())

    out: List[str] = []
    for p in parts:
        if not p:
            continue
        if len(p) > max_chars:
            for i in range(0, len(p), max_chars):
                out.append(p[i : i + max_chars])
        else:
            out.append(p)

    return out


def debate_loop(
    *,
    memory_objects: List[str],
    failure_summary: str,
    primary_model: str,
    secondary_model: str,
    rounds: int = 2,
    temperature: Optional[float] = None,
) -> str:
    """Two-model cross debate. Returns a consensus report string."""

    api_key = _require_ark_api_key()
    client = Ark(api_key=api_key)

    mem = "\n\n".join([f"[M{i+1}]\n{m}" for i, m in enumerate(memory_objects)])

    base_instructions = (
        "You are participating in a rigorous validation debate. "
        "You MUST cite memory objects by ID (e.g., [M1], [M2]) when making claims. "
        "Focus on eliminating hallucinations and resolving logical ambiguity."
    )

    transcript: List[str] = []
    last_claim = ""

    for r in range(1, rounds + 1):
        # Model A proposes
        prompt_a = (
            f"{base_instructions}\n\n"
            "Task: Given the failure summary, propose the most likely root cause and a corrected solution/interpretation. "
            "Cite evidence from memory objects. Keep it concise and rigorous.\n\n"
            f"Failure summary:\n{failure_summary}\n\n"
            f"Memory objects:\n{mem}\n"
        )
        if last_claim:
            prompt_a += f"\nOpponent last claim:\n{last_claim}\n"

        resp_a = client.chat.completions.create(
            model=primary_model,
            messages=[{"role": "user", "content": prompt_a}],
            temperature=temperature,
        )
        claim_a = (resp_a.choices[0].message.content or "").strip()  # type: ignore[attr-defined]
        transcript.append(f"[Round {r}][{primary_model}]\n{claim_a}")

        # Model B critiques
        prompt_b = (
            f"{base_instructions}\n\n"
            "Task: Critique the opponent's claim for gaps, unstated assumptions, or contradictions. "
            "Then propose a refined, consensus-ready conclusion. Cite memory objects.\n\n"
            f"Failure summary:\n{failure_summary}\n\n"
            f"Memory objects:\n{mem}\n\n"
            f"Opponent claim:\n{claim_a}\n"
        )
        resp_b = client.chat.completions.create(
            model=secondary_model,
            messages=[{"role": "user", "content": prompt_b}],
            temperature=temperature,
        )
        claim_b = (resp_b.choices[0].message.content or "").strip()  # type: ignore[attr-defined]
        transcript.append(f"[Round {r}][{secondary_model}]\n{claim_b}")

        last_claim = claim_b

    consensus_prompt = (
        "You are to produce the final consensus result. "
        "Return a short structured report with: findings, evidence (memory citations), and recommended fix.\n\n"
        f"Failure summary:\n{failure_summary}\n\n"
        f"Debate transcript:\n" + "\n\n".join(transcript)
    )

    resp_c = client.chat.completions.create(
        model=primary_model,
        messages=[{"role": "user", "content": consensus_prompt}],
        temperature=temperature,
    )
    return (resp_c.choices[0].message.content or "").strip()  # type: ignore[attr-defined]


def validate_markdown_file(
    md_path: Path,
    *,
    run_code: bool = True,
) -> List[ValidationResult]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    blocks = extract_fenced_code_blocks(text)

    results: List[ValidationResult] = []
    for b in blocks:
        if b.language not in {"py", "python"}:
            results.append(
                ValidationResult(
                    file_path=md_path,
                    block=b,
                    status="skipped",
                    stdout="",
                    stderr="",
                    returncode=None,
                    note=f"language={b.language or 'plain'}",
                )
            )
            continue

        if not run_code or not b.code.strip():
            results.append(
                ValidationResult(
                    file_path=md_path,
                    block=b,
                    status="skipped",
                    stdout="",
                    stderr="",
                    returncode=None,
                    note="empty block",
                )
            )
            continue

        try:
            rc, out, err = run_python_in_sandbox(b.code)
            status = "ok" if rc == 0 else "failed"
            results.append(
                ValidationResult(
                    file_path=md_path,
                    block=b,
                    status=status,
                    stdout=out,
                    stderr=err,
                    returncode=rc,
                )
            )
        except subprocess.TimeoutExpired as e:
            results.append(
                ValidationResult(
                    file_path=md_path,
                    block=b,
                    status="failed",
                    stdout=_coerce_text(e.stdout),
                    stderr=_coerce_text(e.stderr) + "\nTimeoutExpired",
                    returncode=None,
                    note="timeout",
                )
            )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validation & consensus engine: sandbox-run code blocks and (optionally) trigger multi-model debate on failures."
    )
    parser.add_argument(
        "--sources-dir",
        default="sources",
        help="Directory containing markdown files (default: sources)",
    )
    parser.add_argument(
        "--no-code",
        action="store_true",
        help="Do not execute code blocks (still scans and reports).",
    )
    parser.add_argument(
        "--debate",
        action="store_true",
        help="On validation failure, trigger debate loop (requires ARK_API_KEY).",
    )
    parser.add_argument(
        "--primary-model",
        default=DEFAULT_PRIMARY_MODEL,
        help=f"Primary model for debate/consensus (default: {DEFAULT_PRIMARY_MODEL})",
    )
    parser.add_argument(
        "--secondary-model",
        default=DEFAULT_SECONDARY_MODEL,
        help=f"Secondary model for debate (default: {DEFAULT_SECONDARY_MODEL})",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Debate rounds (default: 2)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Also validate mock paper pairs (*_paper.md + *_answers.md) under sources-dir.",
    )
    args = parser.parse_args()

    sources_dir = Path(args.sources_dir)
    md_files = iter_markdown_files(sources_dir)

    print(f"Scanning {len(md_files)} markdown files in {sources_dir}...")

    all_results: List[ValidationResult] = []
    failures: List[ValidationResult] = []

    for md in md_files:
        results = validate_markdown_file(md, run_code=not args.no_code)
        all_results.extend(results)
        failures.extend([r for r in results if r.status == "failed"])

        python_blocks = [r for r in results if r.block.language in {"py", "python"}]
        ok_n = sum(1 for r in python_blocks if r.status == "ok")
        fail_n = sum(1 for r in python_blocks if r.status == "failed")
        print(f"- {md.name}: python_blocks={len(python_blocks)} ok={ok_n} failed={fail_n}")

    total_py = sum(1 for r in all_results if r.block.language in {"py", "python"})
    ok_total = sum(1 for r in all_results if r.status == "ok")
    failed_total = sum(1 for r in all_results if r.status == "failed")

    print(f"Summary: python_blocks={total_py} ok={ok_total} failed={failed_total} skipped={len(all_results) - ok_total - failed_total}")

    mock_failed = 0
    if args.mock:
        pairs = discover_mock_pairs(sources_dir)
        print(f"Mock pairs discovered: {len(pairs)}")
        for base, paper_path, answers_path in pairs:
            check = validate_mock_pair(base, paper_path, answers_path)
            if check.status == "ok":
                print(f"- {base}: ok")
            else:
                mock_failed += 1
                print(f"- {base}: FAILED")
                for issue in check.issues[:10]:
                    print(f"  - {issue}")

        combined = discover_mock_combined_files(sources_dir)
        print(f"Mock combined files discovered: {len(combined)}")
        for p in combined:
            status, issues = validate_mock_combined(p)
            if status == "ok":
                print(f"- {p.name}: ok")
            else:
                mock_failed += 1
                print(f"- {p.name}: FAILED")
                for issue in issues[:10]:
                    print(f"  - {issue}")

    if failures and args.debate:
        try:
            for f in failures:
                md_text = f.file_path.read_text(encoding="utf-8", errors="ignore")
                memory = build_memory_objects(md_text)
                failure_summary = (
                    f"File: {f.file_path}\n"
                    f"Code block lines: {f.block.start_line}-{f.block.end_line}\n"
                    f"Return code: {f.returncode}\n"
                    f"STDERR:\n{(f.stderr or '').strip()}\n"
                    f"STDOUT:\n{(f.stdout or '').strip()}\n"
                )
                print("\n=== Debate Loop Triggered ===")
                print(failure_summary)
                consensus = debate_loop(
                    memory_objects=memory,
                    failure_summary=failure_summary,
                    primary_model=args.primary_model,
                    secondary_model=args.secondary_model,
                    rounds=args.rounds,
                )
                print("\n=== Consensus Report ===")
                print(consensus)
        except RuntimeError as e:
            print(f"Debate skipped: {e}")

    any_failed = bool(failures) or (mock_failed > 0)
    return 0 if not any_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
