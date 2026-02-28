import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from volcenginesdkarkruntime import Ark

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

try:
    from app.streaming import TokenRateProgress, estimate_tokens, stream_text_from_ark_response
except ModuleNotFoundError:
    # Supports running as a script: `python app/pdfToMarkdown.py ...`
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from app.streaming import TokenRateProgress, estimate_tokens, stream_text_from_ark_response


REFUSE_TOO_IMAGE_HEAVY_SENTINEL = "REFUSE_TOO_IMAGE_HEAVY"


def _require_ark_api_key() -> str:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing ARK_API_KEY. Set it in your shell (export ARK_API_KEY=...)"
        )
    return api_key


def _encode_image_as_data_url(image_path: Path) -> str:
    ext = image_path.suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg" if ext in {"jpg", "jpeg"} else "application/octet-stream"
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def extract_text_from_pdf(
    pdf_path: Path,
    max_pages: Optional[int] = None,
    per_page_char_limit: int = 8000,
) -> List[str]:
    """Extract embedded text (not OCR) from PDF pages."""
    texts: List[str] = []
    try:
        import pdfplumber  # type: ignore
    except Exception:
        pdfplumber = None  # type: ignore

    if pdfplumber is not None:
        with pdfplumber.open(str(pdf_path)) as pdf:
            total = len(pdf.pages)
            n = total if max_pages is None else min(total, max_pages)
            for i in range(n):
                t = pdf.pages[i].extract_text() or ""
                t = t.strip()
                if per_page_char_limit and len(t) > per_page_char_limit:
                    t = t[:per_page_char_limit] + "\n…(truncated)"
                texts.append(t)
        return texts

    # Fallback: PyMuPDF if available
    try:
        import fitz  # type: ignore
    except Exception:
        return []

    doc = fitz.open(str(pdf_path))
    try:
        total = doc.page_count
        n = total if max_pages is None else min(total, max_pages)
        for i in range(n):
            page = doc.load_page(i)
            t = (page.get_text("text") or "").strip() # type: ignore
            if per_page_char_limit and len(t) > per_page_char_limit:
                t = t[:per_page_char_limit] + "\n…(truncated)"
            texts.append(t)
    finally:
        doc.close()
    return texts


def render_pdf_to_images(
    pdf_path: Path,
    images_dir: Path,
    max_pages: Optional[int] = None,
    dpi: int = 200,
    image_format: str = "png",
) -> List[Path]:
    """Render each PDF page to an image file and return image paths."""
    images_dir.mkdir(parents=True, exist_ok=True)
    image_format = image_format.lower()
    if image_format not in {"png", "jpg", "jpeg"}:
        raise ValueError("image_format must be png/jpg/jpeg")

    # Prefer PyMuPDF (no external poppler dependency)
    try:
        import fitz  # type: ignore

        doc = fitz.open(str(pdf_path))
        try:
            total = doc.page_count
            n = total if max_pages is None else min(total, max_pages)
            scale = dpi / 72.0
            matrix = fitz.Matrix(scale, scale)
            out_paths: List[Path] = []
            for i in range(n):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                out_path = images_dir / f"page_{i+1:04d}.{image_format}"
                pix.save(str(out_path))
                out_paths.append(out_path)
            return out_paths
        finally:
            doc.close()
    except Exception:
        pass

    # Fallback: pdf2image (requires poppler)
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Unable to render PDF to images. Install PyMuPDF (pymupdf) or pdf2image + poppler."
        ) from e

    pil_images = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        first_page=1,
        last_page=None if max_pages is None else max_pages, # type: ignore
    )
    out_paths = []
    for i, img in enumerate(pil_images):
        out_path = images_dir / f"page_{i+1:04d}.{image_format}"
        img.save(str(out_path))
        out_paths.append(out_path)
    return out_paths


def build_pdf_to_markdown_prompt(
    extracted_text_by_page: List[str],
    overall_char_limit: int = 20000,
    *,
    refuse_if_too_image_heavy: bool = True,
) -> str:
    chunks: List[str] = []
    used = 0
    for i, page_text in enumerate(extracted_text_by_page, start=1):
        if not page_text:
            continue
        header = f"\n\n[Extracted text - Page {i}]\n"
        block = header + page_text
        if overall_char_limit and used + len(block) > overall_char_limit:
            remaining = max(0, overall_char_limit - used)
            if remaining > 0:
                chunks.append(block[:remaining] + "\n…(overall text truncated)")
            break
        chunks.append(block)
        used += len(block)

    extracted = "".join(chunks).strip()
    instructions = (
        "You are a document conversion engine. Convert the provided PDF pages to GitHub-flavored Markdown.\n"
        "- Preserve headings, lists, tables, code blocks, and links when present.\n"
        "- If content is a scanned page, rely on the image; if selectable text is provided below, use it to improve accuracy.\n"
        "- Keep the output as clean Markdown only (no preamble).\n"
    )
    if refuse_if_too_image_heavy:
        instructions += (
            "- IMPORTANT: If the document is predominantly visual imagery (photos/art/comics/posters/diagrams without enough text) "
            "and a faithful Markdown representation would mainly be subjective descriptions of images, then refuse. "
            f"In that case output EXACTLY this token and nothing else: {REFUSE_TOO_IMAGE_HEAVY_SENTINEL}\n"
        )
    if extracted:
        return instructions + "\n\nSelectable text extracted from the PDF (may be incomplete):\n" + extracted
    return instructions


