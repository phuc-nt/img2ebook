import os
import re
import json
import tempfile
import requests
from io import BytesIO
from typing import List
from typing import List
import asyncio 
from fastapi import FastAPI, Request, HTTPException, Body, BackgroundTasks
from fastapi.responses import RedirectResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.auth.transport.requests
from fpdf import FPDF
from PIL import Image
from services.gemini_service import GeminiOCR
import zipfile
import io
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed

# Allow insecure transport for local development (http instead of https)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Global executor to be managed by lifespan
process_executor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global process_executor
    # Increased workers to support parallel batch processing within tasks (Paid Tier: 100)
    process_executor = ThreadPoolExecutor(max_workers=100)
    yield
    # Shutdown
    print("Shutting down executor...")
    process_executor.shutdown(wait=False, cancel_futures=True)

app = FastAPI(lifespan=lifespan)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_SECRET_FILE = 'client_secret.json'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
REDIRECT_URI = 'http://localhost:8000/auth/callback'

# Global store for tokens
user_tokens = {}

def get_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

def get_drive_service():
    if 'default' not in user_tokens:
        return None
    
    token_info = user_tokens['default']
    credentials = Credentials(
        token=token_info['token'],
        refresh_token=token_info.get('refresh_token'),
        token_uri=token_info['token_uri'],
        client_id=token_info['client_id'],
        client_secret=token_info['client_secret'],
        scopes=token_info['scopes']
    )
    
    # Refresh token if expired
    if credentials.expired and credentials.refresh_token:
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        # Update our store
        token_info['token'] = credentials.token
    
    return build('drive', 'v3', credentials=credentials)

def extract_folder_id(url: str):
    # Matches /folders/ID or ?id=ID
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return url # Assume it's just the ID if no match

@app.get("/auth/login")
def login():
    flow = get_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='select_account'  # Forces Google to show account selector
    )
    return {"url": authorization_url}

@app.get("/auth/logout")
def logout():
    user_tokens.clear()
    return {"status": "logged_out"}

@app.get("/auth/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Code not found")
    
    flow = get_flow()
    flow.fetch_token(code=code)
    
    credentials = flow.credentials
    user_tokens['default'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return RedirectResponse(url="http://localhost:5173?status=success")

@app.get("/api/user")
def get_user():
    if 'default' not in user_tokens:
        return {"logged_in": False}
    return {"logged_in": True}

async def download_images_from_folder(service, folder_id, tmp_dir):
    """Refactored helper to list and download images."""
    logger.info(f"Listing files in folder: {folder_id}")
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
        pageSize=100,
        fields="files(id, name, mimeType)",
        orderBy="name"
    ).execute()
    files = results.get('files', [])
    
    logger.info(f"Found {len(files)} images in Drive folder.")
    if not files:
        return []

    downloaded_files = []
    total_files = len(files)
    
    for i, file_meta in enumerate(files):
        # Check cancellation
        if cancel_event.is_set():
            logger.warning("Download cancelled by user.")
            return None

        file_id = file_meta['id']
        file_ext = file_meta['mimeType'].split('/')[-1]
        tmp_path = os.path.join(tmp_dir, f"{file_id}.{file_ext}")
        
        logger.info(f"Downloading {i+1}/{total_files}: {file_meta['name']}")
        request = service.files().get_media(fileId=file_id)
        with open(tmp_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        # Track original name for sorting or reference if needed
        downloaded_files.append({"path": tmp_path, "name": file_meta['name']})
        
        # Update global progress (Approximation: 10% scanning + 70% downloading)
        percent = 10 + int((i / total_files) * 70)
        current_progress.update({
            "status": "processing",
            "percent": percent,
            "message": f"Downloading {i+1}/{total_files}: {file_meta['name']}"
        })
        
    logger.info(f"Download complete. {len(downloaded_files)} files saved to {tmp_dir}")
    return downloaded_files

import asyncio
from fastapi.responses import StreamingResponse

import threading

# Global progress and cancellation
current_progress = {"status": "idle", "percent": 0, "message": ""}
cancel_event = threading.Event()

@app.get("/api/progress")
async def progress_stream():
    async def event_generator():
        while True:
            if current_progress["status"] == "complete" or current_progress["status"] == "error" or current_progress["status"] == "cancelled":
                yield f"data: {json.dumps(current_progress)}\n\n"
                break
            yield f"data: {json.dumps(current_progress)}\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/cancel")
