from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database.mongo import connect_to_mongo, close_mongo_connection
from backend.routes.raw_judgment_routes import router as raw_judgment_router
from backend.routes.upload_routes import router as upload_router
from backend.routes.ai_routes import router as ai_router
from backend.routes.similarity_routes import router as similarity_router
from backend.routes.chatbot_routes import router as chatbot_router
from backend.routes.prediction_routes import router as prediction_router
from backend.routes.dashboard_routes import router as dashboard_router
from backend.services.pipeline_worker import pipeline_worker
app = FastAPI(title="Legal AI Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(upload_router)
app.include_router(ai_router)
app.include_router(similarity_router)
app.include_router(chatbot_router)
app.include_router(prediction_router)
app.include_router(dashboard_router)
# ---- startup ----
@app.on_event("startup")
def startup():
    connect_to_mongo()
    pipeline_worker.start()

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
