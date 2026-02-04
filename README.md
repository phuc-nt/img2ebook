# Google Drive Image to Ebook/OCR Tool

A modern web application to convert Google Drive image folders into PDF Ebooks or clean text via Gemini-powered OCR.

## Features
- **Google Drive Integration**: Connect your drive and select image folders.
- **PDF Ebook**: Batch convert images into a single sorted PDF.
- **Smart OCR (Gemini 3 Flash)**: High-fidelity text extraction with cross-page word merging.
- **Parallel Processing**: Scalable batching (up to 100 concurrent threads for Paid Tier).
- **Modern UI**: Dark-mode glassmorphism interface built with React & Tailwind CSS.

## Setup

### Backend (FastAPI)
1. `cd backend`
2. `python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. Place your `client_secret.json` from Google Cloud Console in the `backend/` folder.
5. `uvicorn main:app --reload`

### Frontend (React)
1. `cd frontend`
2. `npm install`
3. `npm run dev`

## Usage
1. Paste your Google Drive folder link.
2. Select **PDF** or **Smart OCR**.
3. For OCR, provide your **Gemini API Key**.
4. Click convert and download the result.