def convert_pdf_to_markdown(
    pdf_path: Path,
    output_md_path: Path,
    *,
    model: str,
    max_pages: Optional[int] = None,
    dpi: int = 200,
    images_subdir: str = "_pdf_images",
    per_page_text_char_limit: int = 8000,
    overall_text_char_limit: int = 20000,
    temperature: Optional[float] = None,
    refuse_if_too_image_heavy: bool = True,
    show_progress: bool = False,
    on_progress_tokens: Optional[Callable[[int], None]] = None,
) -> Tuple[str, List[Path]]:
    pdf_path = pdf_path.expanduser().resolve()
    output_md_path = output_md_path.expanduser().resolve()
    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    images_dir = output_md_path.parent / images_subdir / pdf_path.stem
    image_paths = render_pdf_to_images(pdf_path, images_dir, max_pages=max_pages, dpi=dpi)
    extracted_text = extract_text_from_pdf(
        pdf_path,
        max_pages=max_pages,
        per_page_char_limit=per_page_text_char_limit,
    )

    prompt_text = build_pdf_to_markdown_prompt(
        extracted_text,
        overall_char_limit=overall_text_char_limit,
        refuse_if_too_image_heavy=refuse_if_too_image_heavy,
    )

    content_blocks = [{"type": "text", "text": prompt_text}]
    for p in image_paths:
        content_blocks.append({"type": "image_url", "image_url": {"url": _encode_image_as_data_url(p)}}) # type: ignore

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content_blocks,
            }
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    api_key = _require_ark_api_key()
    client = Ark(api_key=api_key)
    if show_progress or on_progress_tokens is not None:
        progress = TokenRateProgress(label="pdf") if show_progress else None
        if progress:
            progress.start()
        stream = client.chat.completions.create(**payload, stream=True)
        parts: List[str] = []
        total_tok = 0
        for chunk in stream:
            delta_text = stream_text_from_ark_response([chunk])
            if not delta_text:
                continue
            parts.append(delta_text)
            total_tok = estimate_tokens("".join(parts))
            if progress:
                progress.update(total_tok)
            if on_progress_tokens is not None:
                on_progress_tokens(total_tok)
        markdown = "".join(parts)
        if progress:
            progress.finish(estimate_tokens(markdown))
    else:
        resp = client.chat.completions.create(**payload)
        msg = resp.choices[0].message # type: ignore
        markdown = msg.content or ""

    if refuse_if_too_image_heavy and markdown.strip() == REFUSE_TOO_IMAGE_HEAVY_SENTINEL:
        raise RuntimeError(
            "Refused: PDF appears too image-heavy to represent as Markdown without subjective image descriptions."
        )

    output_md_path.write_text(markdown, encoding="utf-8")
    return markdown, image_paths


def pdf_diagnostics(
    pdf_path: Path,
    max_pages: Optional[int] = None,
) -> dict:
    """Lightweight stats for debugging preprocessing without calling the model."""
    pdf_path = pdf_path.expanduser().resolve()
    embedded_text = extract_text_from_pdf(pdf_path, max_pages=max_pages)
    per_page_text_chars = [len(t or "") for t in embedded_text]
    per_page_image_counts: List[int] = []

    try:
        import fitz  # type: ignore

        doc = fitz.open(str(pdf_path))
        try:
            total = doc.page_count
            n = total if max_pages is None else min(total, max_pages)
            for i in range(n):
                page = doc.load_page(i)
                per_page_image_counts.append(len(page.get_images(full=True)))
        finally:
            doc.close()
    except Exception:
        per_page_image_counts = []

    return {
        "pdf": str(pdf_path),
        "pages_considered": len(per_page_text_chars),
        "per_page_text_chars": per_page_text_chars,
        "total_text_chars": sum(per_page_text_chars),
        "per_page_image_counts": per_page_image_counts,
        "total_images": sum(per_page_image_counts) if per_page_image_counts else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a PDF to Markdown using Ark vision model (images + extracted text).")
    parser.add_argument("--pdf", required=True, help="Path to the input PDF")
    parser.add_argument("--out", required=True, help="Path to the output .md")
    parser.add_argument(
        "--model",
        default=os.environ.get("ARK_MODEL", "doubao-seed-1-8-251228"),
        help="Ark model name (default: env ARK_MODEL or doubao-seed-1-8-251228)",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Only process the first N pages")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI for page images")
    parser.add_argument("--temperature", type=float, default=None, help="Optional model temperature")
    parser.add_argument(
        "--allow-image-heavy",
        action="store_true",
        help=f"Do not refuse when image-heavy (disables {REFUSE_TOO_IMAGE_HEAVY_SENTINEL} logic)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preprocess only: render images + extract text and print diagnostics (no Ark call, no ARK_API_KEY needed).",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    if args.dry_run:
        pdf_path = pdf_path.expanduser().resolve()
        out_path = out_path.expanduser().resolve()
        images_dir = out_path.parent / "_pdf_images" / pdf_path.stem
        image_paths = render_pdf_to_images(pdf_path, images_dir, max_pages=args.max_pages, dpi=args.dpi)
        print({
            "rendered_images": len(image_paths),
            "images_dir": str(images_dir),
            "diagnostics": pdf_diagnostics(pdf_path, max_pages=args.max_pages),
        })
        return 0

    convert_pdf_to_markdown(
        pdf_path,
        out_path,
        model=args.model,
        max_pages=args.max_pages,
        dpi=args.dpi,
        temperature=args.temperature,
        refuse_if_too_image_heavy=not args.allow_image_heavy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())