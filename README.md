[hero](hero.png)

# Lighthouse: EduAI

An AI-enpowered educational platform that amplifies actual innovation in the latest papers, saving time & accelerate learning with realtime multi-agent consensus validation. No matter you're newly onboard or reknowned sailors, Lighthouse guides YOUR way through the most turbulent, ever-changing water.

Lighthouse assists real-world learning in an automated workflow, ingests PDF papers in managable sessions of summarization, chanllenges you with configurable quizes, which then goes through multi-agent validation. The revision delivers interactive results with retrieval-augmented generation support.

- Hosted demo: https://win7.win/HTE-Hackathon-HKUer/demo/index.html (static page)

## Detailed Summary

Lighthouse is designed to streamline the academic lifecycle of study materials—from raw PDF papers to validated mock examinations. Unlike broad AI tools, ighthouse provides a **session-centric workspace** where all documents, snapshots, and AI interactions are pinned to a specific context.

### Core Workflow
1.  **Ingest**: High-fidelity conversion of PDFs to Markdown. It intelligently chooses between fast text extraction and vision-based conversion (using Ark/Doubao models) to handle complex layouts and diagrams.
2.  **Generate**: Mock papers are synthesized from your ingested sources. You can control the distribution of Multiple Choice, Short Answer, and Coding questions to match specific exam styles.
3.  **Validate (The Consensus Engine)**: This is the platform's flagship feature. Instead of a single AI review, it launches a **multi-agent discussion**. A "Main Model" and "Sub Model" review the generated content, debate potential improvements, and must reach a consensus. The entire "thinking" process is streamed live to the user and finally exported as a revised document.
4.  **Query & Export**: Use the built-in streaming chat to ask questions across all session documents. Once satisfied with a document, export it to a clean, formatted PDF via the system-integrated Pandoc pipeline.

### Technical Architecture
-   **Backend**: Async Flask server managing an in-memory job store for background processing.
-   **AI Routing**: Multi-provider support for **Ark (Doubao/DeepSeek)** and **MiniMax**.
-   **Frontend**: A responsive React SPA with real-time SSE (Server-Sent Events) for job progress and AI streaming logs.
-   **Data Consistency**: Session-based snapshots allow users to "fork" their source library at any time, ensuring no work is lost during iterative AI generation.

## Key Features

- **Session-Scoped Workspace**: Multiple isolated sessions with file snapshots and library management.
- **Smart PDF Ingest**: Multi-file PDF-to-Markdown conversion using Ark (Doubao) vision models or text extraction heuristics.
- **Mock Paper Generation**: Generate exams based on session documents with customizable style, topic, and difficulty ratios.
- **Consensus Validate**: A two-model "consensus" workflow where a Main Model and Sub Model discuss and review mock papers, generating revised versions and a streaming "AI thinking" log.
- **Streaming Chat**: ChatGPT-like interface for querying session documents (using context stuffing) with Markdown and LaTeX rendering.
- **Markdown to PDF**: View any Markdown source as a formatted PDF using system `pandoc` with automatic LaTeX symbol support (e.g., ✓).

## Project Structure

- `app/`: Backend logic for PDF ingest, mockpapers, validation, and chat routing.
- `frontui/`: React + Tailwind CSS + Vite frontend.
- `main.py`: Flask API server and background job runner.
- `data/`: Local storage for sessions, source files, and snapshots.

## Environment Setup

1. **Python Dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirement.txt
   ```

2. **Frontend Dependencies**:
   ```bash
   cd frontui
   npm install
   ```

3. **System Dependencies**:
   - `pandoc`: Required for "View PDF" functionality.
   - `xelatex` (optional): Recommended for rendering Unicode glyphs in PDFs.

4. **API Keys**:
   Create a `.env` file in the root directory:
   ```env
   ARK_API_KEY=your_ark_key_here
   ANTHROPIC_API_KEY=your_minimax_key_here
   ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
   EXA_API_KEY=your_exa_key_here
   ```

## How to Run

1. **Start the Backend**:
   ```bash
   python main.py
   ```
   The server runs on `http://127.0.0.1:8000`.

2. **Start the Frontend**:
   ```bash
   cd frontui
   npm run dev
   ```
   Navigate to `http://localhost:5173`.

## Static HTML Demo

If you just want to preview the UI (no backend, no real actions), a static demo is included in `demo/`.

- Open `demo/index.html` directly in a browser, or
- Serve it locally (recommended for consistent asset loading):
   ```bash
   cd demo
   python3 -m http.server 4174 --bind 127.0.0.1
   ```
   Then open `http://127.0.0.1:4174/`.

## Usage Tips

- **Multi-File Ingest**: On the Ingest page, select multiple PDFs to process them in parallel jobs.
- **AI Thinking Log**: During Validation, use the side panel to view the live streaming "thoughts" of the models as they reach consensus.
- **Snapshotting**: Use the Snapshots page to save the state of your session's sources before major changes.
