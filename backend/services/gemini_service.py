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
Role: Professional Book Transcriber.
Task: Convert these book pages into a single, seamless markdown text file.

Rules:
1. Precision: Keep every word and punctuation mark exactly as seen in the text.
2. Continuity: Do NOT break lines at the end of a physical page. 
   - Merge hyphenated words that split across pages (e.g., "com-" on page 1 and "puter" on page 2 becomes "computer").
   - Only insert a line break/paragraph break if the text clearly indicates a new paragraph.
3. Segmentation: 
   - Detect Chapter titles (e.g. "Chapter 1", "Chương 2", or big bold separate titles). 
   - Before each chapter, insert exactly: "<<<CHAPTER_START: Title Name>>>".
   - If there is no clear chapter title, just continue the text.
4. Noise Removal: Ignore page numbers, headers, and footers. Do not transcribe them.
5. Formatting: Use Markdown for basic formatting (bold, italic) if present in the text.

Output: Return ONLY the transcribed text. Do not add any introductory or concluding remarks.
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
