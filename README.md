# ⚖️ LexAI — Legal Intelligence Platform

> **Enterprise-grade AI platform for Indian legal professionals.** Upload documents, get AI summaries, map IPC→BNS sections, predict outcomes, check ADR eligibility, and sync live eCourts data — all in one dark-luxury interface.

---

## 📋 Table of Contents

1. [Project Overview](#-project-overview)
2. [Tech Stack](#-tech-stack)
3. [Architecture](#-architecture)
4. [Features](#-features)
5. [Database Schema](#-database-schema)
6. [API Reference](#-api-reference)
7. [Frontend Components](#-frontend-components)
8. [Environment Setup](#-environment-setup)
9. [Installation & Running](#-installation--running)
10. [Project Structure](#-project-structure)
11. [Design System](#-design-system)
12. [How It Was Built](#-how-it-was-built)

---

## 🧠 Project Overview

**LexAI** is a full-stack Legal AI platform built for Indian advocates, paralegals, and legal researchers. It combines:

- **Document Intelligence** — PDF/image upload with OCR, AI summarisation, multi-language translation
- **BNS Citation Mapper** — Maps deprecated IPC/CrPC/IEA sections to modern BNS/BNSS/BSA (July 2024)
- **ADR Suitability Engine** — NALSA-informed scoring to assess Lok Adalat / arbitration eligibility
- **eCourts AI Assistant** — Guided NJDG portal navigation + CAPTCHA-based live case sync
- **Win Probability Predictor** — Rule-based + ML case outcome prediction
- **AI Legal Chatbot** — Multi-language counsel chatbot with case context
- **DB Intelligence Layer** — Live analytics dashboard over 20 MySQL tables

---

## 🛠 Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API Framework | **FastAPI** (Python 3.11+) |
| ASGI Server | **Uvicorn** |
| Primary Database | **MySQL** (20 relational tables) |
| Document Store | **MongoDB** (raw judgments, vectors) |
| AI / LLM | **Groq API** (llama-3.3-70b-versatile) + **Ollama** (local llama3) |
| Embeddings | **sentence-transformers** (all-MiniLM-L6-v2) |
| Similarity Search | **scikit-learn** cosine similarity (in-memory vector store) |
| PDF Extraction | **pdfplumber** |
| OCR | **pytesseract** + **Pillow** |
| Web Scraping | **requests** + **BeautifulSoup4** (eCourts portal) |
| Translation | **deep-translator** (Google Translate API) |
| Scheduler | **APScheduler** (eCourts background sync) |
| Auth | **bcrypt** + **PyJWT** |

### Frontend
| Layer | Technology |
|---|---|
| Framework | **React 18** (Vite) |
| Styling | **Tailwind CSS** + Vanilla CSS (custom design tokens) |
| Fonts | Cormorant Garamond, DM Sans, IBM Plex Mono |
| HTTP | Native `fetch` API |
| Routing | Hash-based (`#/page`) — no React Router |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                        │
│  Vite + TailwindCSS · Hash Router · Dark Luxury UI      │
└───────────────┬─────────────────────────────────────────┘
                │  REST API (JSON)
                ▼
┌─────────────────────────────────────────────────────────┐
│                 FASTAPI BACKEND                          │
│  15 Route modules · CORS middleware · Global exc handler│
├────────────┬──────────────┬──────────────┬──────────────┤
│  Pipeline  │  AI Services │  DB Intel    │  eCourts     │
│  Worker    │  (Groq/LLM)  │  Layer       │  Scheduler   │
└────────────┴──────┬───────┴──────┬───────┴──────────────┘
                    │              │
          ┌─────────▼──┐   ┌───────▼──────┐
          │  MongoDB   │   │    MySQL      │
          │ (vectors,  │   │ (20 tables,  │
          │  raw text) │   │  all features)│
          └────────────┘   └──────────────┘
```

### Data Flow — Document Upload
```
User uploads PDF/Image
        ↓
UploadZone.jsx  →  POST /upload
        ↓
pipeline_worker.py  (background thread)
        ↓
pdfplumber / pytesseract  →  raw text
        ↓
metadata_pipeline.py  →  extract case metadata
        ↓
section_mapper_service.py  →  detect IPC/BNS citations
        ↓
MongoDB  (raw text + embeddings)
MySQL   (case_files, case_metadata, bns_mappings)
        ↓
vector_store.add()  →  in-memory cosine index
```

---

## ✨ Features

### 1. 📄 Document Intelligence (Workspace)
- **Upload** PDF or image files (drag-and-drop or click)
- **OCR fallback** — pytesseract for scanned documents
- **Auto metadata extraction** — case number, parties, court, judge, year
- **AI Summarisation** — Groq LLM generates plain-language case brief
- **Key Legal Points** — structured bullet extraction
- **Multi-Language Translation** — 7 Indian languages (Hindi, Telugu, Kannada, Tamil, Malayalam, Marathi + Simple English)
- **Precedent Search** — cosine similarity against embedded case database

**Endpoint:** `POST /upload` · `GET /ai/summarize/{case}` · `GET /ai/translate/{case}`

---

### 2. 📖 BNS Section Mapper
Implements the July 1, 2024 criminal law reform (IPC → BNS, CrPC → BNSS, IEA → BSA).

#### Sub-features:
| Feature | Description |
|---|---|
| **Section Lookup** | Search any IPC/CrPC/IEA section → get BNS/BNSS/BSA equivalent |
| **FIR Analyzer** | Paste raw FIR/charge sheet text → AI extracts all citations and maps them |
| **Draft Rewriter** | Paste legal petition → auto-replaces all deprecated sections inline |
| **Change Types** | Retained · Modified · Merged · Replaced · Split |
| **Era Detection** | Labels documents: Pre-2024 / Transitional / BNS-Compliant |

**Endpoints:** `GET /bns/lookup` · `POST /bns/analyze-text` · `POST /bns/rewrite-draft`

**Database:** `bns_section_mappings` table (80+ mappings from MHA gazette)

---

### 3. ⚖️ ADR Suitability Predictor
Rule-based + AI scoring engine aligned with NALSA guidelines.

#### Scoring Factors:
- Case type (civil preferred over criminal)
- Claim amount vs. Lok Adalat thresholds
- Number of parties
- Case age / pendency
- Prior settlement attempts
- Subject-matter keywords (family, property, motor accident, cheque dishonour)

#### Output:
- **Suitability score** (0–100%)
- **ADR pathway** — Lok Adalat / Arbitration / Mediation / Conciliation
- **Settlement range** estimate
- **AI-drafted referral application** (ready to file)
- **Case Lookup mode** — load stored ADR data for any case number
- **Manual mode** — enter case details directly without uploading

**Endpoints:** `GET /adr/assessment/{case}` · `POST /adr/manual-assess` · `POST /adr/generate-application`

---

### 4. 🏛️ eCourts Intelligence

#### 4a. AI Guide (ECourtsAssistant)
- Detects **search method** from free-text query (CNR / case number / party name / FIR / advocate / act+section)
- Returns **step-by-step instructions** for the official eCourts portal
- Shows **confidence level** and **portal URL**
- Quick-pick example buttons for common query types

#### 4b. Paste & Analyze
- User copies text from eCourts result page → pastes here
- System auto-extracts: **CNR**, parties, next hearing, legal sections
- **BNS auto-mapping** of all extracted sections
- **ADR eligibility hint**
- Saves CNR to MySQL if case reference provided

#### 4c. Live Sync (eCourtsStatus)
- **CAPTCHA flow** — fetches live CAPTCHA from eCourts portal using `requests.Session`
- Submit CNR + CAPTCHA → live case data from NJDG
- **AI urgency scoring** on hearing dates (Critical / High / Medium / Low)
- **Hearing history** tab
- **AI Case Brief** tab
- Background **APScheduler** refreshes synced cases every 6 hours

**Endpoints:** `POST /ecourts/guide` · `POST /ecourts/analyze-pasted` · `GET /ecourts/captcha` · `POST /ecourts/live-search` · `GET /ecourts/status/{case}`

---

### 5. 🔮 Win Probability Predictor (Predict Page)
- Input: case type, court level, evidence count, witness count, delay (years), legal representation
- Rule-based scoring + normalised ML features
- Outputs: **win %**, **risk level**, **key factors**, **recommendations**
- Manual entry form with dark-luxury gold-input fields

**Endpoint:** `POST /predict/manual`

---

### 6. 🤖 AI Legal Chatbot
- Floating persistent chatbot on Workspace page
- **Case-context aware** — uses uploaded case number for grounded answers
- **Multi-language** — replies in 7 Indian languages + English
- **Groq LLM** backend (llama-3.3-70b) with legal system prompt
- Streaming-ready response architecture
- Conversation history maintained in component state

**Endpoint:** `POST /chatbot/ask`

---

### 7. 🧠 DB Intelligence Dashboard
- **Live read-out** of all 20 MySQL tables
- Row counts, index health, last-write timestamps
- Feature routing map — shows which tables serve which features
- Table search + filter
- One-click **Refresh** with last-updated timestamp

**Endpoint:** `GET /intelligence/overview` · `GET /intelligence/table/{name}`

---

### 8. 🔐 Authentication
- **Register / Login** with email + password
- Passwords hashed with **bcrypt**
- **JWT** tokens (stored in component state, not localStorage for security)
- Auth gate — entire app behind login wall
- Dark-luxury AuthPage with animated gold gradient

**Endpoints:** `POST /auth/register` · `POST /auth/login` · `GET /auth/me`

---

## 🗄 Database Schema

### MySQL Tables (20 total)

| Table | Purpose |
|---|---|
| `case_files` | Uploaded documents — filename, status, timestamps |
| `case_metadata` | Extracted metadata — court, judge, parties, year |
| `case_sections` | Legal sections cited per case |
| `bns_section_mappings` | IPC/CrPC/IEA → BNS/BNSS/BSA official mappings |
| `bns_case_mappings` | Per-case BNS mapping results |
| `adr_assessments` | ADR scoring results per case |
| `adr_factors` | Individual factor scores |
| `ecourts_cases` | Live-synced eCourts case data |
| `ecourts_hearings` | Hearing history records |
| `predictions` | Win probability prediction results |
| `users` | Auth — email, hashed password, created_at |
| `user_sessions` | JWT session tracking |
| `chatbot_sessions` | Chat history per user/case |
| `feedback` | User feedback on AI responses |
| `translations` | Cached translated summaries |
| `ai_summaries` | Cached Groq-generated summaries |
| `similar_cases` | Similarity search results cache |
| `document_embeddings` | Vector chunk metadata |
| `pipeline_queue` | Background processing job queue |
| `intelligence_events` | DB layer audit/event log |

### MongoDB Collections

| Collection | Purpose |
|---|---|
| `cases` | Raw extracted text, full document content |
| `embeddings` | Sentence chunk vectors (384-dim) |
| `judgments` | Raw judgment text for vector search |

---

## 🔌 API Reference

### Upload & Documents
```
POST   /upload                          # Upload PDF/image, enqueue pipeline
GET    /cases/{case_number}             # Get case metadata
GET    /raw/{case_number}               # Raw extracted text
```

### AI Features
```
GET    /ai/summarize/{case_number}      # Generate AI case summary
GET    /ai/translate/{case}?language=   # Translate summary/full text
GET    /search/{case_number}            # Find similar cases (cosine)
POST   /chatbot/ask                     # AI chatbot response
```

### BNS Mapper
```
GET    /bns/lookup?act=IPC&section=302  # Single section lookup
GET    /bns/case-report/{case}          # Full case BNS audit
POST   /bns/analyze-text               # Extract + map citations from text
POST   /bns/rewrite-draft              # Auto-rewrite document
```

### ADR
```
GET    /adr/assessment/{case}           # Stored ADR assessment
POST   /adr/manual-assess              # Manual input assessment
POST   /adr/generate-application       # Draft Lok Adalat application
```

### eCourts
```
POST   /ecourts/guide                   # Detect search method, return steps
POST   /ecourts/analyze-pasted          # Extract + map pasted case text
GET    /ecourts/captcha                 # Fetch live CAPTCHA from portal
POST   /ecourts/live-search             # Submit CNR + CAPTCHA, get live data
GET    /ecourts/status/{case}           # Stored eCourts data for case
```

### Prediction
```
POST   /predict/manual                  # Win probability (manual input)
```

### Intelligence
```
GET    /intelligence/overview           # All 20 table stats
GET    /intelligence/table/{name}       # Single table deep-dive
```

### Auth
```
POST   /auth/register                   # Create account
POST   /auth/login                      # Get JWT token
GET    /auth/me                         # Verify token, get user info
```

---

## 🖥 Frontend Components

| Component | File | Purpose |
|---|---|---|
| **App.jsx** | `src/App.jsx` | Root — hash router, page renders, shared helpers |
| **AuthPage** | `AuthPage.jsx` | Login/Register with animated dark form |
| **UploadZone** | `UploadZone.jsx` | Drag-and-drop PDF upload with progress |
| **Chatbot** | `Chatbot.jsx` | Floating AI chatbot with multi-language select |
| **BNSComponents** | `BNSComponents.jsx` | SectionLookupPage, DraftAnalyzer, DocumentRewriter |
| **ADRPanel** | `ADRPanel.jsx` | ADR scoring display + application generator |
| **ECourtsAssistant** | `ECourtsAssistant.jsx` | 3-step guided portal navigator + paste analyzer |
| **eCourtsStatus** | `eCourtsStatus.jsx` | CAPTCHA live sync, tabs: overview/history/AI |
| **PredictionPage** | `PredictionPage.jsx` | Win probability form + results |
| **IntelligenceDashboard** | `IntelligenceDashboard.jsx` | Live DB layer analytics |
| **RecentCasesPanel** | `RecentCasesPanel.jsx` | Workspace history of uploaded cases |

---

## ⚙️ Environment Setup

Create `backend/.env` from the example:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=legal_ai_mongo

# MySQL
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=legal_ai

# LLM — Groq (cloud, fast)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.3-70b-versatile

# LLM — Ollama (local fallback)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# CORS
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## 🚀 Installation & Running

### Prerequisites
- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- MongoDB 6.0+
- Tesseract OCR (`brew install tesseract` / `apt install tesseract-ocr`)
- *(Optional)* Ollama for local LLM

### Step 1 — Clone & Setup Backend

```bash
git clone <repo-url>
cd mini-pro

# Create virtual environment
python -m venv backend/.venv
source backend/.venv/bin/activate        # Windows: backend\.venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Copy and fill environment variables
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials
```

### Step 2 — Setup Databases

```bash
# MySQL — create database and run migrations
mysql -u root -p -e "CREATE DATABASE legal_ai;"
# The app auto-creates tables on first startup

# MongoDB — just ensure it's running
mongod --dbpath /data/db
```

### Step 3 — Run Backend

```bash
# From project root
uvicorn backend.main:app --reload --port 8000
```

Backend starts at: `http://127.0.0.1:8000`  
Interactive API docs: `http://127.0.0.1:8000/docs`

### Step 4 — Setup & Run Frontend

```bash
cd frontend
npm install
cp .env.example .env        # set VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Frontend starts at: `http://localhost:5173`

---

## 📁 Project Structure

```
mini-pro/
├── backend/
│   ├── main.py                      # FastAPI app, middleware, startup/shutdown
│   ├── requirements.txt             # Python dependencies
│   ├── .env / .env.example          # Environment config
│   │
│   ├── routes/                      # API route handlers (15 modules)
│   │   ├── upload_routes.py         # Document upload + pipeline trigger
│   │   ├── ai_routes.py             # Summarize, translate, case viewer
│   │   ├── similarity_routes.py     # Cosine similarity search
│   │   ├── chatbot_routes.py        # AI chatbot endpoint
│   │   ├── bns_routes.py            # BNS lookup, analyze, rewrite
│   │   ├── adr_routes.py            # ADR scoring + application gen
│   │   ├── ecourts_routes.py        # eCourts guide, CAPTCHA, live-search
│   │   ├── prediction_routes.py     # Win probability
│   │   ├── manual_prediction_routes.py  # Manual prediction form
│   │   ├── intelligence_routes.py   # DB intelligence layer
│   │   ├── auth_routes.py           # Register/login/JWT
│   │   ├── dashboard_routes.py      # Dashboard analytics
│   │   ├── feedback_routes.py       # User feedback collection
│   │   └── raw_judgment_routes.py   # Raw text retrieval
│   │
│   ├── services/                    # Business logic layer
│   │   ├── pipeline_worker.py       # Background document processor (threading)
│   │   ├── section_mapper_service.py    # IPC→BNS citation extraction
│   │   ├── adr_suitability_service.py   # ADR scoring engine
│   │   ├── ecourts_scraper.py           # NJDG portal scraper + CAPTCHA
│   │   ├── ecourts_service.py           # eCourts DB operations
│   │   ├── ecourts_scheduler.py         # APScheduler background sync
│   │   ├── db_intelligence.py           # Live MySQL table analytics
│   │   ├── metadata_pipeline.py         # Case metadata extraction
│   │   └── learning_engine.py           # Adaptive scoring feedback loop
│   │
│   ├── ai/
│   │   └── vector_store.py          # In-memory cosine similarity index
│   │
│   ├── database/
│   │   ├── mongo.py                 # MongoDB connection pool
│   │   └── mysql.py                 # MySQL connection pool
│   │
│   └── models/                      # Pydantic request/response schemas
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Root component, all page functions, router
│   │   ├── main.jsx                 # React entry point
│   │   ├── styles.css               # Global design system (tokens, components)
│   │   │
│   │   └── components/
│   │       ├── AuthPage.jsx         # Login + Register
│   │       ├── UploadZone.jsx       # File upload UI
│   │       ├── Chatbot.jsx          # Floating AI chatbot
│   │       ├── BNSComponents.jsx    # Section Lookup, FIR Analyzer, Rewriter
│   │       ├── ADRPanel.jsx         # ADR assessment display
│   │       ├── ECourtsAssistant.jsx # AI guide + paste analyzer
│   │       ├── eCourtsStatus.jsx    # CAPTCHA live sync panel
│   │       ├── PredictionPage.jsx   # Win probability form
│   │       ├── IntelligenceDashboard.jsx  # DB layer analytics
│   │       └── RecentCasesPanel.jsx # Upload history
│   │
│   ├── package.json
│   └── vite.config.js
│
├── uploads/                         # Uploaded PDF files (gitignored)
├── logs/                            # Server logs
└── scripts/                         # Utility / seed scripts
```

---

## 🎨 Design System

### Color Tokens (CSS Variables)
```css
--bg-primary:    #0A0E1A    /* Deep navy background */
--bg-elevated:   #11131C    /* Card surfaces */
--text-primary:  #F5F7FA    /* Primary text */
--text-secondary:#B8BCC8    /* Secondary text */
--text-muted:    #6B7280    /* Placeholder / labels */
--border-gold:   rgba(201,168,76,0.18)   /* Gold accent borders */
--border-subtle: rgba(255,255,255,0.06)  /* Subtle dividers */
```

### Gold Accent Palette
```
#C9A84C  — Primary gold (buttons, active states, focus rings)
#E3B341  — Bright gold (hover, highlights)
#A0832A  — Deep gold (pressed states)
```

### Component Classes
| Class | Usage |
|---|---|
| `.glass-card` | Dark glassmorphism card with gold border |
| `.gold-input` | Dark input field with gold focus ring |
| `.gold-textarea` | Multi-line version of gold-input |
| `.gold-select` | Custom select with gold SVG chevron |
| `.btn-primary` | Gold gradient button |
| `.btn-secondary` | Outlined gold button |
| `.btn-ghost` | Text-only button |
| `.label-xs` | 10px uppercase tracking label |
| `.form-label` | Input label above gold-input |
| `.tab-bar` | Tab switcher container |
| `.tab-btn` | Tab button with active gold state |
| `.page-hero` | Dark slate-900 hero card |
| `.progress-track` | Progress bar track |
| `.progress-fill` | Animated progress fill |

### Typography
```
Headings:    Cormorant Garamond (serif, legal authority feel)
Body:        DM Sans (clean, readable)
Code/Mono:   IBM Plex Mono (CNR numbers, section citations)
```

---

## 🏗 How It Was Built

### Phase 1 — Foundation
1. Initialised **Vite + React** frontend and **FastAPI** backend
2. Set up **MySQL** schema with 20 normalised tables
3. Set up **MongoDB** for document storage and embedding vectors
4. Built basic **upload pipeline** — PDF → text → MongoDB storage

### Phase 2 — Core AI Features
1. Integrated **pdfplumber** for structured PDF text extraction
2. Added **pytesseract OCR** fallback for scanned image documents
3. Connected **Groq API** (llama-3.3-70b) for AI summarisation
4. Built **sentence-transformers** embedding pipeline + cosine similarity search
5. Implemented **deep-translator** for 7-language translation

### Phase 3 — Legal Intelligence
1. Built **BNS Section Mapper** — 80+ mappings seeded from MHA gazette PDFs into MySQL
2. Implemented **FIR text analyzer** using regex + DB lookup for citation extraction
3. Built **draft auto-rewriter** with inline section substitution
4. Implemented **ADR suitability engine** with NALSA-informed scoring rules

### Phase 4 — eCourts Integration
1. Built **eCourts web scraper** using `requests.Session` + BeautifulSoup for CAPTCHA handling
2. Implemented **3-step AI guide** — free-text query → method detection → step-by-step instructions
3. Added **paste-and-analyze** workflow — extract CNR/parties/sections from copied portal text
4. Set up **APScheduler** for background case status refresh (every 6 hours)

### Phase 5 — Auth & Security
1. Built **JWT authentication** with bcrypt password hashing
2. Added auth gate — entire app protected behind login
3. Implemented global CORS middleware with regex origin matching
4. Added global exception handler to preserve CORS headers on 500 errors

### Phase 6 — DB Intelligence Layer
1. Built **db_intelligence.py** service — live MySQL table analytics
2. Created **IntelligenceDashboard** component with table search + metrics
3. Routed all feature data access through centralised MySQL service layer

### Phase 7 — UI/UX Overhaul (Dark Luxury)
1. Designed **CSS design token system** in `styles.css` (CSS custom properties)
2. Built `.glass-card`, `.gold-input`, `.gold-textarea`, `.gold-select` component classes
3. Migrated all components from light Tailwind classes to dark luxury equivalents
4. Standardised all page heroes to `bg-slate-900` card with ambient blobs
5. Implemented responsive layouts across all 6 pages

---

## 🔑 Key Decisions

| Decision | Reason |
|---|---|
| **FastAPI over Django** | Async-first, auto OpenAPI docs, faster for AI inference endpoints |
| **MySQL as primary DB** | Relational integrity for legal mappings, indexed joins for BNS lookup |
| **MongoDB alongside** | Flexible schema for raw text + high-dimensional embedding vectors |
| **Hash router (no React Router)** | Simpler SPA deployment, no server-side routing config needed |
| **Groq API (not OpenAI)** | Free tier, llama-3.3-70b is fast and excellent for legal reasoning |
| **sentence-transformers local** | No API cost per embedding, runs on CPU |
| **CAPTCHA via requests.Session** | Preserves cookies across CAPTCHA fetch + CNR submit to eCourts portal |
| **APScheduler in-process** | Lightweight — avoids Celery/Redis setup for scheduled sync |

---

## 📄 License

MIT License — © 2024 Mohammed Naseer Ahmed

---

*Built with ❤️ for Indian legal professionals. LexAI is an educational tool and does not constitute legal advice.*
