# Legal AI

Legal AI is an upload-first court-document analysis system built with a FastAPI backend and a React + Vite frontend.

The application accepts a PDF or image, extracts text through OCR, stores the raw and cleaned document, runs metadata extraction, summary generation, translation, chunking, embeddings, similarity search, prediction, and exposes a legal chatbot on top of the stored case data.

## What Is Implemented

- Upload-only document ingestion pipeline
- OCR-based text extraction
- Metadata extraction with rule-based + AI fallback flow
- MongoDB storage for raw documents and AI artifacts
- MySQL storage for structured case records, audit logs, predictions, and feedback
- Background worker for multi-stage case processing
- Plain-language summaries and key points
- Regional-language translation for summaries and chatbot answers
- Similar-case search using keyword overlap + embeddings
- Automated and manual outcome prediction
- Legal chatbot with metadata mode, RAG mode, general legal mode, and hybrid mode
- Dashboard APIs for case history, coverage, audit, and pipeline status

## Tech Stack

- Backend: FastAPI
- Frontend: React + Vite
- Document store: MongoDB
- Structured store: MySQL
- OCR: `pdfplumber`, `pytesseract`, `Pillow`
- Embeddings / NLP: `sentence-transformers`, `transformers`, `scikit-learn`
- Optional LLM providers: Ollama and Groq

## Project Structure

