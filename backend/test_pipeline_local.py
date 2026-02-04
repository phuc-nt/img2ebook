import os
import time
from PIL import Image
from dotenv import load_dotenv
from services.gemini_service import GeminiOCR
import zipfile
import io

# Load local .env
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
IMAGE_DIR = os.getenv("LOCAL_TEST_IMAGE_DIR", "../test/img")

def run_local_ocr():
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    # 1. Gather local images with NATURAL SORT
    import re
    def natural_keys(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

    all_files = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_files = sorted([os.path.join(IMAGE_DIR, f) for f in all_files], key=lambda x: natural_keys(os.path.basename(x)))
    
    if not image_files:
        print(f"No images found in {IMAGE_DIR}")
        return

    print(f"--- Local OCR Test Stage ---")
    print(f"Total images: {len(image_files)}")
    
    gemini = GeminiOCR(API_KEY)
    
    # BATCHING STRATEGY: Maximize parallelism (up to 100 batches)
    # For local test, we run sequentially but use same logic as production
    total_batches = min(100, len(image_files))  # Max 100 batches or 1 per file
    batch_size = (len(image_files) + total_batches - 1) // total_batches
    
    print(f"Batch strategy: {total_batches} batches, ~{batch_size} images/batch")
    
    full_text = ""
    
    # We will run this synchronously for the test to see clear logs
    for i in range(total_batches):
        start_idx = i * batch_size
        end_idx = min(start_idx + batch_size, len(image_files))
        batch_paths = image_files[start_idx:end_idx]
        
        print(f"\n[Batch {i+1}/{total_batches}] Processing files: {[os.path.basename(p) for p in batch_paths]}...")
        
        images = [Image.open(p) for p in batch_paths]
        
        try:
            start_time = time.time()
            # Simple progress callback for logs
            def log_progress(text_chunk):
                print(".", end="", flush=True)
                
            text = gemini.transcribe_batch(images, progress_callback=log_progress)
            duration = time.time() - start_time
            print(f"\nBatch {i+1} complete ({len(text)} chars) in {duration:.2f}s")
            
            full_text += text + "\n\n"
        except Exception as e:
            print(f"\nError in batch {i+1}: {e}")
        finally:
            for img in images: img.close()

    # 2. Packaging / Splitting with deduplication
    print("\n--- Final Processing: Segmentation ---")
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"results/ocr_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    
    if "<<<CHAPTER_START:" in full_text:
        parts = full_text.split("<<<CHAPTER_START:")
        
        # Save intro
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
                
                # Normalize for comparison
                normalized = title.lower().replace(" ", "")
                
                if normalized in chapters:
                    # Merge with existing
                    chapters[normalized]["content"] += "\n\n" + content
                    print(f"Merged duplicate: {title}")
                else:
                    chapters[normalized] = {"title": title, "content": content}
        
        # Write deduplicated chapters
        for j, (norm_title, data) in enumerate(chapters.items()):
            safe_title = "".join([c for c in data["title"] if c.isalnum() or c in (' ', '_')]).strip()
            name = f"{j+1:02d}_{safe_title}.txt"
            with open(os.path.join(output_dir, name), 'w', encoding='utf-8') as f:
                f.write(data["content"])
            print(f"Created: {name}")
    else:
        with open(os.path.join(output_dir, "full_text.txt"), 'w', encoding='utf-8') as f:
            f.write(full_text)
        print("No segments detected. Outputting full text.")

    print(f"\nResults saved to folder: {output_dir}")
    print("\nPreview of first 500 chars:")
    print("-" * 30)
    print(full_text[:500])
    print("-" * 30)

if __name__ == "__main__":
    run_local_ocr()
