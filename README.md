# Legal AI (Upload-Only Pipeline)

Legal AI backend + frontend for court judgment processing.

This project is **upload-driven only**: users upload case files (PDF/image), text is extracted, and AI features are generated from uploaded content.

## Features

1. Language Translation
- Supports `en`, `hi`, `te` (and additional fallback languages in module).
- Preserves legal terms such as `IPC`, `CrPC`, and `Section <number>`.

2. Legal Summarization
- `short_summary` (3-5 lines)
- `detailed_summary` (facts, issues, reasoning, decision)
- `key_points` (6-10 bullet points)

3. Similar Case Finder
- Keyword-based + semantic scoring.
- Uses acts/sections/issue keywords and embedding similarity.
- Returns top 5 matches with similarity score.

4. Winning Probability Prediction
- Uses baseline + historical case outcomes from existing records.
- Returns predicted outcome, probability/confidence, and factors.

5. Legal Chatbot (RAG-style)
- Retrieves relevant case context and answers legal questions.
- Can also respond to summary/translation intents from user prompts.

## Project Structure

- `backend/` FastAPI backend, AI modules, queue worker
- `frontend/` React (Vite) frontend

## Tech Stack

- FastAPI
- MongoDB (raw text, chunks, embeddings metadata, AI outputs)
- MySQL (structured legal tables)
- React + Vite frontend

## Upload Processing Pipeline

`UPLOAD -> OCR/TEXT EXTRACTION -> RAW STORE -> CLEAN/PARAGRAPHS/LANGUAGE -> FACTS -> SUMMARIES -> TRANSLATION -> CHUNKING -> EMBEDDINGS -> SIMILARITY -> PREDICTION -> COMPLETED`

Queue processor collection: `processing_queue`.

## Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create environment file:

```bash
cp .env.example .env
```

Set values in `backend/.env`:

- `MONGO_URI`
- `MONGO_DB`
- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DB`

Run backend:

```bash
uvicorn backend.main:app --reload
```

### 2. Database Schema

Use SQL file:

- `backend/scripts/init_legal_ai.sql`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default:
- `http://localhost:5173`

Backend default:
- `http://127.0.0.1:8000`

## Frontend API Environment

Set backend URL via:

- `frontend/.env.development`
- `frontend/.env.staging`
- `frontend/.env.production`

Variable:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Core API Endpoints

### Upload
- `POST /cases/upload-case`

### Feature Status for a Case
- `GET /cases/features/{case_number}`

### Analyze Case (final consolidated output)
- `GET /ai/analyze/{case_number}?language=en|hi|te`

Response format:

```json
{
  "translation": {"language": "hi", "text": "...", "model_used": "..."},
  "summaries": {
    "short": "...",
    "detailed": "...",
    "key_points": ["...", "..."]
  },
  "similar_cases": [
    {"case_number": "...", "title": "...", "court": "...", "similarity_score": 0.84}
  ],
  "prediction": {
    "outcome": "Likely to Win",
    "probability": 0.73,
    "confidence": 0.73,
    "factors": ["...", "..."]
  }
}
```

### Individual Modules
- `GET /ai/summarize/{case_number}`
- `GET /ai/translate/{case_number}?language=hi|te|ur|simple_en`
- `GET /search/{case_number}`
- `GET /prediction/{case_number}`
- `GET /chatbot/ask?q=...`

### Dashboard
- `GET /dashboard/overview`
- `GET /dashboard/metrics`
- `GET /dashboard/cases`
- `GET /dashboard/pipeline/{case_number}`
- `GET /dashboard/recent-activity`
- `GET /dashboard/sql-health`

## Notes

- The app is configured for **upload-only data flow** (dataset bulk insert route is disabled).
- For case numbers containing `/`, API routes support path-style case numbers.
- If transformer models are unavailable, fallback logic still returns usable output.

## License

Internal/academic project usage.
