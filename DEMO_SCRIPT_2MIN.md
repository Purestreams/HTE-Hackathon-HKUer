# 2‑Minute Demo Script (Lighthouse: EduAI)

This is a **time-coded** talk track to demonstrate the end-to-end workflow in ~2 minutes.

## Pre-demo (10s, not counted)
- If demoing **live**: run backend (`python main.py`) and frontend (`cd frontui && npm run dev`).
- If demoing **static**: open the hosted UI demo: https://win7.win/HTE-Hackathon-HKUer/demo/index.html

---

## 0:00–0:10 — One-sentence pitch
“Lighthouse turns messy course PDFs into a **session-scoped** library, then generates a mock exam, runs a **two-model consensus validation** with streaming logs, and lets you chat/export everything as clean Markdown/PDF.”

## 0:10–0:25 — Sessions + Dashboard
- Open **Dashboard**.
- Say: “Everything is scoped to an **active session** so sources, snapshots, and AI outputs don’t mix across courses.”

## 0:25–0:40 — Upload / Ingest (PDF → Markdown)
- Go to **Upload** (or **PDF Ingest** if you want to show the routing controls).
- Say: “We can ingest PDFs in **auto** mode—fast text extraction when possible, and **vision** conversion for diagram-heavy pages.”
- Click **Create job / Upload**.

(If static demo: point out the page layout + controls; say ‘in live mode this creates background jobs’.)

## 0:40–1:00 — Mockpaper generation
- Go to **Mockpaper**.
- Call out controls quickly:
  - `num_questions`
  - `ratios` (MCQ / short / code)
  - language + topic
- Say: “This generates an exam with inline solutions by default, or separate paper+answer key.”
- Click **Create job**.

## 1:00–1:25 — Validate (Consensus Engine + streaming)
- Go to **Validate**.
- Select one generated mockpaper Markdown file.
- Ensure toggles are visible:
  - `run_code` (execute fenced python blocks)
  - `mock` (sanity-check formatting/numbering)
  - `ai_review` (Main model judges + Sub model challenges)
- Click **Create job**.
- Say: “The key is you can watch the **streaming discussion log** as the two models debate and converge on a revised result.”

## 1:25–1:40 — Chat (RAG over your session files)
- Go to **Chat**.
- Select 1–3 source files.
- Ask a short question, e.g.:
  - “Summarize the key concepts and give 3 exam-style questions.”
- Say: “Answers stream live, and we show which sources were used.”

## 1:40–1:55 — Library + PDF export
- Go to **Library**.
- Open a Markdown file in **View**, then click **View PDF** (pandoc pipeline).
- Say: “This gives a clean PDF export for sharing/printing.”

## 1:55–2:00 — Snapshots + Jobs (safety + observability)
- Mention **Snapshots**: “Save/fork the entire source library before big changes.”
- Mention **Jobs**: “All long tasks are trackable with status and logs.”

---

## If you only have 60 seconds
1. Dashboard (sessions) → 2. Mockpaper → 3. Validate (streaming consensus log) → 4. Chat → 5. Library ‘View PDF’
