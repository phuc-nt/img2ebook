import google.generativeai as genai
from PIL import Image
import time
import os

# API Key provided by user
API_KEY = "AIzaSyCjQNRTiIR7J_U1lcSaXHMpYYjlQPfxSsI"

def test_gemini():
    print(f"Configuring Gemini with key: {API_KEY[:5]}...")
    genai.configure(api_key=API_KEY)
    
    # Use the requested model
    model_name = 'gemini-3-flash-preview'
    print(f"Initializing model: {model_name}")
    model = genai.GenerativeModel(model_name)
    
    img_path = "test/img/Copy of page_5.png"
    if not os.path.exists(img_path):
        print(f"Error: File {img_path} not found.")
        return

    print(f"Opening image: {img_path}")
    img = Image.open(img_path)
    
    prompt = "Transcribe this text exactly."
    
    print("Sending request to Gemini... (Stream=True)")
    start_time = time.time()
    
    try:
        response = model.generate_content([prompt, img], stream=True)
        
        print("Response received. Iterating chunks...")
        char_count = 0
        for chunk in response:
            if chunk.text:
                print(f"Chunk received: {len(chunk.text)} chars")
                char_count += len(chunk.text)
            
        print(f"Total characters: {char_count}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_gemini()
