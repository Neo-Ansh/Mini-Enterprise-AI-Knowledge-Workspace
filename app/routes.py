# app/routes.py
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional


from app.rag import PDFRAG, WorkspaceRAG    # ← Phase 5.5-C
from app.db import MongoDB
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin
)
from app.models import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
    RegisterResponse,
    AssignMemberRequest        # ← Phase 5.5-B
)
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

class WorkspaceChatRequest(BaseModel):
    workspace_id: str
    question: str

class UpdateRoleRequest(BaseModel):
    role: str    # "admin", "member", or "viewer"

# =====================================================================
# AUTH ROUTES
# =====================================================================

@router.post("/auth/register")
async def register(data: UserRegister, db: MongoDB = Depends(get_db)):
    existing = await db.get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    count = await db.user_count()

    if count == 0:
        role = "admin"
        status = "approved"
    else:
        role = "member"
        status = "pending"

    hashed = hash_password(data.password)
    user = await db.create_user(
        name=data.name,
        email=data.email,
        hashed_password=hashed,
        role=role,
        status=status
    )

    if role == "admin":
        token = create_access_token(
            user_id=user["id"],
            email=user["email"],
            role=user["role"]
        )
        logger.info("admin_registered", extra={"user_id": user["id"]})
        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user["id"],
                name=user["name"],
                email=user["email"],
                role=user["role"],
                status=user["status"],
                created_at=user["created_at"]
            )
        )

    logger.info("user_registered_pending", extra={"user_id": user["id"]})
    return RegisterResponse(
        message="Registration successful. Your request has been sent to the admin for approval.",
        name=user["name"],
        email=user["email"],
        status=user["status"]
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: MongoDB = Depends(get_db)):
    user = await db.get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if user["status"] == "pending":
        raise HTTPException(
            status_code=403,
            detail="Your account is pending admin approval. Please wait."
        )

    if user["status"] == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Your account request has been rejected. Contact admin."
        )

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
            status=user["status"],
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
# ADMIN ROUTES
# =====================================================================

