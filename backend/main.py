from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.database.mongo import connect_to_mongo, close_mongo_connection
from backend.routes.raw_judgment_routes import router as raw_judgment_router
from backend.routes.upload_routes import router as upload_router
from backend.routes.ai_routes import router as ai_router
from backend.routes.similarity_routes import router as similarity_router
from backend.routes.chatbot_routes import router as chatbot_router
from backend.routes.prediction_routes import router as prediction_router
from backend.routes.dashboard_routes import router as dashboard_router
from backend.routes.manual_prediction_routes import router as manual_prediction_router
from backend.services.pipeline_worker import pipeline_worker
from backend.ai.vector_store import vector_store

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(title="Legal AI Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler: ensures CORS headers are present on 500 errors.
# Starlette's default 500 handler bypasses the CORS middleware, so fetch() in
# the browser sees "No Access-Control-Allow-Origin" and masks the real error.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    headers = {
        "Access-Control-Allow-Origin":      origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0],
        "Access-Control-Allow-Credentials": "true",
    }
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "detail": type(exc).__name__},
        headers=headers,
    )

app.include_router(upload_router)
app.include_router(ai_router)
app.include_router(similarity_router)
app.include_router(chatbot_router)
app.include_router(prediction_router)
app.include_router(dashboard_router)
app.include_router(manual_prediction_router)
# ---- startup ----
@app.on_event("startup")
def startup():
    connect_to_mongo()
    pipeline_worker.start()
    # Re-load previously embedded cases into in-memory vector index so
    # similarity search works immediately without re-processing documents.
    try:
        loaded = vector_store.load_from_db()
        print(f"[startup] Vector store loaded {loaded} chunks from MongoDB.")
    except Exception as exc:
        print(f"[startup] Vector store reload skipped: {exc}")

# ---- shutdown ----
@app.on_event("shutdown")
def shutdown():
    pipeline_worker.stop()
    close_mongo_connection()

# ---- routes ----
app.include_router(raw_judgment_router)

@app.get("/")
def home():
    return {"message": "Legal AI Running"}
