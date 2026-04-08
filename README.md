# Legal AI Insights Platform

AI-powered platform to upload legal documents and turn them into plain-language insights, translations, similarity matches, predictions, and chatbot answers.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Problem It Solves](#problem-it-solves)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [End-to-End Processing Flow](#end-to-end-processing-flow)
- [AI Capabilities](#ai-capabilities)
- [Related Research Papers](#related-research-papers)
- [Useful Datasets and Resources](#useful-datasets-and-resources)
- [Why This Project Is Publishable](#why-this-project-is-publishable)
- [Suggested Paper Outline](#suggested-paper-outline)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Data Storage Model](#data-storage-model)
- [SQL Schema Reference (Brief)](#sql-schema-reference-brief)
- [MongoDB Schema Reference (Brief)](#mongodb-schema-reference-brief)
- [MongoDB Atlas Setup (Brief)](#mongodb-atlas-setup-brief)
- [Installation and Setup](#installation-and-setup)
- [Environment Variables](#environment-variables)
- [How to Use](#how-to-use)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Screenshots](#screenshots-placeholder)
- [Future Enhancements](#future-enhancements)
- [Contribution Guidelines](#contribution-guidelines)
- [License](#license)
- [Author](#author)

---

## Project Overview

**Legal AI Insights Platform** is a full-stack legal-tech application built to simplify complex legal documents.

Users can upload scanned or digital court documents (PDF/image), and the platform performs OCR, extracts metadata, generates summaries, translates output, retrieves similar cases, predicts outcomes, and supports legal Q&A through a chatbot.

The platform combines:

- FastAPI APIs for core processing
- MongoDB + MySQL dual-storage architecture
- NLP and embedding-based retrieval
- Optional LLM integrations (Groq/Ollama)
- React + Vite frontend for an interactive user experience

---

## Problem It Solves

Legal documents are difficult for most users because they are:

- Long and technical
- Filled with legal jargon
- Often scanned and not machine-readable
- Hard to search, compare, and understand quickly

This project reduces that friction by automating legal document understanding and presenting insights in plain language and multiple languages.

---

## Key Features

- 📄 **Upload Legal Documents**: PDF, PNG, JPG, JPEG, TIFF, TIF
- 🔍 **OCR + Text Extraction**: Extract text from scanned and digital files
- 🧹 **Text Normalization Pipeline**: Clean noisy OCR output for downstream AI tasks
- 🧾 **Case Metadata Extraction**: Rule-based extraction + AI fallback + quality gate
- 🧠 **AI Summarization**:
  - `basic_summary` (simple, concise)
  - `short_summary`
  - `detailed_summary`
  - `key_points`
- 🌐 **Multilingual Translation**: English, Hindi, Telugu (+ extended languages)
- ⚖️ **Legal Section Detection**: Section/act detection and legal token-aware translation
- 🔎 **Similar Case Retrieval**: Keyword overlap + semantic embedding hybrid scoring
- 💬 **Hybrid Legal Chatbot**:
  - Metadata mode
  - RAG content mode
  - Legal knowledge mode
  - Hybrid mode
- 📊 **Dashboard APIs**: Overview, metrics, recent activity, pipeline status, SQL health, audit logs
- 🔁 **Background Processing Worker**: Multi-stage queue-driven processing
- 🧮 **Prediction APIs**:
  - Historical-text predictor
  - Structured manual outcome prediction
- 🧾 **Feedback Loop**: Store corrections for metadata-learning refinement

---

## System Architecture

### High-Level Components

1. **Frontend (React + Vite)**
- Upload documents
- Trigger summary/translation/similarity
- Open manual prediction page
- Chat with legal assistant
- View recent cases and status

2. **Backend API (FastAPI)**
- Receives uploads and stores files
- Runs OCR + metadata extraction
- Exposes AI, chatbot, dashboard, and prediction endpoints
- Starts background pipeline worker

3. **AI Processing Layer (Python modules)**
- OCR, text cleaning, summarization, translation
- Embedding generation and vector search
- Rule-based + optional LLM-based logic

4. **Data Layer**
- **MongoDB**: raw judgments, queue, AI outputs, chunks, embeddings metadata, summaries, translations, predictions
- **MySQL**: normalized relational data, audit logs, feedback, chat history, similar cases

### Request Flow Snapshot

`Frontend -> FastAPI -> OCR/NLP/AI -> MongoDB/MySQL -> Frontend`

---

## End-to-End Processing Flow

### Upload Pipeline

1. User uploads a file via `POST /cases/upload-case`.
2. File is stored under `uploads/`.
3. OCR runs and extracts text.
4. Text is normalized and split into paragraphs.
5. Metadata extraction runs:
- Rule-based extraction
- Optional Ollama/Groq fallback
- Learning corrections from past feedback
- Quality gate check for SQL write eligibility
6. Case is stored in MongoDB (`raw_judgments`).
7. Structured metadata is upserted to MySQL (`cases`) when quality checks pass.
8. Case is enqueued in `processing_queue` for background pipeline execution.

### Background Worker Stages

Queue stage progression:

`extracted -> cleaned -> summarized -> translated -> chunked -> embedded -> predicted -> completed`

What each stage does:

- `extracted`: clean text, detect language, split paragraphs, update case record
- `cleaned`: generate facts and summaries
- `summarized`: translate summary payload
- `translated`: create text chunks for retrieval
- `chunked`: create embeddings and vector index entries
- `embedded`: generate prediction outputs
- `predicted`: mark case complete

---

## AI Capabilities

### 1) Metadata Extraction

- Rule-based case parser for case number, parties, court, dates, judges, advocates, disposition
- Optional AI extraction via:
- Ollama
- Groq
- Merge strategy + validation + confidence scoring
- Quality gate to prevent poor metadata from entering SQL
- Feedback-driven learning adjustments via `learning_feedback`

### 2) Summarization

- Section-aware summarizer with header-noise removal
- Fact/argument/outcome signal detection
- Key-point generation
- Optional model-assisted refinement with quality checks

### 3) Translation

- Translation targets include Hindi (`hi`), Telugu (`te`), and more
- Protects legal tokens and proper nouns using placeholders
- Supports simple-English mode
- Uses LLM translation when available, then fallback strategy

### 4) Similarity Search

- Hybrid scoring:
- 65% keyword overlap (acts/sections/legal terms)
- 35% semantic similarity (embeddings)
- Stores similar-case links in MySQL

### 5) Chatbot

Four-route architecture:

- `metadata`: answers from structured fields only
- `rag_content`: answers from retrieved case text
- `legal_knowledge`: answers general legal concepts
- `hybrid`: combines legal explanation + case-specific application

### 6) Prediction

- Text-based predictor (`/prediction/{case_id}`) using baseline + historical similarity enhancement
- Manual weighted predictor (`/predict/manual`) using structured legal factors

---

## Related Research Papers

- **Automatic Legal Judgment Summarization Using LLMs (JUST-NLP 2025)** - Abstractive legal summarization with LLM evaluation.
- **Legal Document Summarization Using NLP & ML Techniques** - Extractive baselines with vectors/similarity.
- **Improving Legal Judgment Prediction via Deep Learning** - Prediction pipelines linked with legal text understanding.
- **Legal Judgment Prediction Systematic Review** - Survey of prediction methods and evaluation approaches.
- **ValidEase: NLP Simplification & Summarization of Legal Texts** - Simplification-focused legal NLP framing.
- **Indian Legal Judgment Summarization Using Pretrained Models** - T5/BART-style summarization direction.
- **Legal NLP Survey (2024)** - Broad coverage of summarization, classification, retrieval, and prediction.

Use these in the Related Work section of your paper and map each to your corresponding module (summarizer, predictor, chatbot, retrieval).

---

## Useful Datasets and Resources

### Suggested Datasets/Benchmarks

- `LegalBench` - Legal reasoning benchmark tasks.
- `IndicLegalQA` - Legal QA pairs (useful for chatbot evaluation).
- `ILSI (Indian Legal Statute Identification)` - Legal section/statute identification.
- `awesome-legal-nlp` dataset lists - Curated legal NLP datasets.
- `Cambridge Law Corpus` - Large legal text corpus for benchmarking.

### Public Legal Data Sources

- Free Law Project
- PlainSite
- Awesome Legal Data (GitHub collections)

### Research Portals

- ACL Anthology
- arXiv
- ResearchGate
- Springer
- SAGE Journals

---

## Why This Project Is Publishable

- Integrates multiple legal AI tasks in one platform (summarization, retrieval, prediction, translation, chatbot).
- Uses practical legal document workflows (upload -> OCR -> analytics -> user-facing insights).
- Includes multilingual capability (important for Indian legal accessibility).
- Uses modern retrieval architecture (embeddings + vector search + RAG-style answering).
- Supports auditability and reproducibility via structured logs and versioned outputs.

---

## Suggested Paper Outline

1. Introduction and Motivation
2. Related Work (summarization, prediction, legal QA, retrieval)
3. Dataset and Data Pipeline (OCR, metadata, storage)
4. Methodology (summary, translation, retrieval, prediction, chatbot)
5. Evaluation (ROUGE/BLEU, prediction metrics, response quality)
6. Results and Error Analysis
7. Conclusion and Future Work

---

## Tech Stack

### Frontend

- React 18
- Vite 5
- Plain CSS (custom styling; Tailwind is not currently used)

### Backend

- Python 3.11+
- FastAPI
- Uvicorn

### Databases

- MongoDB (document storage + processing state)
- MySQL (relational entities, logs, audit, feedback)

### AI/NLP/OCR Libraries

- sentence-transformers (`all-MiniLM-L6-v2` embeddings)
- transformers / torch
- scikit-learn
- pdfplumber
- pytesseract
- Pillow
- deep-translator

### Optional Model Providers

- Ollama (local model serving)
- Groq API
- Hugging Face Hub (model download/caching for embeddings)

### Tooling

- npm scripts for orchestration
- PowerShell scripts for setup and backend run

---

## Project Structure

```text
mini-pro/
├── backend/
│   ├── ai/
│   │   ├── embeddings.py
│   │   ├── legal_chatbot.py
│   │   ├── predictor.py
│   │   ├── summarizer.py
│   │   ├── translator.py
│   │   └── vector_store.py
│   ├── database/
│   │   ├── mongo.py
│   │   ├── mysql.py
│   │   └── settings.py
│   ├── models/
│   ├── routes/
│   │   ├── upload_routes.py
│   │   ├── ai_routes.py
│   │   ├── similarity_routes.py
│   │   ├── chatbot_routes.py
│   │   ├── prediction_routes.py
│   │   ├── manual_prediction_routes.py
│   │   ├── dashboard_routes.py
│   │   └── feedback_routes.py
│   ├── services/
│   │   ├── metadata_pipeline.py
│   │   ├── learning_engine.py
│   │   └── pipeline_worker.py
│   ├── utils/
│   │   ├── ocr_processor.py
│   │   └── case_extractor.py
│   ├── scripts/
│   │   └── init_legal_ai.sql
│   ├── .env.example
│   ├── requirements.txt
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── styles.css
│   │   └── components/
│   ├── .env.example
│   └── package.json
├── scripts/
│   ├── setup.ps1
│   ├── install-backend.ps1
│   └── run-backend.ps1
├── uploads/
└── README.md
```

---

## API Reference

### Upload & Case Features

- `POST /cases/upload-case` - Upload and ingest legal document
- `GET /cases/features/{case_number}` - Feature availability for a case

### AI

- `GET /ai/summarize/{case_number}` - Generate/store summaries
- `GET /ai/translate/{case_number}?language=<code>&mode=summary|raw` - Translate summary or full text
- `GET /ai/case/{case_id}` - Fetch case details by Mongo `_id`
- `GET /ai/analyze/{case_number}` - Combined analysis (summary/translation/similarity/prediction)

### Similarity

- `GET /search/{case_number}` - Retrieve top similar cases

### Chatbot

- `POST /chatbot/ask` - Ask chatbot with optional case context/history

### Prediction

- `GET /prediction/{case_id}` - Text-driven prediction
- `POST /predict/manual` - Structured manual probability prediction

### Dashboard

- `GET /dashboard/overview`
- `GET /dashboard/metrics`
- `GET /dashboard/recent-activity`
- `GET /dashboard/cases`
- `GET /dashboard/pipeline/{case_number}`
- `GET /dashboard/sql-health`
- `GET /dashboard/audit/{case_id}`

### Feedback

- `POST /feedback` - Store correction feedback
- `GET /feedback` - List recent feedback

### Misc

- `GET /` - Health message (`Legal AI Running`)
- `POST /raw-judgments/insert` - Intentionally disabled (returns 400)

---

## Data Storage Model

### MongoDB Collections

- `raw_judgments`
- `processing_queue`
- `case_facts`
- `case_summaries`
- `case_translations`
- `case_chunks`
- `embeddings_metadata`
- `case_predictions`
- `ai_outputs`

### MySQL Tables

Created via `backend/scripts/init_legal_ai.sql`:

- `cases`
- `case_acts`
- `case_facts`
- `case_summaries`
- `case_translations`
- `case_predictions`
- `case_audit_logs`
- `learning_feedback`
- `similar_cases`
- `judge_analytics`
- `chat_history`
- `system_logs`

---

## SQL Schema Reference (Brief)

Schema source: `backend/scripts/init_legal_ai.sql`.

### `cases` (main metadata)

`case_id`, `case_number`, `case_prefix`, `case_number_numeric`, `case_year`, `title`, `court_name`, `court_level`, `bench`, `case_type`, `filing_date`, `registration_date`, `decision_date`, `petitioner`, `respondent`, `judge_names`, `advocates`, `disposition`, `citation`, `source`, `pdf_url`, `created_at`.

### Other relational tables

- `case_acts`: `act_id`, `case_id`, `act_name`, `section`, `description`
- `case_facts`: `fact_id`, `case_id`, `fact_type`, `fact_text`
- `case_summaries`: `summary_id`, `case_id`, `summary_type`, `summary_text`, `model_used`, `created_at`
- `case_translations`: `translation_id`, `case_id`, `language_code`, `translated_summary`, `model_used`, `created_at`
- `case_predictions`: `prediction_id`, `case_id`, `predicted_outcome`, `win_probability`, `confidence_score`, `key_factors`, `model_version`, `created_at`
- `case_audit_logs`: metadata extraction and quality-gate audit JSON fields + flags
- `learning_feedback`: correction learning records
- `similar_cases`: cached similar-case links (`case_id`, `similar_case_id`, `similarity_score`)
- `judge_analytics`: per-judge aggregate metrics
- `chat_history`: user query, response, context IDs, response time
- `system_logs`: module-level operational logs

---

## MongoDB Schema Reference (Brief)

Database: `legal_ai_mongo`.

### `raw_judgments` (primary case document)

Core fields used by current pipeline:

- `source_type`, `case_number`, `title`, `case_id_mysql`
- `file_info`: `file_name`, `stored_path`, `upload_time`
- `judgment_text`: `raw_text`, `clean_text`, `paragraphs`, `language`, `token_count`
- `case_metadata` (extracted metadata + quality flags)
- `nlp_flags` (`text_cleaned`, `summarized`, `translated`, `embedded`, etc.)
- `processing_status`, `created_at`, `last_updated_at`, `error_logs`

### `processing_queue`

- `case_id`, `case_number`, `stage`, `status`, `attempts`, `error`, `worker_id`, `started_at`, `finished_at`, `updated_at`, `created_at`

### `case_chunks`

- `case_id`, `case_number`, `chunk_index`, `chunk_type`, `text`, `created_at`

### `embeddings_metadata`

- `case_id`, `case_number`, `chunk_index`, `model`, `dimension`, `created_at`

### `ai_outputs`

- `case_id`, `case_number`, `stage`, `output`, `created_at`

### Additional collections used by APIs/pipeline

- `case_summaries`
- `case_translations`
- `case_predictions`
- `case_facts`

---

## MongoDB Atlas Setup (Brief)

1. Create an Atlas M0 cluster in a nearby region (for India, Mumbai is usually best).
2. Create a database user (`Database Access`) with read/write privileges.
3. Add IP access (`Network Access`) for your machine (avoid `0.0.0.0/0` in production).
4. Copy Python connection string and set in `backend/.env`:
   - `MONGO_URI=...`
   - `MONGO_DB=legal_ai_mongo`
5. Start backend and verify connection from logs (`MongoDB connected`).
6. Upload one case and confirm collections are created/populated.

Recommended initial collections:

- `raw_judgments`
- `processing_queue`
- `case_chunks`
- `embeddings_metadata`
- `ai_outputs`
- `case_summaries`
- `case_translations`
- `case_predictions`

---

## Installation and Setup

### Prerequisites

- Node.js 20+
- npm 10+
- Python 3.11+
- MongoDB (local or Atlas)
- MySQL 8+
- Tesseract OCR installed (required for image OCR)

Windows OCR path used in code:

`C:\Program Files\Tesseract-OCR\tesseract.exe`

If your Tesseract is elsewhere, update `backend/utils/ocr_processor.py`.

### 1) Clone

```bash
git clone <your-repo-url>
cd mini-pro
```

### 2) Install Dependencies

Option A: one command setup (recommended on Windows)

```powershell
npm run setup
```

Option B: manual

```powershell
npm run frontend:install
npm run backend:install
```

### 3) Configure Environment Files

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Edit both files with your credentials and local settings.

### 4) Initialize MySQL Schema

```bash
mysql -u root -p < backend/scripts/init_legal_ai.sql
```

### 5) Run Services

Backend:

```powershell
npm run backend:dev
```

Frontend:

```powershell
npm run frontend:dev
```

### 6) Open in Browser

- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8000`
- Swagger Docs: `http://127.0.0.1:8000/docs`

### Alternative Backend Start (direct uvicorn)

```powershell
.\backend\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Use either direct `uvicorn` or `npm run backend:dev`, not both at once.

---

## Environment Variables

### `backend/.env`

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=legal_ai_mongo

MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DB=legal_ai

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

HF_TOKEN=
```

### `frontend/.env`

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### Notes

- `HF_TOKEN` is optional but recommended for higher Hugging Face rate limits.
- Do not commit `.env` files with real secrets.

---

## How to Use

1. Upload a legal PDF/image from the upload card.
2. Wait for initial storage and metadata extraction.
3. Run summary.
4. Translate summary (or full raw text mode if needed).
5. Retrieve similar cases.
6. Ask the chatbot with selected mode (`auto`, `hybrid`, `rag`, `general`, `metadata`).
7. Use manual prediction page for structured outcome probabilities.
8. Monitor case coverage/status through dashboard endpoints.

---

## Troubleshooting

### `net::ERR_CONNECTION_REFUSED` in frontend

Cause: backend is not running or stopped.

Fix:

- Start backend and keep terminal open.
- Verify `http://127.0.0.1:8000/docs` works.
- Ensure frontend uses correct `VITE_API_BASE_URL`.

### File picker opens twice on upload

Resolved in current code by avoiding duplicate click triggers in upload component.

### MongoDB `AutoReconnect` / `getaddrinfo failed`

Cause: temporary DNS/network issue reaching MongoDB host.

Current worker behavior includes retry logic so transient failures do not permanently kill pipeline processing.

### Hugging Face warning about unauthenticated requests

Add `HF_TOKEN` in `backend/.env` and restart backend.

### `405 Method Not Allowed` on `/cases/upload-case`

Expected for `GET`; the endpoint supports `POST` upload only.

---

## Security Notes

- Never commit secrets (`.env`, API keys, DB passwords).
- Rotate keys immediately if exposed.
- CORS is configured for localhost by default; restrict origins before deployment.
- Current codebase focuses on local/dev workflow; authentication and production hardening should be added before public deployment.

---

## Future Enhancements

- Voice assistant for legal Q&A
- Better case-outcome modeling with richer training data
- Lawyer recommendation and legal aid routing
- Advanced analytics dashboard (judge/court trends, timelines)
- RBAC + auth for multi-user secure usage
- Background job queue backed by dedicated worker infrastructure

---

## Contribution Guidelines

1. Fork the repository.
2. Create a feature branch (`feature/your-feature-name`).
3. Keep commits focused and descriptive.
4. Add/adjust tests where possible.
5. Open a pull request with clear summary and screenshots (if UI changes).

Suggested commit style:

- `feat: add ...`
- `fix: resolve ...`
- `docs: update README ...`

---

## License

This project is currently for internal/academic usage.

If you want open-source distribution, add a license file (for example `MIT` or `Apache-2.0`) and update this section.

---

## Author

**Your Name**

- GitHub: `https://github.com/your-username`
- LinkedIn: `https://linkedin.com/in/your-profile`
- Email: `your-email@example.com`

---

## Screenshots (Placeholder)

Add screenshots to `docs/screenshots/` and reference them like below:

```md
![Upload Screen](docs/screenshots/upload.png)
![Summary Screen](docs/screenshots/summary.png)
![Chatbot Screen](docs/screenshots/chatbot.png)
```

---

If this project helped you, consider starring the repository.