```text
mini-pro/
|-- backend/
|   |-- ai/
|   |-- database/
|   |-- routes/
|   |-- services/
|   |-- utils/
|   |-- scripts/
|   `-- main.py
|-- frontend/
|   |-- src/
|   |-- public/
|   `-- package.json
|-- scripts/
|-- uploads/
`-- README.md
```

## End-to-End Implementation Flow

### 1. Frontend upload flow

1. User opens the upload screen in the React app.
2. The frontend sends the selected file to `POST /cases/upload-case`.
3. The backend stores the file under `uploads/`.
4. The frontend later consumes summary, translation, similarity, prediction, dashboard, and chatbot APIs.

### 2. Backend ingestion flow

The upload route is implemented in [backend/routes/upload_routes.py](backend/routes/upload_routes.py).

The route performs this sequence:

1. Save the uploaded file locally.
2. Run OCR / text extraction using `extract_text(...)`.
3. Normalize the text.
4. Split the text into paragraphs.
5. Detect the language code.
6. Run metadata extraction through `process_document_metadata(...)`.
7. Build a canonical case title from petitioner/respondent when available.
8. Insert the main document into MongoDB collection `raw_judgments`.
9. Validate metadata quality for SQL writes.
10. Upsert structured case metadata into MySQL when validation passes.
11. Enqueue the case into MongoDB collection `processing_queue`.

### 3. Metadata extraction flow

Metadata extraction is handled before the background worker starts the deeper NLP pipeline.

Current implementation characteristics:

- Rule-based metadata extraction runs first.
- AI fallback can use Ollama and/or Groq if the rule-based result is weak.
- A quality gate decides whether SQL writes are allowed.
- Audit information is stored so rule output, AI output, final merged output, and learning adjustments can be reviewed later.

### 4. Background worker flow

The worker runs from [backend/services/pipeline_worker.py](backend/services/pipeline_worker.py) and is started in [backend/main.py](backend/main.py) during FastAPI startup.

Queue progression:

```text
extracted -> cleaned -> summarized -> translated -> chunked -> embedded -> predicted -> completed
```

Stage details:

- `extracted`
  - Cleans raw OCR text
  - Detects language
  - Splits paragraphs
  - Updates `raw_judgments`
  - Writes initial structured case record to MySQL when allowed

- `cleaned`
  - Extracts basic facts
  - Generates structured summaries
  - Generates a plain-language `basic_summary`
  - Stores summary outputs in MongoDB and MySQL

- `summarized`
  - Translates the summary content, not the full raw document, for worker-generated translations
  - Stores translations in MongoDB and MySQL

- `translated`
  - Splits the cleaned text into overlapping chunks
  - Stores header and body chunks in `case_chunks`

- `chunked`
  - Generates embeddings for chunks
  - Stores embedding metadata in `embeddings_metadata`
  - Loads chunks into the in-memory vector store
  - Computes related cases for structured similarity links

- `embedded`
  - Runs historical outcome prediction
  - Stores prediction outputs in MongoDB and MySQL

- `predicted`
  - Marks the case as `completed`

### 5. Summary flow

Summary APIs are implemented in [backend/routes/ai_routes.py](backend/routes/ai_routes.py).

Current summary behavior:

- `GET /ai/summarize/{case_number}`
- Produces:
  - `basic_summary`
  - `short_summary`
  - `detailed_summary`
  - `key_points`
- Stores results in MongoDB collection `case_summaries`
- Writes summary rows to MySQL table `case_summaries`

### 6. Translation flow

Translation is also handled in [backend/routes/ai_routes.py](backend/routes/ai_routes.py).

Current translation behavior:

- `GET /ai/translate/{case_number}?language=<code>&mode=summary|raw`
- `mode=summary` translates user-facing summary content
- `mode=raw` translates the full cleaned document only on explicit request
- Cached translations are returned from MongoDB when available
- Proper nouns and legal tokens are protected before translation

### 7. Similar case flow

Similarity search is implemented in [backend/routes/similarity_routes.py](backend/routes/similarity_routes.py).

Current similarity behavior:

- Extracts keywords from:
  - acts / sections metadata
  - detected section references in the text
  - core legal terms such as IPC, CrPC, Constitution, Evidence Act, Contract Act
- Builds an embedding for the source case
- Compares source case to candidate cases
- Ranks using:
  - keyword overlap weight: 65%
  - semantic similarity weight: 35%
- Returns top matches through `GET /search/{case_number}`

### 8. Prediction flow

There are two prediction paths:

- Automatic case prediction
  - `GET /prediction/{case_number}`
  - Uses stored case text and historical heuristics

- Manual prediction tool
  - `POST /predict/manual`
  - Uses structured user inputs such as case type, court level, evidence strength, dispute type, relief type, and delay in filing
  - Returns plaintiff percentage, defendant percentage, confidence, and explanation

### 9. Chatbot flow

The chatbot route is implemented in [backend/routes/chatbot_routes.py](backend/routes/chatbot_routes.py) and the core logic lives in [backend/ai/legal_chatbot.py](backend/ai/legal_chatbot.py).

Current chatbot request flow:

1. Frontend builds `chat_history` from prior user and assistant messages.
2. Frontend sends `POST /chatbot/ask`.
3. Backend accepts:
   - `query`
   - `case_number`
   - `language`
   - `response_mode`
   - `chat_history`
4. `generate_answer(...)` routes the request into one of four modes:
   - `metadata`
   - `rag_content`
   - `legal_knowledge`
   - `hybrid`
5. Prompt builders format conversation history for both:
   - document-grounded prompts
   - general legal prompts
6. If a non-English language is requested, the final answer is translated for chatbot output.
7. The request/response pair is stored in MySQL table `chat_history`.

Supported chatbot `response_mode` values:

- `auto`
- `hybrid`
- `rag`
- `general`
- `metadata`

### 10. Dashboard and feedback flow

Dashboard endpoints are implemented in [backend/routes/dashboard_routes.py](backend/routes/dashboard_routes.py).

They provide:

- total case counts
- pipeline coverage metrics
- recent AI activity
- recent cases list
- per-case pipeline status
- SQL health check
- metadata audit history

Feedback endpoints are implemented in [backend/routes/feedback_routes.py](backend/routes/feedback_routes.py).

They allow:

- storing correction feedback for extracted metadata
- listing recent feedback entries

## Data Storage Overview

### MongoDB collections used

- `raw_judgments`
- `processing_queue`
- `case_facts`
- `case_summaries`
- `case_translations`
- `case_chunks`
- `embeddings_metadata`
- `case_predictions`
- `ai_outputs`

### MySQL tables used

The schema is created from [backend/scripts/init_legal_ai.sql](backend/scripts/init_legal_ai.sql).

Core tables include:

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

## Environment Files

Do not commit real secrets. Keep actual credentials only in local `.env` files.

### Backend env file

Create `backend/.env` with the following structure:

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
```

