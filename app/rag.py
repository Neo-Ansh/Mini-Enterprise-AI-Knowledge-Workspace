import io
import re
import hashlib                      # ← Phase 6: for cache key hashing
import google.generativeai as genai

from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings

from app.config import GEMINI_API_KEY


class PDFRAG:
    """Single document RAG — used for /chat route."""

    def __init__(self, file_bytes: bytes):

        if not GEMINI_API_KEY:
            raise ValueError("Missing GEMINI_API_KEY")

        genai.configure(api_key=GEMINI_API_KEY)

        self.text = self.extract_text(file_bytes)

        if not self.text.strip():
            raise ValueError(
                "PDF contains no extractable text. "
                "Scanned/image PDFs are not supported."
            )

        self.chunks = self.create_chunks(self.text)
        self.vectorstore = self.create_vectorstore(self.chunks)
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

        # ── Phase 6: in-memory cache per session ──────────────────────
        # key: md5 hash of question
        # value: full result dict {answer, sources}
        self._cache: dict = {}

    def extract_text(self, file_bytes: bytes) -> str:
        pdf_reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def create_chunks(self, text: str) -> list:
        splitter = CharacterTextSplitter(
            separator="\n",
            chunk_size=1000,
            chunk_overlap=200
        )
        return splitter.split_text(text)

    def create_vectorstore(self, chunks: list):
        embeddings = FakeEmbeddings(size=1352)
        return FAISS.from_texts(chunks, embeddings)

    def keyword_search(self, question: str, k: int = 4) -> list:
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "what", "which", "who", "how", "when", "where", "why", "that",
            "this", "these", "those", "it", "its", "and", "or", "but", "not"
        }
        words = re.findall(r'\b\w+\b', question.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        if not keywords:
            return []

        scored_chunks = []
        for chunk in self.chunks:
            chunk_lower = chunk.lower()
            score = sum(1 for kw in keywords if kw in chunk_lower)
            if score > 0:
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored_chunks[:k]]

    def query(self, question: str) -> dict:

        # ── Phase 6: check cache first ────────────────────────────────
        cache_key = hashlib.md5(question.strip().lower().encode()).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return {
                "answer": cached["answer"],
                "sources": cached["sources"],
                "cached": True          # tells frontend this was a cache hit
            }

        # ── Semantic search via FAISS ─────────────────────────────────
        semantic_docs = self.vectorstore.similarity_search(question, k=4)
        semantic_texts = [doc.page_content for doc in semantic_docs]

        keyword_texts = self.keyword_search(question, k=4)

        seen = set()
        merged = []
        for text in semantic_texts + keyword_texts:
            key = text[:100]
            if key not in seen:
                seen.add(key)
                merged.append(text)

        merged = merged[:6]
        context = "\n\n".join(merged)

        prompt = f"""
Answer the question based only on the context below.

Context:
{context}

Question:
{question}
"""
        response = self.model.generate_content(prompt)

        sources = [
            {
                "chunk_index": i + 1,
                "text": chunk[:200]
            }
            for i, chunk in enumerate(merged)
        ]

        result = {
            "answer": response.text,
            "sources": sources,
            "cached": False
        }

        # ── Phase 6: store in cache ───────────────────────────────────
        self._cache[cache_key] = result

        return result


# ── Phase 5.5-C: Multi-document workspace RAG ─────────────────────────

class WorkspaceRAG:
    """
    Multi-document RAG — used for /chat/workspace route.
    Takes multiple PDFs from a workspace and builds one
    combined vectorstore across all of them.
    Sources include which document each chunk came from.
    """

    def __init__(self, documents: list):
        """
        documents: list of dicts
        [
            {
                "session_id": "...",
                "pdf_name": "hr_policy.pdf",
                "file_bytes": b"..."
            },
            ...
        ]
        """
        if not GEMINI_API_KEY:
            raise ValueError("Missing GEMINI_API_KEY")

        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

        self.tracked_chunks = []

        splitter = CharacterTextSplitter(
            separator="\n",
            chunk_size=1000,
            chunk_overlap=200
        )
        embeddings = FakeEmbeddings(size=1352)

        all_texts = []

        for doc in documents:
            try:
                text = self._extract_text(doc["file_bytes"])
                if not text.strip():
                    continue
                chunks = splitter.split_text(text)
                for chunk in chunks:
                    self.tracked_chunks.append({
                        "text": chunk,
                        "pdf_name": doc["pdf_name"],
                        "session_id": doc["session_id"]
                    })
                    all_texts.append(chunk)
            except Exception:
                continue

        if not all_texts:
            raise ValueError("No readable documents found in this workspace.")

        self.vectorstore = FAISS.from_texts(all_texts, embeddings)

        # ── Phase 6: in-memory cache per workspace query ──────────────
        self._cache: dict = {}

    def _extract_text(self, file_bytes: bytes) -> str:
        pdf_reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def _keyword_search(self, question: str, k: int = 4) -> list:
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "what", "which", "who", "how", "when", "where", "why", "that",
            "this", "these", "those", "it", "its", "and", "or", "but", "not"
        }
        words = re.findall(r'\b\w+\b', question.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        if not keywords:
            return []

        scored = []
        for tracked in self.tracked_chunks:
            chunk_lower = tracked["text"].lower()
            score = sum(1 for kw in keywords if kw in chunk_lower)
            if score > 0:
                scored.append((score, tracked))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:k]]

    def query(self, question: str) -> dict:

        # ── Phase 6: check cache first ────────────────────────────────
        cache_key = hashlib.md5(question.strip().lower().encode()).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return {
                "answer": cached["answer"],
                "sources": cached["sources"],
                "cached": True
            }

        # ── Semantic search ───────────────────────────────────────────
        semantic_docs = self.vectorstore.similarity_search(question, k=4)
        semantic_texts = [doc.page_content for doc in semantic_docs]

        semantic_tracked = []
        for text in semantic_texts:
            for tracked in self.tracked_chunks:
                if tracked["text"] == text:
                    semantic_tracked.append(tracked)
                    break

        keyword_tracked = self._keyword_search(question, k=4)

        seen = set()
        merged = []
        for tracked in semantic_tracked + keyword_tracked:
            key = tracked["text"][:100]
            if key not in seen:
                seen.add(key)
                merged.append(tracked)

        merged = merged[:6]

        context = "\n\n".join([t["text"] for t in merged])

        prompt = f"""
You are an AI assistant for a company knowledge workspace.
Answer the question based only on the context below.
The context comes from multiple company documents.

Context:
{context}

Question:
{question}
"""
        response = self.model.generate_content(prompt)

        sources = [
            {
                "chunk_index": i + 1,
                "pdf_name": tracked["pdf_name"],
                "session_id": tracked["session_id"],
                "text": tracked["text"][:200]
            }
            for i, tracked in enumerate(merged)
        ]

        result = {
            "answer": response.text,
            "sources": sources,
            "cached": False
        }

        # ── Phase 6: store in cache ───────────────────────────────────
        self._cache[cache_key] = result

        return result