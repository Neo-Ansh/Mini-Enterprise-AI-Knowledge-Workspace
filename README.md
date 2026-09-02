Mini Enterprise AI Knowledge Workspace

A private, workspace-scoped RAG system — think "internal ChatGPT" for a company's documents. Teams get isolated workspaces, upload documents into them, and query the contents with an LLM. Access is controlled by role (admin / member / viewer), so users only ever search documents in workspaces they belong to.

Features
JWT authentication with bcrypt password hashing and an admin-approval flow for new signups
Role-based access control — global roles (admin/user) and per-workspace roles (member/viewer)
Isolated workspaces — documents uploaded to a workspace are only searchable by its members
Hybrid retrieval — combines FAISS vector similarity search with keyword scoring, merged and deduplicated before generation
Multi-document RAG — a single workspace query searches across every document in that workspace at once, with per-chunk source attribution
In-memory response caching per session to skip redundant LLM calls on repeated questions
MongoDB persistence for users, workspaces, document metadata, raw PDF bytes, and chat history
Structured JSON logging with per-request IDs and timing
Tech Stack
Layer	Technology
Backend	FastAPI, Motor (async MongoDB driver)
Auth	python-jose (JWT), passlib + bcrypt
RAG	LangChain, FAISS, PyPDF2
LLM	Google Gemini 2.5 Flash
Database	MongoDB
Frontend	Vanilla HTML/CSS/JavaScript
Architecture
Client (vanilla JS)
      │
      ▼
FastAPI (main.py) ── request logging middleware
      │
      ├── /api/auth/*         → register, login, JWT issuance
      ├── /api/admin/*        → user approval, roles, workspace membership
      ├── /api/upload         → PDF ingestion → chunk → embed → FAISS index
      ├── /api/chat           → single-document query
      └── /api/chat/workspace → multi-document query across a workspace
      │
      ▼
MongoDB — users, workspaces, document metadata, raw PDF bytes, chat history

Query flow: a question is checked against a per-session cache, then run through FAISS similarity search and keyword scoring in parallel; the results are merged, deduped, and passed to Gemini 2.5 Flash as context for the final answer, with source chunks returned alongside it.

Setup

Prerequisites: Python 3.11+, MongoDB (local or Atlas), a Gemini API key.

bash
git clone https://github.com/Neo-Ansh/Mini-Enterprise-AI-Knowledge-Workspace.git
cd Mini-Enterprise-AI-Knowledge-Workspace
pip install -r requirements.txt

Create a .env file in the project root:

GEMINI_API_KEY=your_gemini_api_key
MONGO_CONNECTION_STR=your_mongodb_connection_string
JWT_SECRET=some_long_random_string

Run it:

bash
uvicorn main:app --reload

Then open http://localhost:8000.

Project Structure
app/
├── auth.py       # JWT creation/verification, password hashing, auth dependencies
├── config.py     # environment variable loading and validation
├── db.py         # all MongoDB operations (users, workspaces, documents, chat history)
├── logger.py     # structured JSON logging setup
├── models.py     # Pydantic request/response schemas
├── rag.py        # PDFRAG (single-doc) and WorkspaceRAG (multi-doc) retrieval + generation
└── routes.py     # API endpoints
frontend/         # vanilla HTML/CSS/JS client
main.py           # FastAPI app, middleware, static file serving