Meaning of backend env variables:

- `MONGO_URI`: MongoDB connection string
- `MONGO_DB`: MongoDB database name
- `MYSQL_HOST`: MySQL host
- `MYSQL_USER`: MySQL username
- `MYSQL_PASSWORD`: MySQL password
- `MYSQL_DB`: MySQL database name
- `GROQ_API_KEY`: optional Groq API key
- `GROQ_MODEL`: optional Groq model name
- `OLLAMA_BASE_URL`: optional Ollama server URL
- `OLLAMA_MODEL`: optional Ollama model name
- `FRONTEND_ORIGINS`: optional comma-separated extra frontend origins for CORS

### Frontend env file

Create `frontend/.env` with:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Meaning of frontend env variables:

- `VITE_API_BASE_URL`: backend base URL used by the React app

## Setup

### 1. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

### 2. Create environment files

PowerShell:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Then edit both `.env` files with your local values.

### 3. Create MySQL schema

Import the schema file:

```bash
mysql -u root -p < backend/scripts/init_legal_ai.sql
```

### 4. Run backend

```bash
uvicorn backend.main:app --reload
```

Run the command above from the repo root.

### 5. Run frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. Optional root-level helper scripts

From the repo root:

```bash
npm run frontend:install
npm run frontend:dev
npm run backend:install
npm run backend:dev
npm run setup
```

## Optional LLM Setup

### Ollama

```bash
ollama pull llama3
ollama run llama3
```

### Groq

Add `GROQ_API_KEY` in `backend/.env` if you want Groq fallback for metadata extraction and chatbot answers.

## Active API Endpoints

### Upload

- `POST /cases/upload-case`

### AI routes

- `GET /ai/summarize/{case_number}`
- `GET /ai/translate/{case_number}?language=hi&mode=summary`
- `GET /ai/case/{case_id}`
- `GET /ai/analyze/{case_number}`

### Similarity

- `GET /search/{case_number}`

### Chatbot

- `POST /chatbot/ask`

Example request body:

```json
{
  "query": "Summarize the main reasoning in this judgment",
  "case_number": "ABC/123/2024",
  "language": "en",
  "response_mode": "rag",
  "chat_history": [
    { "role": "user", "text": "Who is the petitioner?" },
    { "role": "assistant", "text": "The petitioner is ..." }
  ]
}
```

### Predictions

- `GET /prediction/{case_number}`
- `POST /predict/manual`

### Dashboard

- `GET /dashboard/overview`
- `GET /dashboard/metrics`
- `GET /dashboard/recent-activity`
- `GET /dashboard/cases`
- `GET /dashboard/pipeline/{case_number}`
- `GET /dashboard/sql-health`
- `GET /dashboard/audit/{case_id}`

### Feedback

- `POST /feedback`
- `GET /feedback`

### Disabled direct raw insert

- `POST /raw-judgments/insert`
  - intentionally disabled
  - upload flow must go through `/cases/upload-case`

## Frontend Behavior

The React app currently provides:

- Upload and analyze page
- Recent cases panel
- Similar-case viewer modal
- Translation controls
- Manual prediction page
- Floating legal chatbot
- Expand / collapse chatbot panel
- Chatbot markdown rendering for bullets, bold text, and blockquotes

## Notes

- This is an upload-driven system. Direct dataset insertion is intentionally blocked.
- Case numbers containing `/` are supported in path-based API routes.
- The backend starts the pipeline worker automatically on app startup.
- The backend reloads stored vector metadata on startup so similarity search works without re-uploading data.
- The chatbot endpoint is `POST`, not `GET`.

## License

Internal / academic project usage.
