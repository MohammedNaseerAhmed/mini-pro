from fastapi import APIRouter
from backend.database.mongo import get_db
from backend.ai.predictor import predict_case_with_history

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.get("/{case_id:path}")
def predict(case_id: str):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_id})

    if not case:
        return {"error": "case not found"}

    text = case.get("judgment_text", {}).get("raw_text", "")

    result = predict_case_with_history(text)

    return {"case_number": case_id, **result}
