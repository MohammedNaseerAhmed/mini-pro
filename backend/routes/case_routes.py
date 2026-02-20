from fastapi import APIRouter, UploadFile, File
from backend.database.mongo import get_db
import os
import uuid

router = APIRouter()

UPLOAD_DIR = "uploaded_cases"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload-case")
async def upload_case(file: UploadFile = File(...)):
    db = get_db()

    file_id = str(uuid.uuid4())
    file_path = f"{UPLOAD_DIR}/{file_id}_{file.filename}"

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    case_doc = {
        "file_name": file.filename,
        "stored_path": file_path,
        "status": "uploaded"
    }

    result = db.cases.insert_one(case_doc)

    return {"message": "Case uploaded", "case_id": str(result.inserted_id)}