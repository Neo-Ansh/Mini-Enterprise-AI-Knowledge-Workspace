import io
import google.generativeai as genai

from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings

from app.config import GEMINI_API_KEY


class PDFRAG:
    def __init__(self, file_bytes: bytes):

        if not GEMINI_API_KEY:
            raise ValueError("Missing GEMINI_API_KEY")

        genai.configure(api_key=GEMINI_API_KEY)

        self.text = self.extract_text(file_bytes)

        if not self.text.strip():
            raise ValueError(
                "PDF contains no extractable text. "
                "Scanned/image PDFs are  not supported."
            )

        self.vectorstore = self.create_vectorstore(self.text)

        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def extract_text(self, file_bytes: bytes) -> str:

        pdf_reader = PdfReader(io.BytesIO(file_bytes))

        text = ""

        for page in pdf_reader.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        return text

    def create_vectorstore(self, text: str):

        splitter = CharacterTextSplitter(
            separator="\n",
            chunk_size=1000,
            chunk_overlap=200
        )

        texts = splitter.split_text(text)

        # temporary local embeddings
        embeddings = FakeEmbeddings(size=1352)

        return FAISS.from_texts(texts, embeddings)

    def query(self, question: str) -> str:

        docs = self.vectorstore.similarity_search(
            question,
            k=4
        )

        context = "\n\n".join(
            [doc.page_content for doc in docs]
        )

        prompt = f"""
Answer the question based only on the context below.

Context:
{context}

Question:
{question}
"""

        response = self.model.generate_content(prompt)

        return response.text