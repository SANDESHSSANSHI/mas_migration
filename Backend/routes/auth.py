# === routes/auth.py ===

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from services.auth_service import (
    create_user, UserSignup,
    get_account_details, change_password
)
from utils.couchdb import get_session_info
import os
from dotenv import load_dotenv
import httpx
from http.cookies import SimpleCookie

load_dotenv()
COUCHDB_URL = os.getenv("COUCHDB_URL")
COUCHDB_ADMIN = os.getenv("COUCHDB_ADMIN", "admin")

print("✅ Auth router loaded")
router = APIRouter(prefix="/auth", tags=["Auth"])


# ----------------- Signup -----------------
@router.post("/signup")
async def signup(user: UserSignup):
    result = await create_user(user)
    return JSONResponse(status_code=201, content=result)


# ----------------- Login -----------------
@router.post("/login")
async def login_proxy(request: Request):
    body = await request.json()
    email = body.get("email")
    password = body.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    # 🔑 Use email as CouchDB username if you stored it that way
    username = email

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{COUCHDB_URL}/_session",
            data={"name": username, "password": password},   # safer encoding
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

    if response.status_code == 200:
        response_data = response.json()
        if not response_data.get("ok") or not response_data.get("name"):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        logged_in_user = response_data["name"]

        # Extract AuthSession from Set-Cookie header
        set_cookie_header = response.headers.get("set-cookie")
        if not set_cookie_header:
            raise HTTPException(status_code=500, detail="Authentication failed - no session cookie received")

        cookie = SimpleCookie()
        cookie.load(set_cookie_header)
        if "AuthSession" not in cookie:
            raise HTTPException(status_code=500, detail="Failed to extract AuthSession cookie")

        auth_session_value = cookie["AuthSession"].value

        # Return FastAPI response with cookie set
        fastapi_response = JSONResponse(content={
            "ok": True,
            "message": "Login successful",
            "name": logged_in_user
        })
        fastapi_response.set_cookie(
            key="AuthSession",
            value=auth_session_value,
            httponly=True,
            samesite="Strict",
            secure=False,   # change to True if HTTPS enforced
            max_age=86400,
            path="/"
        )
        return fastapi_response

    # ---- Login failed ----
    try:
        error_data = response.json()
        error_message = error_data.get("reason", "Login failed")
    except Exception:
        error_message = response.text or "Login failed"
    print(f"❌ CouchDB login failed: {response.status_code} {error_message}")
    raise HTTPException(status_code=401, detail=error_message)


# ----------------- Get Account -----------------
@router.get("/account")
async def get_account(request: Request):
    cookie_value = request.cookies.get("AuthSession")
    if not cookie_value:
        raise HTTPException(status_code=401, detail="Missing AuthSession cookie")

    session_info = await get_session_info(cookie_value)
    if not session_info or not session_info.get("name"):
        raise HTTPException(status_code=401, detail="Invalid session or cookie")

    return {"email": session_info["name"]}


# ----------------- Change Password -----------------
@router.post("/account/change-password")
async def change_password_api(request: Request):
    cookie_value = request.cookies.get("AuthSession")
    if not cookie_value:
        raise HTTPException(status_code=401, detail="Missing authentication cookie")

    session_info = await get_session_info(cookie_value)
    if not session_info or not session_info.get("name"):
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    username = session_info["name"]
    body = await request.json()
    new_password = body.get("new_password")
    current_password = body.get("current_password")

    if not new_password:
        raise HTTPException(status_code=400, detail="New password is required")

    try:
        await change_password(username, new_password, current_password)

        response = JSONResponse(content={
            "message": "Password updated successfully. Please log in again.",
            "success": True
        })
        # Clear cookie after password change
        response.delete_cookie("AuthSession", path="/")
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Password change error: {e}")
        raise HTTPException(status_code=500, detail="Failed to change password")


# ----------------- Logout -----------------
@router.post("/logout")
async def logout(request: Request):
    session_cookie = request.cookies.get("AuthSession")
    if session_cookie:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{COUCHDB_URL}/_session",
                headers={"Cookie": f"AuthSession={session_cookie}"}
            )

    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("AuthSession", path="/")
    return response


# ----------------- Debug Endpoints -----------------
@router.get("/ping")
async def ping():
    return {"msg": "pong"}

@router.get("/debug/cookie")
async def debug_cookie(request: Request):
    return {"cookies": dict(request.cookies)}
