# Mini Enterprise AI Knowledge Workspace

A private, workspace-scoped RAG system for teams. Users upload documents into isolated workspaces and query them with an LLM. Access is controlled by role, so users only ever search documents in workspaces they belong to.

## Features

- JWT authentication with bcrypt password hashing and an admin-approval flow for new signups
- Role-based access control, with global roles (admin/user) and per-workspace roles (member/viewer)
- Isolated workspaces, so documents uploaded to a workspace are only searchable by its members
- Hybrid retrieval combining FAISS vector similarity search with keyword scoring
- Multi-document RAG, so a single workspace query searches across every document in that workspace at once, with source attribution per chunk
- In-memory response caching per session to skip redundant LLM calls on repeated questions
- MongoDB persistence for users, workspaces, document metadata, raw PDF bytes, and chat history
- Structured JSON logging with per-request IDs and timing

## Tech Stack

Backend: FastAPI, Motor (async MongoDB driver)

Auth: python-jose (JWT), passlib with bcrypt

RAG: LangChain, FAISS, PyPDF2

LLM: Google Gemini 2.5 Flash

Database: MongoDB

Frontend: Vanilla HTML, CSS, and JavaScript

## How It Works

A user registers and waits for admin approval, then logs in and receives a JWT used to authenticate every request. Documents are uploaded into a workspace, where they're text-extracted, split into chunks, embedded, and indexed in FAISS. When a user asks a question, the system checks a per-session cache, then runs FAISS similarity search and keyword search in parallel, merges and deduplicates the results, and passes them to Gemini 2.5 Flash as context for the final answer. Source chunks are returned alongside the answer.

## Setup

Prerequisites: Python 3.11+, MongoDB (local or Atlas), and a Gemini API key.

Clone the repository and install dependencies:

git clone https://github.com/Neo-Ansh/Mini-Enterprise-AI-Knowledge-Workspace.git
cd Mini-Enterprise-AI-Knowledge-Workspace
pip install -r requirements.txt

Create a .env file in the project root with the following variables:

GEMINI_API_KEY=your_gemini_api_key
MONGO_CONNECTION_STR=your_mongodb_connection_string
JWT_SECRET=some_long_random_string

Run the app:

uvicorn main:app --reload

Then open http://localhost:8000 in your browser.

## Project Structure

app/auth.py handles JWT creation and verification, password hashing, and auth dependencies.

app/config.py loads and validates environment variables.

app/db.py contains all MongoDB operations for users, workspaces, documents, and chat history.

app/logger.py sets up structured JSON logging.

app/models.py defines Pydantic request and response schemas.

app/rag.py contains the PDFRAG class for single-document retrieval and the WorkspaceRAG class for multi-document retrieval and generation.

app/routes.py defines the API endpoints.

frontend/ contains the vanilla HTML, CSS, and JS client.

main.py is the FastAPI app entry point, handling middleware and static file serving.