def cancel_process():
    if current_progress["status"] == "processing" or current_progress["status"] == "starting":
        cancel_event.set()
        current_progress.update({"status": "cancelled", "message": "Cancelling..."})
    return {"status": "ok"}

@app.post("/api/ocr/convert")
async def convert_ocr(payload: dict = Body(...)):
    url = payload.get("url")
    api_key = payload.get("api_key")
    
    if not url or not api_key:
        raise HTTPException(status_code=400, detail="URL and Gemini API Key are required")
        
    cancel_event.clear()
    current_progress.update({"status": "starting", "percent": 0, "message": "Initializing OCR..."})
    
    loop = asyncio.get_event_loop()
    # Use the global executor managed by lifespan
    return await loop.run_in_executor(process_executor, process_ocr_conversion, url, api_key)

def process_ocr_conversion(url, api_key):
    try:
        if cancel_event.is_set(): raise Exception("Cancelled")
        
        service = get_drive_service()
        if not service:
             current_progress.update({"status": "error", "message": "Auth failed"})
             return {"success": False, "error": "Not authenticated"}

        folder_id = extract_folder_id(url)
        current_progress.update({"status": "processing", "percent": 5, "message": "Scanning folder..."})
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Reusing the helper logic
            downloaded_files = asyncio.run(download_images_from_folder(service, folder_id, tmp_dir)) \
                if asyncio.iscoroutinefunction(download_images_from_folder) else download_images_from_folder(service, folder_id, tmp_dir)
            
            if downloaded_files is None: # Cancelled
                raise Exception("Cancelled by user")
            
            if not downloaded_files:
                return {"success": False, "error": "No images found"}

            # NATURAL SORT: Critical for seamless text!
            # We must ensure Page 1 -> Page 2 -> Page 10 (not 1 -> 10 -> 2)
            import re
            def natural_keys(item):
                text = item['name']
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            
            downloaded_files.sort(key=natural_keys)
            logger.info(f"Sorted {len(downloaded_files)} files naturally.")
            
            # Parallel Processing
            gemini = GeminiOCR(api_key) 
            full_text = ""
            
            # BATCHING STRATEGY: Maximize parallelism (up to 100 batches)
            # - For quality, each batch should have at least 1 image
            # - Prefer more batches (faster) over larger batches (better context)
            # - Max 100 concurrent batches (Paid Tier limit)
            total_files = len(downloaded_files)
            target_concurrency = min(100, total_files)  # Max 100 batches or 1 batch per file
            
            # Calculate roughly equal chunk sizes
            # k is base size, m is remainder to distribute
            k, m = divmod(total_files, target_concurrency)
            file_batches = []
            start_idx = 0
            for i in range(target_concurrency):
                # Distribute remainder one by one
                chunk_size = k + 1 if i < m else k
                end_idx = start_idx + chunk_size
                file_batches.append(downloaded_files[start_idx:end_idx])
                start_idx = end_idx
                
            total_batches = len(file_batches)
            logger.info(f"Dynamic Batching: Split {total_files} files into {total_batches} batches (Target 10). Work distribution: {[len(b) for b in file_batches]}")
            
            # Shared progress tracking
            completed_batches = 0
            lock = threading.Lock()
            results = [None] * total_batches

            def process_batch_wrapper(b_idx, batch_files):
                if cancel_event.is_set(): return None
                
                images_opened = []
                try:
                    for f in batch_files:
                        img = Image.open(f["path"])
                        images_opened.append(img)
                    
                    if not images_opened: return ""

                    # We won't use granular char streaming updates here to avoid lock contention
                    # Instead we update on completion
                    text = gemini.transcribe_batch(images_opened, cancel_callback=lambda: cancel_event.is_set())
                    return text
                except Exception as e:
                    logger.error(f"Batch {b_idx} failed: {e}")
                    raise e
                finally:
                    for img in images_opened: img.close()

            # Execute batches in parallel
            # Max workers = 100 (Paid Tier)
            with ThreadPoolExecutor(max_workers=100) as batch_executor:
                future_to_batch = {
                    batch_executor.submit(process_batch_wrapper, i, file_batches[i]): i 
                    for i in range(total_batches)
                }
                
                for future in as_completed(future_to_batch):
                    b_idx = future_to_batch[future]
                    try:
                        text_result = future.result()
                        if text_result is None: # Cancelled
                            raise Exception("Cancelled")
                        
                        results[b_idx] = text_result
                        
                        with lock:
                            completed_batches += 1
                            percent = 80 + int((completed_batches / total_batches) * 15)
                            current_progress.update({
                                "status": "processing",
                                "percent": percent,
                                "message": f"Analyzing... Completed Batch {completed_batches}/{total_batches}"
                            })
                            logger.info(f"Batch {b_idx+1}/{total_batches} completed.")
                            
                    except Exception as e:
                        if "Cancelled" in str(e):
                            raise Exception("Cancelled by user")
                        logger.error(f"Error in batch {b_idx}: {e}")

            # Assemble text in order
            for res in results:
                if res:
                    full_text += res + "\n"
            
            # Post-processing: Create timestamped folder with text files
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"results/ocr_{timestamp}"
            os.makedirs(output_dir, exist_ok=True)
            
            current_progress.update({"status": "processing", "percent": 99, "message": "Saving results..."})
            logger.info(f"Creating output directory: {output_dir}")
            
            # Split by chapter if detected, with deduplication
            if "<<<CHAPTER_START" in full_text:
                parts = full_text.split("<<<CHAPTER_START:")
                
                # Save intro if exists
                if parts[0].strip():
                    with open(os.path.join(output_dir, "00_Intro.txt"), 'w', encoding='utf-8') as f:
                        f.write(parts[0].strip())
                
                # Process chapters with deduplication
                chapters = {}  # {normalized_title: {"title": original, "content": text}}
                
                for part in parts[1:]:
                    if ">>>" in part:
                        title, content = part.split(">>>", 1)
                        title = title.strip()
                        content = content.strip()
                        
                        # Normalize for comparison (lowercase, no extra spaces)
                        normalized = title.lower().replace(" ", "")
                        
                        if normalized in chapters:
                            # Merge with existing chapter
                            chapters[normalized]["content"] += "\n\n" + content
                            logger.info(f"Merged duplicate chapter: {title}")
                        else:
                            # New chapter
                            chapters[normalized] = {"title": title, "content": content}
                
                # Write deduplicated chapters
                for i, (norm_title, data) in enumerate(chapters.items()):
                    safe_title = "".join([c for c in data["title"] if c.isalnum() or c in (' ', '_')]).strip()
                    filename = f"{i+1:02d}_{safe_title}.txt"
                    with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
                        f.write(data["content"])
                    logger.info(f"Created: {filename}")
            else:
                with open(os.path.join(output_dir, "full_text.txt"), 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logger.info("No chapters detected. Saved as full_text.txt")
            
            # For web download, create a ZIP of this folder
            output_zip = f"{output_dir}.zip"
            with zipfile.ZipFile(output_zip, 'w') as zf:
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, output_dir)
                        zf.write(file_path, arcname)
            
            logger.info(f"Results saved to folder: {output_dir}")
            logger.info(f"Download ZIP created: {output_zip}")
            
        current_progress.update({"status": "complete", "percent": 100, "message": "OCR Complete!"})
        return {"success": True, "download_url": "/api/download"} # We can reuse download endpoint if we overwrite output file or make endpoint dynamic
        
    except Exception as e:
        current_progress.update({"status": "error", "message": str(e)})
        return {"success": False, "error": str(e)}

