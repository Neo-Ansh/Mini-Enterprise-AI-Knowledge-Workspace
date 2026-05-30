# PDF RAG Chatbot System
for mongo atlas setup id used is "anshnew123321@gmail.com"


A simple web app that allows you to chat with your PDF documents using Retrieval Augmented Generation (RAG) technology. Upload any PDF and ask questions about its content to receive accurate, context-aware answers.

<img src="https://github.com/user-attachments/assets/73e4a4ed-c8af-47b9-9d0b-6cf378b3a832" alt="RAG Reader Preview" width="650">

## 🚀 Features

- **PDF Processing**: Upload and process PDF documents of any size
- **Natural Language Queries**: Ask questions in plain English about your document
- **Contextual Answers**: Get answers based on the content of your PDF
- **Interactive UI**: Clean, responsive user interface for direct interaction
- **Session Management**: Multiple document sessions with persistent storage
- **MongoDB Integration**: Store sessions for persistence across server restarts

## 🛠 Setup Instructions

### Prerequisites

- Anaconda or Miniconda
- Python 11
- OpenAI API key
- MongoDB (local installation or cloud)

### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/andreas-pattichis/PDF-RAG-Chatbot-System.git
cd PDF-RAG-Chatbot-System
```

2. **Create and activate a conda environment with Python 11**
```bash
conda create -n pdf-rag-env python=3.11
conda activate pdf-rag-env
```

3. **Install the required packages**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
Create a `.env` file in the root directory:
```
OPENAI_API_KEY=your_openai_api_key
MONGO_CONNECTION_STR=mongodb://localhost:27017
```

5. **Run the application**
```bash
uvicorn main:app --reload
```

6. **Access the application**: Open your browser and navigate to `http://localhost:8000`

## 📖 Usage Guide

1. Open the application in your browser
2. Drag and drop a PDF file into the upload area or click to browse
3. Click the "Upload PDF" button
4. Wait for processing to complete (larger PDFs take longer)
5. Type your question in the text box at the bottom
6. Press Enter or click the send button
7. Continue asking questions as needed

## 🧠 How RAG Works

Retrieval Augmented Generation (RAG) combines information retrieval with text generation for more accurate, contextual responses.

<img src="https://github.com/user-attachments/assets/c50d595b-febe-4797-8a65-36f97f97e244" alt="RAG Process Flow" width="650">

### RAG Process Flow:

1. **Document Processing Phase**:
   - PDF Document → Text Extraction → Chunk & Process Text → Create Embeddings → Store in Vector DB

2. **Query Processing Phase**:
   - User Question → Query Embedding → Retrieve Similar Chunks → Context Augmentation → Answer Generation

## 🏗 System Architecture

1. **Frontend**: HTML/CSS/JS interface for user interaction
2. **FastAPI Backend**: Handles HTTP requests and coordinates the RAG workflow
3. **RAG Engine**: Processes PDFs, creates embeddings, and generates answers
4. **Vector Database**: Stores document embeddings for efficient semantic retrieval
5. **LLM Integration**: Connects with OpenAI API for natural language responses
6. **MongoDB**: Stores PDF sessions persistently

## 🗄️ MongoDB Setup

### Local MongoDB Setup
1. Install MongoDB Community Edition from [MongoDB Download Center](https://www.mongodb.com/try/download/community)
2. Use connection string: `mongodb://localhost:27017` in your `.env` file
3. Install MongoDB Compass (optional) for visual database inspection

### MongoDB Atlas (Cloud) Alternative
1. Create an account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)
2. Create a cluster, set up network access, and create a database user
3. Add your connection string to the `.env` file

## 📁 Project Structure

```
PDF-RAG-Chatbot-System/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration and environment variables
│   ├── db.py              # MongoDB integration
│   ├── rag.py             # RAG implementation
│   └── routes.py          # API endpoints
├── frontend/
│   ├── index.html         # Main HTML file
│   ├── script.js          # Frontend JavaScript
│   └── style.css          # CSS styles
├── .env                   # Environment variables (create this)
├── main.py                # Application entry point
└── requirements.txt       # Python dependencies
```

## 🔍 Key Components

### Backend Components

- **PDFRAG Class**: Handles text extraction, chunking, embeddings creation, and answer generation
- **MongoDB Integration**: Manages persistent storage of PDF sessions
- **API Routes**: Handles HTTP requests for uploads, chat, and session management

### Frontend Components

- Clean, responsive UI with drag-and-drop PDF upload and interactive chat interface
- JavaScript for AJAX requests, PDF handling, and UI state management

## 🛡 Technologies Used

- **Backend**: FastAPI, LangChain, OpenAI API, PyPDF2, FAISS, MongoDB
- **Frontend**: HTML5/CSS3, JavaScript, Fetch API

## 📄 License

This project is licensed under the MIT License.

---

Created with ❤️ by Andreas Pattichis
