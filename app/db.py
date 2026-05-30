# app/db.py
import certifi
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from bson.binary import Binary
from bson import ObjectId

from app.config import MONGO_CONNECTION_STR
from app.logger import get_logger

logger = get_logger("db")


class MongoDB:
    def __init__(self):
        self.use_in_memory = False
        self.in_memory_storage = {}
        self.in_memory_chat_history = {}
        self.client = None
        self.db = None
        self.sessions = None
        self.workspaces = None
        self.users = None
        self.documents = None
        self.chat_history = None
        self.workspace_members = None          # ← Phase 5.5-B

        try:
            self.client = AsyncIOMotorClient(
                MONGO_CONNECTION_STR,
                serverSelectionTimeoutMS=5000,
                tls=True,
                tlsCAFile=certifi.where(),
                tlsAllowInvalidCertificates=False
            )

            self.db = self.client["pdf_rag_db"]

            self.sessions = self.db["sessions"]
            self.workspaces = self.db["workspaces"]
            self.users = self.db["users"]
            self.documents = self.db["documents"]
            self.chat_history = self.db["chat_history"]
            self.workspace_members = self.db["workspace_members"]  # ← Phase 5.5-B

            logger.info(
                "mongodb_client_initialized",
                extra={"database": "pdf_rag_db"}
            )

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(
                "mongodb_connection_failed",
                extra={"error": str(e)}
            )
            self.use_in_memory = True

        except Exception as e:
            logger.error(
                "unexpected_mongodb_error",
                extra={"error": str(e)}
            )
            self.use_in_memory = True

    # ── Core ──────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        if self.use_in_memory or self.client is None:
            return False
        try:
            await self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.error("mongodb_ping_failed", extra={"error": str(e)})
            return False

    # ── Session methods ───────────────────────────────────────────────

    async def store_session(self, session_id: str, pdf_bytes: bytes) -> bool:
        if self.use_in_memory:
            self.in_memory_storage[session_id] = pdf_bytes
            logger.info("session_stored_memory", extra={"session_id": session_id})
            return True
        try:
            session_doc = {
                "session_id": session_id,
                "pdf_bytes": Binary(pdf_bytes)
            }
            existing = await self.sessions.find_one({"session_id": session_id})
            if existing:
                await self.sessions.replace_one({"session_id": session_id}, session_doc)
            else:
                await self.sessions.insert_one(session_doc)
            logger.info("session_stored_mongodb", extra={"session_id": session_id})
            return True
        except Exception as e:
            logger.error("mongodb_store_failed", extra={"session_id": session_id, "error": str(e)})
            self.in_memory_storage[session_id] = pdf_bytes
            logger.warning("fallback_memory_storage_used", extra={"session_id": session_id})
            return True

    async def load_session(self, session_id: str):
        if self.use_in_memory:
            pdf_bytes = self.in_memory_storage.get(session_id)
            if pdf_bytes is None:
                logger.warning("session_not_found_memory", extra={"session_id": session_id})
            return pdf_bytes
        try:
            session = await self.sessions.find_one({"session_id": session_id})
            if not session:
                logger.warning("session_not_found_mongodb", extra={"session_id": session_id})
                return None
            logger.info("session_loaded_mongodb", extra={"session_id": session_id})
            return bytes(session["pdf_bytes"])
        except Exception as e:
            logger.error("mongodb_load_failed", extra={"session_id": session_id, "error": str(e)})
            return self.in_memory_storage.get(session_id)

    async def session_exists(self, session_id: str) -> bool:
        if self.use_in_memory:
            return session_id in self.in_memory_storage
        try:
            count = await self.sessions.count_documents({"session_id": session_id})
            return count > 0
        except Exception as e:
            logger.error("session_exists_check_failed", extra={"session_id": session_id, "error": str(e)})
            return session_id in self.in_memory_storage

    async def delete_session(self, session_id: str) -> bool:
        self.in_memory_storage.pop(session_id, None)
        if self.use_in_memory:
            logger.info("session_deleted_memory", extra={"session_id": session_id})
            return True
        try:
            result = await self.sessions.delete_one({"session_id": session_id})
            if result.deleted_count > 0:
                logger.info("session_deleted_mongodb", extra={"session_id": session_id})
                return True
            logger.warning("session_delete_not_found", extra={"session_id": session_id})
            return False
        except Exception as e:
            logger.error("mongodb_delete_failed", extra={"session_id": session_id, "error": str(e)})
            return False

    async def list_sessions(self) -> list:
        if self.use_in_memory:
            return list(self.in_memory_storage.keys())
        try:
            cursor = self.sessions.find({}, {"session_id": 1, "_id": 0})
            return [doc["session_id"] async for doc in cursor]
        except Exception as e:
            logger.error("list_sessions_failed", extra={"error": str(e)})
            return list(self.in_memory_storage.keys())

    # ── User methods ──────────────────────────────────────────────────

    async def create_user(
        self,
        name: str,
        email: str,
        hashed_password: str,
        role: str = "member",
        status: str = "pending"
    ) -> dict:
        doc = {
            "name": name,
            "email": email,
            "hashed_password": hashed_password,
            "role": role,
            "status": status,
            "created_at": datetime.utcnow()
        }
        result = await self.users.insert_one(doc)
        user_id = str(result.inserted_id)
        logger.info("user_created", extra={"user_id": user_id, "role": role, "status": status})
        return {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
            "status": status,
            "created_at": doc["created_at"]
        }

    async def get_user_by_email(self, email: str) -> dict | None:
        try:
            user = await self.users.find_one({"email": email})
            if not user:
                return None
            return {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "hashed_password": user["hashed_password"],
                "role": user["role"],
                "status": user.get("status", "approved"),
                "created_at": user["created_at"]
            }
        except Exception as e:
            logger.error("get_user_by_email_failed", extra={"error": str(e)})
            return None

    async def get_user_by_id(self, user_id: str) -> dict | None:
        try:
            user = await self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return None
            return {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
                "status": user.get("status", "approved"),
                "created_at": user["created_at"]
            }
        except Exception as e:
            logger.error("get_user_by_id_failed", extra={"error": str(e)})
            return None

    async def list_users(self) -> list:
        try:
            cursor = self.users.find({}, {"hashed_password": 0})
            users = []
            async for u in cursor:
                users.append({
                    "id": str(u["_id"]),
                    "name": u["name"],
                    "email": u["email"],
                    "role": u["role"],
                    "status": u.get("status", "approved"),
                    "created_at": u["created_at"]
                })
            return users
        except Exception as e:
            logger.error("list_users_failed", extra={"error": str(e)})
            return []

    async def user_count(self) -> int:
        try:
            return await self.users.count_documents({})
        except Exception:
            return 0

    # ── User approval methods ─────────────────────────────────────────

    async def get_pending_users(self) -> list:
        try:
            cursor = self.users.find(
                {"status": "pending"},
                {"hashed_password": 0}
            )
            users = []
            async for u in cursor:
                users.append({
                    "id": str(u["_id"]),
                    "name": u["name"],
                    "email": u["email"],
                    "role": u["role"],
                    "status": u.get("status", "pending"),
                    "created_at": u["created_at"]
                })
            return users
        except Exception as e:
            logger.error("get_pending_users_failed", extra={"error": str(e)})
            return []

    async def update_user_status(self, user_id: str, status: str) -> bool:
        try:
            result = await self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"status": status}}
            )
            if result.modified_count > 0:
                logger.info("user_status_updated", extra={"user_id": user_id, "status": status})
                return True
            logger.warning("user_status_update_not_found", extra={"user_id": user_id})
            return False
        except Exception as e:
            logger.error("update_user_status_failed", extra={"user_id": user_id, "error": str(e)})
            return False
    
    async def get_dashboard_stats(self) -> dict:
        """
        Returns counts for admin dashboard.
        total_users, pending_users, total_workspaces, total_documents
        """
        try:
            total_users = await self.users.count_documents({})
            pending_users = await self.users.count_documents({"status": "pending"})
            approved_users = await self.users.count_documents({"status": "approved"})
            rejected_users = await self.users.count_documents({"status": "rejected"})
            total_workspaces = await self.workspaces.count_documents({})
            total_documents = await self.documents.count_documents({})
            return {
                "total_users": total_users,
                "pending_users": pending_users,
                "approved_users": approved_users,
                "rejected_users": rejected_users,
                "total_workspaces": total_workspaces,
                "total_documents": total_documents
            }
        except Exception as e:
            logger.error("get_dashboard_stats_failed", extra={"error": str(e)})
            return {}

    async def update_user_role(self, user_id: str, role: str) -> bool:
        """
        Admin changes a user's system role.
        role must be 'admin', 'member', or 'viewer'
        """
        try:
            result = await self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"role": role}}
            )
            if result.modified_count > 0:
                logger.info(
                    "user_role_updated",
                    extra={"user_id": user_id, "role": role}
                )
                return True
            logger.warning(
                "user_role_update_not_found",
                extra={"user_id": user_id}
            )
            return False
        except Exception as e:
            logger.error(
                "update_user_role_failed",
                extra={"user_id": user_id, "error": str(e)}
            )
            return False

    async def delete_user(self, user_id: str) -> bool:
        """
        Permanently removes a user from the system.
        Also removes all their workspace memberships.
        """
        try:
            # Remove from workspace_members collection
            await self.workspace_members.delete_many({"user_id": user_id})

            # Remove user document
            result = await self.users.delete_one({"_id": ObjectId(user_id)})
            if result.deleted_count > 0:
                logger.info("user_deleted", extra={"user_id": user_id})
                return True
            logger.warning("user_delete_not_found", extra={"user_id": user_id})
            return False
        except Exception as e:
            logger.error(
                "delete_user_failed",
                extra={"user_id": user_id, "error": str(e)}
            )
            return False

    # ── Document metadata methods ─────────────────────────────────────

    async def store_document_meta(
        self,
        session_id: str,
        pdf_name: str,
        size_bytes: int,
        uploaded_by: str,
        uploaded_by_name: str,
        workspace_id: str = None
    ) -> dict:
        doc = {
            "session_id": session_id,
            "pdf_name": pdf_name,
            "size_bytes": size_bytes,
            "uploaded_by": uploaded_by,
            "uploaded_by_name": uploaded_by_name,
            "workspace_id": workspace_id,
            "created_at": datetime.utcnow()
        }
        await self.documents.insert_one(doc)
        logger.info("document_meta_stored", extra={"session_id": session_id})
        return {**doc, "id": str(doc.get("_id", ""))}

    async def list_documents(self, workspace_id: str = None) -> list:
        try:
            query = {}
            if workspace_id:
                query["workspace_id"] = workspace_id
            cursor = self.documents.find(query, {"_id": 0})
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error("list_documents_failed", extra={"error": str(e)})
            return []

    async def get_document_meta(self, session_id: str) -> dict | None:
        try:
            doc = await self.documents.find_one(
                {"session_id": session_id}, {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error("get_document_meta_failed", extra={"error": str(e)})
            return None

    async def delete_document_meta(self, session_id: str) -> bool:
        try:
            result = await self.documents.delete_one({"session_id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error("delete_document_meta_failed", extra={"error": str(e)})
            return False

    # ── Workspace methods ─────────────────────────────────────────────

    async def create_workspace(self, name: str, description: str = "") -> dict:
        if self.use_in_memory:
            raise Exception("Workspaces unavailable in memory fallback mode")
        doc = {
            "name": name,
            "description": description,
            "sessions": [],
            "created_at": datetime.utcnow()
        }
        result = await self.workspaces.insert_one(doc)
        workspace_id = str(result.inserted_id)
        logger.info("workspace_created", extra={"workspace_id": workspace_id, "workspace_name": name})
        return {
            "id": workspace_id,
            "name": name,
            "description": description,
            "sessions": [],
            "created_at": doc["created_at"]
        }

    async def list_workspaces(self) -> list:
        if self.use_in_memory:
            return []
        try:
            cursor = self.workspaces.find({})
            workspaces = []
            async for ws in cursor:
                workspaces.append({
                    "id": str(ws["_id"]),
                    "name": ws["name"],
                    "description": ws.get("description", ""),
                    "sessions": ws.get("sessions", []),
                    "created_at": ws.get("created_at")
                })
            return workspaces
        except Exception as e:
            logger.error("list_workspaces_failed", extra={"error": str(e)})
            return []

    async def add_session_to_workspace(self, workspace_id: str, session_id: str) -> bool:
        if self.use_in_memory:
            return False
        try:
            result = await self.workspaces.update_one(
                {"_id": ObjectId(workspace_id)},
                {"$addToSet": {"sessions": session_id}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error("add_session_to_workspace_failed", extra={
                "workspace_id": workspace_id, "session_id": session_id, "error": str(e)
            })
            return False

    async def delete_workspace(self, workspace_id: str) -> bool:
        if self.use_in_memory:
            return False
        try:
            result = await self.workspaces.delete_one({"_id": ObjectId(workspace_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error("delete_workspace_failed", extra={"workspace_id": workspace_id, "error": str(e)})
            return False

    async def get_workspace_sessions_with_meta(self, workspace_id: str) -> list:
        """
        Returns all documents in a workspace with session_id and pdf_name.
        Used by WorkspaceRAG to load all PDFs for multi-doc chat.
        """
        if self.use_in_memory:
            return []
        try:
            ws = await self.workspaces.find_one({"_id": ObjectId(workspace_id)})
            if not ws:
                return []

            session_ids = ws.get("sessions", [])
            if not session_ids:
                return []

            result = []
            for session_id in session_ids:
                meta = await self.documents.find_one(
                    {"session_id": session_id},
                    {"_id": 0, "session_id": 1, "pdf_name": 1}
                )
                if meta:
                    result.append({
                        "session_id": meta["session_id"],
                        "pdf_name": meta.get("pdf_name", "unknown.pdf")
                    })
            return result
        except Exception as e:
            logger.error("get_workspace_sessions_with_meta_failed", extra={
                "workspace_id": workspace_id,
                "error": str(e)
            })
            return []
            
        

    # ── Workspace membership methods ── Phase 5.5-B ───────────────────

    async def assign_member_to_workspace(
        self,
        workspace_id: str,
        user_id: str,
        workspace_role: str,
        added_by: str
    ) -> bool:
        if self.use_in_memory:
            return False
        try:
            # Check if already assigned — update role if so
            existing = await self.workspace_members.find_one({
                "workspace_id": workspace_id,
                "user_id": user_id
            })
            if existing:
                await self.workspace_members.update_one(
                    {"workspace_id": workspace_id, "user_id": user_id},
                    {"$set": {"workspace_role": workspace_role}}
                )
                logger.info("workspace_member_role_updated", extra={
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "workspace_role": workspace_role
                })
                return True

            doc = {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "workspace_role": workspace_role,
                "added_by": added_by,
                "added_at": datetime.utcnow()
            }
            await self.workspace_members.insert_one(doc)
            logger.info("workspace_member_assigned", extra={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "workspace_role": workspace_role
            })
            return True
        except Exception as e:
            logger.error("assign_member_failed", extra={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "error": str(e)
            })
            return False

    async def remove_member_from_workspace(
        self,
        workspace_id: str,
        user_id: str
    ) -> bool:
        if self.use_in_memory:
            return False
        try:
            result = await self.workspace_members.delete_one({
                "workspace_id": workspace_id,
                "user_id": user_id
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error("remove_member_failed", extra={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "error": str(e)
            })
            return False

    async def get_workspace_members(self, workspace_id: str) -> list:
        if self.use_in_memory:
            return []
        try:
            cursor = self.workspace_members.find(
                {"workspace_id": workspace_id},
                {"_id": 0}
            )
            members = []
            async for m in cursor:
                # Fetch user details for each member
                user = await self.get_user_by_id(m["user_id"])
                if user:
                    members.append({
                        "user_id": m["user_id"],
                        "name": user["name"],
                        "email": user["email"],
                        "workspace_role": m["workspace_role"],
                        "added_at": m["added_at"]
                    })
            return members
        except Exception as e:
            logger.error("get_workspace_members_failed", extra={
                "workspace_id": workspace_id,
                "error": str(e)
            })
            return []

    async def get_user_workspace_role(
        self,
        workspace_id: str,
        user_id: str
    ) -> str | None:
        # Returns workspace_role if user is member of workspace
        # Returns None if user has no access
        if self.use_in_memory:
            return None
        try:
            membership = await self.workspace_members.find_one({
                "workspace_id": workspace_id,
                "user_id": user_id
            })
            if membership:
                return membership["workspace_role"]
            return None
        except Exception as e:
            logger.error("get_user_workspace_role_failed", extra={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "error": str(e)
            })
            return None

    async def get_workspaces_for_user(self, user_id: str) -> list:
        # Returns all workspaces a user is assigned to
        if self.use_in_memory:
            return []
        try:
            cursor = self.workspace_members.find(
                {"user_id": user_id},
                {"_id": 0}
            )
            workspace_ids = []
            async for m in cursor:
                workspace_ids.append(m["workspace_id"])

            if not workspace_ids:
                return []

            # Fetch workspace details for each
            workspaces = []
            for wid in workspace_ids:
                try:
                    ws = await self.workspaces.find_one({"_id": ObjectId(wid)})
                    if ws:
                        # Get user role in this workspace
                        membership = await self.workspace_members.find_one({
                            "workspace_id": wid,
                            "user_id": user_id
                        })
                        workspaces.append({
                            "id": str(ws["_id"]),
                            "name": ws["name"],
                            "description": ws.get("description", ""),
                            "sessions": ws.get("sessions", []),
                            "workspace_role": membership["workspace_role"] if membership else "member",
                            "created_at": ws.get("created_at")
                        })
                except Exception:
                    continue
            return workspaces
        except Exception as e:
            logger.error("get_workspaces_for_user_failed", extra={
                "user_id": user_id,
                "error": str(e)
            })
            return []

    # ── Chat history methods ──────────────────────────────────────────

    async def save_chat_message(
        self,
        session_id: str,
        user_id: str,
        question: str,
        answer: str,
        sources: list = []
    ) -> bool:
        doc = {
            "session_id": session_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "sources": sources,
            "timestamp": datetime.utcnow()
        }
        if self.use_in_memory:
            if session_id not in self.in_memory_chat_history:
                self.in_memory_chat_history[session_id] = []
            self.in_memory_chat_history[session_id].append(doc)
            logger.info("chat_saved_memory", extra={"session_id": session_id})
            return True
        try:
            await self.chat_history.insert_one(doc)
            logger.info("chat_saved_mongodb", extra={"session_id": session_id})
            return True
        except Exception as e:
            logger.error("save_chat_failed", extra={"session_id": session_id, "error": str(e)})
            if session_id not in self.in_memory_chat_history:
                self.in_memory_chat_history[session_id] = []
            self.in_memory_chat_history[session_id].append(doc)
            return True

    async def get_chat_history(self, session_id: str) -> list:
        if self.use_in_memory:
            history = self.in_memory_chat_history.get(session_id, [])
            return [
                {
                    "question": h["question"],
                    "answer": h["answer"],
                    "sources": h.get("sources", []),
                    "timestamp": h["timestamp"].isoformat()
                }
                for h in history
            ]
        try:
            cursor = self.chat_history.find(
                {"session_id": session_id},
                {"_id": 0, "question": 1, "answer": 1, "sources": 1, "timestamp": 1}
            ).sort("timestamp", 1)
            history = []
            async for doc in cursor:
                history.append({
                    "question": doc["question"],
                    "answer": doc["answer"],
                    "sources": doc.get("sources", []),
                    "timestamp": doc["timestamp"].isoformat()
                })
            return history
        except Exception as e:
            logger.error("get_chat_history_failed", extra={"session_id": session_id, "error": str(e)})
            return []