@app.post("/api/convert")
async def convert_folder(payload: dict = Body(...), background_tasks: BackgroundTasks = None):
    # Note: For SSE to work well, conversion should ideally be a background task
    # For this simple synchronous flow, we will update the global variable
    # and use asyncio.to_thread in a real async app. 
    # Here we'll just update the variable synchronously which might block main thread
    # So we should refactor to run heavy lifting in a separate thread.
    
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=1)
    
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Reset state
    cancel_event.clear()
    current_progress.update({"status": "starting", "percent": 0, "message": "Initializing..."})
    
    loop = asyncio.get_event_loop()
    # Run in separate thread to not block the progress endpoint
    return await loop.run_in_executor(executor, process_conversion, url)

def process_conversion(url):
    try:
        if cancel_event.is_set(): 
            current_progress.update({"status": "cancelled", "message": "Operation cancelled before start"})
            return {"success": False, "error": "Cancelled by user"}

        service = get_drive_service()
        if not service:
             current_progress.update({"status": "error", "message": "Auth failed"})
             return {"success": False, "error": "Not authenticated"}

        folder_id = extract_folder_id(url)
        current_progress.update({"status": "processing", "percent": 5, "message": "Scanning folder..."})
        
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            pageSize=100,
            fields="files(id, name, mimeType)",
            orderBy="name"
        ).execute()
        files = results.get('files', [])
        
        if not files:
            current_progress.update({"status": "error", "message": "No images found"})
            return {"success": False, "error": "No images found"}
            
        total_files = len(files)
        current_progress.update({"status": "processing", "percent": 10, "message": f"Found {total_files} images. Starting download..."})

        pdf = FPDF()
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Reusing the helper logic
            downloaded_files = asyncio.run(download_images_from_folder(service, folder_id, tmp_dir))
            
            if downloaded_files is None: # Cancelled
                raise Exception("Cancelled by user")
            
            if not downloaded_files:
                return {"success": False, "error": "No images found in folder"}

            # 2. PDF Generation
            pdf = FPDF()
            total_files = len(downloaded_files)
            
            for i, f_info in enumerate(downloaded_files):
                # Check cancellation
                if cancel_event.is_set():
                    current_progress.update({"status": "cancelled", "message": "Operation cancelled by user"})
                    return {"success": False, "error": "Cancelled by user"}
                
                # Update progress (PDF generation phase: 80% to 95%)
                percent = 80 + int((i / total_files) * 15)
                current_progress.update({
                    "status": "processing",
                    "percent": percent,
                    "message": f"Generating PDF page {i+1}/{total_files}..."
                })
                
                tmp_path = f_info["path"]
                try:
                    img = Image.open(tmp_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    pdf.add_page()
                    pdf.image(tmp_path, x=0, y=0, w=210)
                except Exception as e:
                    print(f"Skipping {f_info['name']}: {e}")
            
            current_progress.update({"status": "processing", "percent": 98, "message": "Saving PDF..."})
            output_path = "output_ebook.pdf"
            pdf.output(output_path, "F")
            
        current_progress.update({"status": "complete", "percent": 100, "message": "Done!"})
        return {"success": True, "download_url": "/api/download"}

    except Exception as e:
        current_progress.update({"status": "error", "message": str(e)})
        return {"success": False, "error": str(e)}

@app.get("/api/download")
def download_ebook():
    # Check for latest OCR result ZIP in results/ folder
    import glob
    ocr_zips = glob.glob("results/ocr_*.zip")
    if ocr_zips:
        latest_zip = max(ocr_zips, key=os.path.getmtime)
        return FileResponse(latest_zip, media_type="application/zip", filename=os.path.basename(latest_zip))
    
    # Fallback to PDF if exists
    if os.path.exists("output_ebook.pdf"):
        return FileResponse("output_ebook.pdf", media_type="application/pdf", filename="your_ebook.pdf")
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/")
def read_root():
    return {"message": "Google Drive Ebook API is running"}
