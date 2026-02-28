# 2‑Minute Spoken Demo Script (Lighthouse: EduAI)

Time-coded **talk track** for a ~2 minute live presentation.

## Pre-demo (10s, not counted)
“What you’re seeing is Lighthouse: EduAI. It’s a session-scoped workflow for turning course materials into study-ready content: searchable notes, generated mock exams, consensus validation, and clean PDF exports.”

---

## 0:00–0:10 — One-sentence pitch
“Lighthouse turns messy course PDFs into a **session-scoped** library, generates a mock exam, runs a **two-model consensus validation** with streaming logs, and lets you chat and export everything as clean Markdown and PDF.”

## 0:10–0:25 — Sessions
“The core idea is **sessions**. Each course gets its own isolated workspace, so your sources, snapshots, and AI outputs never get mixed across classes. That makes iterative study workflows safe and repeatable.”

## 0:25–0:40 — Upload + Smart PDF ingest
“On the ingestion side, Lighthouse supports both quick extraction and vision-based conversion. In **auto** mode, it takes the fast path for text PDFs, but switches to **vision** when pages are diagram-heavy—so the resulting Markdown stays high fidelity.”

## 0:40–1:00 — Mockpaper generation
“Once sources are in the session, we generate a mock exam directly from those materials. You can control how many questions you want, the mix of MCQ versus short answer versus coding, plus language and topic constraints. The default output includes inline, step-by-step solutions, with an option for a separate answer key.”

## 1:00–1:25 — Validate (Consensus Engine)
“Validation is the flagship. We don’t rely on a single model’s review—we run a **Main model** as judge/editor and a **Sub model** as challenger. They critique, debate, and converge on a revised version. While that happens, we stream the discussion log so you can see the reasoning process, not just a final black-box answer.”

## 1:25–1:40 — Chat (RAG over session files)
“Then there’s a streaming chat layer over your chosen session files. You can ask for explanations, summaries, or new practice questions, and it answers with Markdown and LaTeX rendering. Importantly, it surfaces which sources were used, so the response stays grounded in your materials.”

## 1:40–1:55 — Library + PDF export
“Everything you generate and ingest is browsable in the library. Markdown renders cleanly, original PDFs remain accessible, and any Markdown can be exported into a polished PDF via a Pandoc pipeline for sharing or printing.”

## 1:55–2:00 — Snapshots + Jobs
“Finally, snapshots let you save and fork the entire source state, and jobs give you visibility into long-running tasks with progress and logs—so the workflow is both safe and observable end-to-end.”

---

## 60-second version (optional)
“Session-scoped library in. Smart PDF-to-Markdown. Mock exam out. Two-model consensus validation with streaming logs. RAG chat across your sources. Export to PDF. Snapshots and job tracking to keep everything safe and auditable.”
