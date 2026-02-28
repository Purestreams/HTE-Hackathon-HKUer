"""Markdown to PDF via system pandoc.

Uses the system `pandoc` binary to render a Markdown file to PDF.

Reference command:
  pandoc input.md -V geometry:margin=1in -o output.pdf

Note: Pandoc typically requires a PDF engine (e.g., LaTeX) to be installed.
"""

from __future__ import annotations

import os
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
	pdf_engine: Optional[str] = None,
	mainfont: Optional[str] = None,
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

	# Default to a Unicode-capable engine so characters like "✓" render.
	# You can override via env PANDOC_PDF_ENGINE or the function arg.
	engine = (pdf_engine or os.environ.get("PANDOC_PDF_ENGINE") or "xelatex").strip()
	if engine:
		# Best-effort check: pandoc will fail if the engine isn't installed.
		if shutil.which(engine) is None:
			raise RuntimeError(
				f"PDF engine '{engine}' not found in PATH. Install a LaTeX distribution (e.g., TeX Live) "
				"or set PANDOC_PDF_ENGINE to an available engine (xelatex/lualatex/pdflatex)."
			)

	# Optional font override; do NOT default to any specific font because it may not exist
	# on the host machine (and will hard-fail the conversion).
	font = str((mainfont if mainfont is not None else os.environ.get("PANDOC_MAINFONT") or "")).strip()

	# If the markdown contains common glyphs that often fail under LaTeX/font setups,
	# rewrite them to TeX commands and include required packages.
	tmp_md: Optional[Path] = None
	tmp_header: Optional[Path] = None
	try:
		try:
			text = md_path.read_text(encoding="utf-8")
		except UnicodeDecodeError:
			text = md_path.read_text(encoding="utf-8", errors="replace")

		needs_pifont = ("✓" in text) or ("✗" in text)
		if needs_pifont:
			# Use pifont ding symbols to avoid relying on system fonts.
			# ✓ -> \ding{51}, ✗ -> \ding{55}
			# Raw TeX is supported by pandoc when producing PDF via LaTeX.
			patched = text.replace("✓", r"\\ding{51}").replace("✗", r"\\ding{55}")
			tmp_md = md_path.with_name(md_path.stem + f".tmp_{uuid.uuid4().hex}" + md_path.suffix)
			tmp_md.write_text(patched, encoding="utf-8")

			tmp_header = md_path.with_name(md_path.stem + f".tmp_{uuid.uuid4().hex}_header.tex")
			tmp_header.write_text("\\usepackage{pifont}\n", encoding="utf-8")
	except Exception:
		# If sanitization fails, proceed with original file; pandoc may still succeed.
		tmp_md = None
		tmp_header = None

	# Write to a temp file then atomically replace.
	tmp_pdf = out_pdf.with_name(out_pdf.stem + f".tmp_{uuid.uuid4().hex}" + out_pdf.suffix)

	cmd = [
		pandoc,
		str(tmp_md or md_path),
		"--from",
		"markdown+raw_tex",
		"--pdf-engine",
		engine,
		"-V",
		f"geometry:margin={margin}",
	]

	if font and engine in {"xelatex", "lualatex"}:
		cmd += ["-V", f"mainfont={font}"]

	if tmp_header is not None:
		cmd += ["-H", str(tmp_header)]

	cmd += [
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
			raise RuntimeError(
				"pandoc failed: "
				+ msg
				+ "\n\nTip: if this is a Unicode/font error (e.g., ✓), keep using xelatex/lualatex and either (1) install a font "
				+ "that contains the glyph and set PANDOC_MAINFONT, or (2) rely on the built-in ✓/✗ sanitization (enabled automatically)."
			) from e
		raise RuntimeError("pandoc failed") from e
	finally:
		try:
			if tmp_md is not None and tmp_md.exists():
				tmp_md.unlink(missing_ok=True)  # type: ignore[arg-type]
		except Exception:
			pass
		try:
			if tmp_header is not None and tmp_header.exists():
				tmp_header.unlink(missing_ok=True)  # type: ignore[arg-type]
		except Exception:
			pass

	elapsed = time.monotonic() - start
	return PandocResult(pdf_path=out_pdf, cached=False, elapsed_sec=float(elapsed))