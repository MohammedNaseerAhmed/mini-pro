from fastapi import APIRouter, HTTPException
from backend.models.raw_judgment_model import RawJudgment

router = APIRouter(prefix="/raw-judgments", tags=["Raw Judgments"])


# INSERT DOCUMENT
@router.post("/insert")
def insert_raw_judgment(judgment: RawJudgment):
    raise HTTPException(
        status_code=400,
        detail="Direct dataset insert is disabled. Use /cases/upload-case so OCR and pipeline stages run automatically.",
    )
