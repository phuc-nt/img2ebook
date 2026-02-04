import os
import time
import google.generativeai as genai
from typing import List
from PIL import Image

class GeminiOCR:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # Using the experimental flash model or the latest stable flash
        self.model = genai.GenerativeModel('gemini-3-flash-preview')

    def generate_prompt(self):
        return """
You are a professional book transcribing agent using advanced vision and reasoning. 
Your goal is to extract text from the provided sequence of book pages and convert them into a single, clean, flowable text.

### STRICT RULES:
1. **SEAMLESS CONTINUITY**: 
   - Most book scans have line breaks at the end of every physical line. You MUST remove these.
   - Join pieces of words that were hyphenated at the end of a line (e.g., "re-markable" becomes "remarkable").
   - Only use professional paragraph breaks (usually a double newline) when a paragraph actually ends in the source text.
   - Output should look like a modern ebook/digital text, not a rigid recreation of the printed page layout.

2. **CHAPTER & ARTICLE SEGMENTATION**:
   - Detect start of Chapters, Articles, or major sections (e.g., "Chapter 1", "I. Introduction", "Tên Bài Viết").
   - When you find a new section, insert a divider: `<<<CHAPTER_START: [Section Title]>>>`.
   - Ensure the title in the divider is descriptive.

3. **NOISE REMOVAL**:
   - Remove page numbers, headers, and footers completely.
   - Do not include any side notes or metadata unless it's part of the main text body.

4. **ACCURACY**:
   - Transcribe every word exactly as it appears. Do not summarize.

Output: Return ONLY the continuous transcribed text.
"""

    def transcribe_batch(self, images: List[Image.Image], progress_callback=None, cancel_callback=None) -> str:
        """
        Sends a batch of images to Gemini Flash for transcription.
        Supports streaming response for progress updates and immediate cancellation.
        """
        prompt = self.generate_prompt()
        
        # Prepare content: [Prompt, Img1, Img2, ...]
        content = [prompt]
        content.extend(images)
        
        try:
            # Use stream=True to get chunks
            response = self.model.generate_content(content, stream=True)
            full_text = ""
            for chunk in response:
                # Check cancellation first
                if cancel_callback and cancel_callback():
                    raise Exception("Cancelled by user")
                
                # Check for safety/copyright blocks (candidates might be empty)
                if not chunk.candidates:
                    continue
                    
                # Access text safely
                try:
                    if chunk.text:
                        full_text += chunk.text
                        if progress_callback:
                            progress_callback(chunk.text)
                except ValueError:
                    # Handle cases where safety filters block content
                    print(f"Warning: Chunk blocked. Finish reason: {chunk.candidates[0].finish_reason}")
                    continue
                    
            return full_text
        except Exception as e:
            # Propagate cancellation immediately
            if "Cancelled by user" in str(e):
                raise e
                
            # Handle rate limits or other API errors
            print(f"Gemini API Error: {e}")
            if "429" in str(e):
                print(f"Rate limit hit. Sleeping for 20s...")
                if cancel_callback and cancel_callback(): raise Exception("Cancelled by user")
                time.sleep(20) 
                return self.transcribe_batch(images, progress_callback, cancel_callback)
            raise e
