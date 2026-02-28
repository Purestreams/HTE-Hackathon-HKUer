# Sources folder layout

The `sources/` directory is treated as **local data** (see `.gitignore`) and is organized for clarity.

## Current structure

- `sources/assignments/A1/`, `A2/`, `A3/`
  - Original assignment PDFs and Markdown.
  - Per-assignment rendered page images live under `sources/assignments/A*/_pdf_images/<pdf-stem>/`.
- `sources/mockpaper/`
  - Generated mock exams from `app/mockpaper.py`.
  - Default output is a single combined markdown: `<name>.md` (answers inline after each question).
  - Use `--separate` to generate the legacy `<name>_paper.md` + `<name>_answers.md` pair.

## Recommended usage

- Generate mock papers from the assignments only (avoid feeding generated mocks back as samples):
  - `python app/mockpaper.py --sample sources/assignments --out-dir sources/mockpaper --name mock_from_sources ...`

- Validate everything under `sources/` (recursive):
  - `python app/validate.py --sources-dir sources --mock`

- Convert a PDF to Markdown and keep images next to the output:
  - `python app/pdfToMarkdown.py --pdf sources/assignments/A1/Assignment1.pdf --out sources/assignments/A1/Assignment1.md ...`