@router.get("/admin/users/pending")
async def get_pending_users(
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    users = await db.get_pending_users()
    return {"pending_users": users}


@router.post("/admin/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    ok = await db.update_user_status(user_id, "approved")
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")
    logger.info("user_approved", extra={
        "user_id": user_id,
        "approved_by": current_user["id"]
    })
    return {"message": "User approved successfully."}


@router.post("/admin/users/{user_id}/reject")
async def reject_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    ok = await db.update_user_status(user_id, "rejected")
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")
    logger.info("user_rejected", extra={
        "user_id": user_id,
        "rejected_by": current_user["id"]
    })
    return {"message": "User rejected."}

@router.get("/admin/dashboard")
async def admin_dashboard(
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin dashboard — system wide stats.
    Returns user counts, workspace counts, document counts.
    """
    stats = await db.get_dashboard_stats()
    return {"dashboard": stats}


@router.get("/admin/users/all")
async def list_all_users(
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin sees all users with their role and status.
    Includes approved, pending, and rejected users.
    """
    users = await db.list_users()
    return {"users": users, "total": len(users)}


@router.put("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    data: UpdateRoleRequest,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin changes a user's system role.
    Allowed roles: admin, member, viewer
    """
    if data.role not in ["admin", "member", "viewer"]:
        raise HTTPException(
            status_code=400,
            detail="Role must be 'admin', 'member', or 'viewer'."
        )

    # Prevent admin from changing their own role
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role."
        )

    ok = await db.update_user_role(user_id, data.role)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")

    logger.info("user_role_changed", extra={
        "user_id": user_id,
        "new_role": data.role,
        "changed_by": current_user["id"]
    })
    return {"message": f"User role updated to {data.role}."}


@router.get("/admin/workspaces/all")
async def list_all_workspaces_admin(
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin sees all workspaces with member counts.
    """
    if db.use_in_memory:
        return {"workspaces": []}

    workspaces = await db.list_workspaces()

    # Add member count to each workspace
    result = []
    for ws in workspaces:
        members = await db.get_workspace_members(ws["id"])
        result.append({
            **ws,
            "member_count": len(members)
        })

    return {"workspaces": result, "total": len(result)}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin permanently deletes a user.
    Also removes all their workspace memberships.
    Cannot delete yourself.
    """
    # Prevent admin from deleting themselves
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account."
        )

    ok = await db.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")

    logger.info("user_deleted_by_admin", extra={
        "user_id": user_id,
        "deleted_by": current_user["id"]
    })
    return {"message": "User deleted successfully."}


# ── Phase 5.5-B: Workspace membership admin routes ────────────────────

@router.post("/admin/workspaces/{workspace_id}/members")
async def assign_member(
    workspace_id: str,
    data: AssignMemberRequest,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """
    Admin assigns a user to a workspace with a role.
    workspace_role must be 'member' or 'viewer'.
    member → can upload + chat
    viewer → can only chat
    """
    if data.workspace_role not in ["member", "viewer"]:
        raise HTTPException(
            status_code=400,
            detail="workspace_role must be 'member' or 'viewer'."
        )

    # Verify user exists and is approved
    user = await db.get_user_by_id(data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="Cannot assign a pending or rejected user to a workspace."
        )

    ok = await db.assign_member_to_workspace(
        workspace_id=workspace_id,
        user_id=data.user_id,
        workspace_role=data.workspace_role,
        added_by=current_user["id"]
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to assign member.")

    logger.info("member_assigned_to_workspace", extra={
        "workspace_id": workspace_id,
        "user_id": data.user_id,
        "workspace_role": data.workspace_role,
        "assigned_by": current_user["id"]
    })
    return {"message": f"User assigned to workspace as {data.workspace_role}."}


@router.delete("/admin/workspaces/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: str,
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """Admin removes a user from a workspace."""
    ok = await db.remove_member_from_workspace(workspace_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found in workspace.")
    logger.info("member_removed_from_workspace", extra={
        "workspace_id": workspace_id,
        "user_id": user_id,
        "removed_by": current_user["id"]
    })
    return {"message": "User removed from workspace."}


@router.get("/admin/workspaces/{workspace_id}/members")
async def get_workspace_members(
    workspace_id: str,
    current_user: dict = Depends(require_admin),
    db: MongoDB = Depends(get_db)
):
    """Admin lists all members of a workspace."""
    members = await db.get_workspace_members(workspace_id)
    return {"workspace_id": workspace_id, "members": members}


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

    # ── Phase 5.5-B: workspace permission check on upload ─────────────
    if workspace_id and current_user["role"] != "admin":
        workspace_role = await db.get_user_workspace_role(
            workspace_id=workspace_id,
            user_id=current_user["id"]
        )
        if workspace_role is None:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this workspace."
            )
        if workspace_role == "viewer":
            raise HTTPException(
                status_code=403,
                detail="Viewers cannot upload documents. Contact your admin."
            )

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
        result = pdf_rag.query(request.question)
        answer = result["answer"]
        sources = result["sources"]

        await db.save_chat_message(
            session_id=session_id,
            user_id=current_user["id"],
            question=request.question,
            answer=answer,
            sources=sources
        )

        logger.info("answer_generated", extra={
            "session_id": session_id,
            "user_id": current_user["id"]
        })
        return {
            "answer": answer,
            "sources": sources
        }

    except Exception as e:
        logger.error("query_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error during query: {str(e)}")


@router.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    history = await db.get_chat_history(session_id)
    return {"session_id": session_id, "history": history}


@router.post("/chat/workspace")
async def chat_with_workspace(
    request: WorkspaceChatRequest,
    current_user: dict = Depends(get_current_user),
    db: MongoDB = Depends(get_db)
):
    workspace_id = request.workspace_id

    if current_user["role"] != "admin":
        workspace_role = await db.get_user_workspace_role(
            workspace_id=workspace_id,
            user_id=current_user["id"]
        )
        if workspace_role is None:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this workspace."
            )

    sessions_meta = await db.get_workspace_sessions_with_meta(workspace_id)

    if not sessions_meta:
        raise HTTPException(
            status_code=404,
            detail="No documents found in this workspace. Upload PDFs first."
        )

    documents = []
    for meta in sessions_meta:
        pdf_bytes = await db.load_session(meta["session_id"])
        if pdf_bytes:
            documents.append({
                "session_id": meta["session_id"],
                "pdf_name": meta["pdf_name"],
                "file_bytes": pdf_bytes
            })

    if not documents:
        raise HTTPException(
            status_code=404,
            detail="Could not load documents from this workspace."
        )

    try:
        workspace_rag = WorkspaceRAG(documents)
        result = workspace_rag.query(request.question)
        answer = result["answer"]
        sources = result["sources"]

        await db.save_chat_message(
            session_id=f"workspace_{workspace_id}",
            user_id=current_user["id"],
            question=request.question,
            answer=answer,
            sources=sources
        )

        logger.info("workspace_answer_generated", extra={
            "workspace_id": workspace_id,
            "user_id": current_user["id"],
            "docs_used": len(documents)
        })

        return {
            "answer": answer,
            "sources": sources,
            "docs_searched": len(documents)
        }

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.error("workspace_chat_failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail=f"Error during workspace chat: {str(e)}"
        )


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
    current_user: dict = Depends(require_admin),   # ← only admin creates workspaces
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
    """
    Admin sees all workspaces.
    Members and viewers see only their assigned workspaces.
    """
    if db.use_in_memory:
        return {"workspaces": []}

    if current_user["role"] == "admin":
        workspaces = await db.list_workspaces()
    else:
        workspaces = await db.get_workspaces_for_user(current_user["id"])

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

    # ── Phase 5.5-B: only admin or workspace member can add sessions ──
    if current_user["role"] != "admin":
        workspace_role = await db.get_user_workspace_role(
            workspace_id=workspace_id,
            user_id=current_user["id"]
        )
        if workspace_role is None or workspace_role == "viewer":
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to add documents to this workspace."
            )

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