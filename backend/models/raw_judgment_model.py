from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ---------------- DATES ----------------
class CaseDates(BaseModel):
    filing_date: Optional[datetime] = None
    registration_date: Optional[datetime] = None
    decision_date: Optional[datetime] = None


# ---------------- PARTIES ----------------
class Parties(BaseModel):
    petitioner: Optional[str] = None
    respondent: Optional[str] = None
    advocates: List[str] = []


# ---------------- FILE INFO ----------------
class FileInfo(BaseModel):
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size_kb: Optional[int] = None
    stored_path: Optional[str] = None
    upload_time: Optional[datetime] = None
    uploaded_by: Optional[str] = "user"


# ---------------- OCR DATA ----------------
class OCRData(BaseModel):
    engine: Optional[str] = None
    ocr_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    language_detected: Optional[str] = None
    page_count: Optional[int] = None
    raw_extracted_text: Optional[str] = None


# ---------------- PARAGRAPH ----------------
class Paragraph(BaseModel):
    para_no: int
    text: Optional[str] = None


# ---------------- JUDGMENT TEXT ----------------
class JudgmentText(BaseModel):
    raw_text: Optional[str] = None
    clean_text: Optional[str] = None
    language: Optional[str] = "en"
    token_count: Optional[int] = None
    paragraphs: List[Paragraph] = []


# ---------------- ENTITIES ----------------
class ExtractedEntities(BaseModel):
    persons: List[str] = []
    organizations: List[str] = []
    locations: List[str] = []
    dates: List[str] = []
    legal_provisions: List[str] = []


# ---------------- CASE ANALYSIS ----------------
class CaseAnalysis(BaseModel):
    case_type_predicted: Optional[str] = None
    legal_domain: Optional[str] = None
    key_issues: List[str] = []
    facts_summary: Optional[str] = None


# ---------------- NLP FLAGS ----------------
class NLPFlags(BaseModel):
    text_cleaned: bool = False
    entities_extracted: bool = False
    summarized: bool = False
    translated: bool = False
    classified: bool = False
    embedded: bool = False
    chunks_created: bool = False
    prediction_done: bool = False


# ---------------- CHUNKING ----------------
class Chunking(BaseModel):
    chunk_count: int = 0
    chunk_size: Optional[int] = None
    overlap: Optional[int] = None
    last_chunked_at: Optional[datetime] = None


# ---------------- EMBEDDING ----------------
class Embedding(BaseModel):
    embedding_model: Optional[str] = None
    vector_dimension: Optional[int] = None
    stored_in_vector_db: bool = False
    embedded_at: Optional[datetime] = None


# ---------------- PREDICTION ----------------
class Prediction(BaseModel):
    predicted_outcome: Optional[str] = None
    win_probability: Optional[float] = None
    confidence_score: Optional[float] = None
    model_version: Optional[str] = None
    predicted_at: Optional[datetime] = None


# ---------------- SOURCE TRACKING ----------------
class Source(BaseModel):
    website: Optional[str] = None
    pdf_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    verified: bool = False


# ---------------- MAIN DOCUMENT ----------------
class RawJudgment(BaseModel):
    source_type: str  # upload / dataset
    dataset_name: Optional[str] = None
    import_batch_id: Optional[str] = None

    case_id_mysql: Optional[int] = None

    case_number: Optional[str] = None
    title: Optional[str] = None
    court_name: Optional[str] = None
    court_level: Optional[str] = None
    bench: Optional[str] = None

    dates: Optional[CaseDates] = CaseDates()

    parties: Optional[Parties] = Parties()
    judges: List[str] = []
    acts_sections: List[dict] = []

    file_info: Optional[FileInfo] = FileInfo()
    ocr_data: Optional[OCRData] = OCRData()
    judgment_text: Optional[JudgmentText] = JudgmentText()

    extracted_entities: Optional[ExtractedEntities] = ExtractedEntities()
    case_analysis: Optional[CaseAnalysis] = CaseAnalysis()

    nlp_flags: Optional[NLPFlags] = NLPFlags()
    chunking: Optional[Chunking] = Chunking()
    embedding: Optional[Embedding] = Embedding()
    prediction: Optional[Prediction] = Prediction()

    source: Optional[Source] = Source()

    processing_status: str = "uploaded"
    error_logs: List[str] = []
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
