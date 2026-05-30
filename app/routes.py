# app/routes.py
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.rag import PDFRAG
from app.db import MongoDB
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin
)
from app.models import UserRegister, UserLogin, TokenResponse, UserResponse
from app.logger import get_logger

logger = get_logger("routes")
router = APIRouter()

# ── Singleton DB instance ─────────────────────────────────────────────
_db_instance: Optional[MongoDB] = None

async def init_db():
    global _db_instance
    _db_instance = MongoDB()
    reachable = await _db_instance.ping()
    if not reachable:
        logger.warning("MongoDB unreachable at startup — switching to in-memory fallback")
        _db_instance.use_in_memory = True

def get_db() -> MongoDB:
    if _db_instance is None:
        raise HTTPException(status_code=503, detail="Database not initialized yet.")
    return _db_instance

# ── In-memory PDFRAG cache ────────────────────────────────────────────
active_sessions: dict = {}

# ── Request models ────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    question: str

class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""

class AddSessionToWorkspace(BaseModel):
    session_id: str

# =====================================================================
# AUTH ROUTES
# =====================================================================

@router.post("/auth/register", response_model=TokenResponse)
async def register(data: UserRegister, db: MongoDB = Depends(get_db)):
    existing = await db.get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    count = await db.user_count()
    role = "admin" if count == 0 else "member"

    hashed = hash_password(data.password)
    user = await db.create_user(
        name=data.name,
        email=data.email,
        hashed_password=hashed,
        role=role
    )

    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"]
    )

    logger.info("user_registered", extra={"user_id": user["id"], "role": role})

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user["role"],
            created_at=user["created_at"]
        )
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: MongoDB = Depends(get_db)):
    user = await db.get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"]
    )

    logger.info("user_logged_in", extra={"user_id": user["id"]})

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user["role"],
            created_at=user["created_at"]
        )
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    user = await db.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse(**user)


@router.get("/auth/users")
async def list_users(
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    users = await db.list_users()
    return {"users": users}


# =====================================================================
# DOCUMENT ROUTES  (protected)
# =====================================================================

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    workspace_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")

    try:
        logger.info("PDF received", extra={
            "pdf_name": file.filename,
            "size_bytes": len(file_bytes),
            "user_id": current_user["id"]
        })

        pdf_rag = PDFRAG(file_bytes)
        session_id = str(uuid.uuid4())

        await db.store_session(session_id, file_bytes)

        user_full = await db.get_user_by_id(current_user["id"])
        await db.store_document_meta(
            session_id=session_id,
            pdf_name=file.filename,
            size_bytes=len(file_bytes),
            uploaded_by=current_user["id"],
            uploaded_by_name=user_full["name"] if user_full else current_user["email"],
            workspace_id=workspace_id
        )

        active_sessions[session_id] = pdf_rag

        if workspace_id:
            await db.add_session_to_workspace(workspace_id, session_id)

        logger.info("session_created", extra={"session_id": session_id})
        return {
            "session_id": session_id,
            "pdf_name": file.filename,
            "message": "PDF processed successfully."
        }

    except ValueError as e:
        logger.warning("PDF rejected", extra={"error": str(e)})
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.error("PDF upload failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@router.post("/chat")
async def chat_with_pdf(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    session_id = request.session_id
    pdf_rag = active_sessions.get(session_id)

    if pdf_rag is None:
        logger.info("session_not_in_memory", extra={"session_id": session_id})
        pdf_bytes = await db.load_session(session_id)
        if pdf_bytes is None:
            raise HTTPException(status_code=404, detail="Session not found. Please upload a PDF first.")
        try:
            pdf_rag = PDFRAG(pdf_bytes)
            active_sessions[session_id] = pdf_rag
        except Exception as e:
            logger.error("rebuild_pdfrag_failed", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Error loading session: {str(e)}")

    try:
        answer = pdf_rag.query(request.question)

        # ── Phase 3: save to chat history ─────────────────────────────
        await db.save_chat_message(
            session_id=session_id,
            user_id=current_user["id"],
            question=request.question,
            answer=answer
        )

        logger.info("answer_generated", extra={
            "session_id": session_id,
            "user_id": current_user["id"]
        })
        return {"answer": answer}

    except Exception as e:
        logger.error("query_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error during query: {str(e)}")


# ── Phase 3: get chat history for a session ───────────────────────────
@router.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    history = await db.get_chat_history(session_id)
    return {"session_id": session_id, "history": history}


@router.get("/documents")
async def list_documents(
    workspace_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    docs = await db.list_documents(workspace_id=workspace_id)
    return {"documents": docs}


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    try:
        session_ids = await db.list_sessions()
        return {"sessions": session_ids}
    except Exception as e:
        logger.error("list_sessions_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    active_sessions.pop(session_id, None)
    await db.delete_document_meta(session_id)
    deleted = await db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    logger.info("session_deleted", extra={"session_id": session_id, "user_id": current_user["id"]})
    return {"message": "Session deleted successfully."}


@router.get("/db-status")
async def db_status(db: MongoDB = Depends(get_db)):
    if db.use_in_memory:
        return {
            "status": "fallback",
            "message": "Using in-memory storage (MongoDB unavailable)",
            "active_sessions": len(db.in_memory_storage)
        }
    reachable = await db.ping()
    return {
        "status": "connected" if reachable else "error",
        "message": "MongoDB reachable" if reachable else "MongoDB ping failed",
        "active_sessions": len(active_sessions)
    }


# =====================================================================
# WORKSPACE ROUTES  (protected)
# =====================================================================

@router.post("/workspaces")
async def create_workspace(
    data: WorkspaceCreate,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    if db.use_in_memory:
        raise HTTPException(status_code=503, detail="Workspaces require MongoDB.")
    workspace = await db.create_workspace(data.name, data.description)
    logger.info("workspace_created", extra={
        "workspace_id": workspace["id"],
        "user_id": current_user["id"]
    })
    return workspace


@router.get("/workspaces")
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    if db.use_in_memory:
        return {"workspaces": []}
    workspaces = await db.list_workspaces()
    return {"workspaces": workspaces}


@router.post("/workspaces/{workspace_id}/sessions")
async def add_to_workspace(
    workspace_id: str,
    data: AddSessionToWorkspace,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    if db.use_in_memory:
        raise HTTPException(status_code=503, detail="Workspaces require MongoDB.")
    ok = await db.add_session_to_workspace(workspace_id, data.session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return {"message": "Session added to workspace."}


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    if db.use_in_memory:
        raise HTTPException(status_code=503, detail="Workspaces require MongoDB.")
    ok = await db.delete_workspace(workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    logger.info("workspace_deleted", extra={
        "workspace_id": workspace_id,
        "user_id": current_user["id"]
    })
    return {"message": "Workspace deleted."}