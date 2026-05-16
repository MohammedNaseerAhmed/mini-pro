"""
Authentication Routes — /auth/*
Simple register / login / logout using bcrypt + JWT.
"""

import os
import datetime
import logging

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "lexai-super-secret-change-in-prod-2026")
JWT_ALG    = "HS256"
JWT_EXPIRE = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def _users_col():
    from backend.database.mongo import get_db  # type: ignore
    try:
        return get_db()["lex_users"]
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB unavailable for auth operations: {exc}",
        )


router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name:     str
    email:    str
    password: str


class LoginRequest(BaseModel):
    email:    str
    password: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_pw(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_token(user_id: str, email: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRE)
    return jwt.encode({"sub": user_id, "email": email, "exp": exp}, JWT_SECRET, algorithm=JWT_ALG)


def _set_cookie(response: Response, token: str):
    response.set_cookie(
        key="lex_token", value=token,
        httponly=True, samesite="lax", secure=False,
        max_age=JWT_EXPIRE * 3600, path="/",
    )


def get_current_user(request: Request) -> dict:
    token = request.cookies.get("lex_token") or \
            request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/register", status_code=201)
async def register(body: RegisterRequest, response: Response):
    name     = body.name.strip()
    email    = body.email.strip().lower()
    password = body.password

    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty.")
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email address.")
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    col = _users_col()
    if col.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    doc = {
        "name":       name,
        "email":      email,
        "password":   _hash_pw(password),
        "created_at": datetime.datetime.utcnow().isoformat(),
        "active":     True,
    }
    result  = col.insert_one(doc)
    user_id = str(result.inserted_id)
    token   = _create_token(user_id, email)
    _set_cookie(response, token)

    return {
        "message": "Account created successfully.",
        "token":   token,
        "user":    {"id": user_id, "name": name, "email": email},
    }


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    email    = body.email.strip().lower()
    password = body.password

    col  = _users_col()
    user = col.find_one({"email": email})
    if not user or not _verify_pw(password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    user_id = str(user["_id"])
    token   = _create_token(user_id, email)
    _set_cookie(response, token)

    return {
        "message": "Logged in successfully.",
        "token":   token,
        "user":    {"id": user_id, "name": user["name"], "email": email},
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="lex_token", path="/")
    return {"message": "Logged out successfully."}


@router.get("/me")
async def me(current: dict = Depends(get_current_user)):
    return {"email": current["email"], "sub": current["sub"]}
