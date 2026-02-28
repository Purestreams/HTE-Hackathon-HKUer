"""Markdown to PDF via system pandoc.

Uses the system `pandoc` binary to render a Markdown file to PDF.

Reference command:
  pandoc input.md -V geometry:margin=1in -o output.pdf

Note: Pandoc typically requires a PDF engine (e.g., LaTeX) to be installed.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PandocResult:
	pdf_path: Path
	cached: bool
	elapsed_sec: float


def markdown_to_pdf(
	md_path: Path,
	pdf_path: Optional[Path] = None,
	*,
	margin: str = "1in",
	timeout_sec: int = 90,
) -> PandocResult:
	"""Convert Markdown file to PDF using `pandoc`.

	Args:
		md_path: Input markdown file path.
		pdf_path: Output PDF path. Defaults to md_path with .pdf suffix.
		margin: Margin passed via `-V geometry:margin=<margin>`.
		timeout_sec: Subprocess timeout.
	"""

	md_path = Path(md_path).expanduser().resolve()
	if not md_path.exists() or not md_path.is_file():
		raise FileNotFoundError(str(md_path))
	if md_path.suffix.lower() not in {".md", ".markdown"}:
		raise ValueError("Input must be a .md/.markdown file")

	out_pdf = Path(pdf_path).expanduser().resolve() if pdf_path else md_path.with_suffix(".pdf")
	out_pdf.parent.mkdir(parents=True, exist_ok=True)

	# Simple caching: if output exists and is newer than input, reuse it.
	try:
		if out_pdf.exists() and out_pdf.is_file() and out_pdf.stat().st_mtime >= md_path.stat().st_mtime:
			return PandocResult(pdf_path=out_pdf, cached=True, elapsed_sec=0.0)
	except Exception:
		pass

	pandoc = shutil.which("pandoc")
	if not pandoc:
		raise RuntimeError("pandoc not found in PATH. Install pandoc to enable PDF viewing.")

	# Write to a temp file then atomically replace.
	tmp_pdf = out_pdf.with_name(out_pdf.stem + f".tmp_{uuid.uuid4().hex}" + out_pdf.suffix)

	cmd = [
		pandoc,
		str(md_path),
		"-V",
		f"geometry:margin={margin}",
		"-o",
		str(tmp_pdf),
	]

	start = time.monotonic()
	try:
		proc = subprocess.run(
			cmd,
			check=True,
			capture_output=True,
			text=True,
			timeout=timeout_sec,
		)
		_ = proc  # silence linters
		tmp_pdf.replace(out_pdf)
	except subprocess.TimeoutExpired as e:
		try:
			if tmp_pdf.exists():
				tmp_pdf.unlink(missing_ok=True)  # type: ignore[arg-type]
		except Exception:
			pass
		raise RuntimeError(f"pandoc timed out after {timeout_sec}s") from e
	except subprocess.CalledProcessError as e:
		try:
			if tmp_pdf.exists():
				tmp_pdf.unlink(missing_ok=True)  # type: ignore[arg-type]
		except Exception:
			pass
		msg = (e.stderr or e.stdout or "").strip()
		if msg:
			raise RuntimeError(f"pandoc failed: {msg}") from e
		raise RuntimeError("pandoc failed") from e

	elapsed = time.monotonic() - start
	return PandocResult(pdf_path=out_pdf, cached=False, elapsed_sec=float(elapsed))