from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_api_key)

def get_chatResponse(prompt: str):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are a math tutor and only answer to math-related questions."
        ), 
        contents=prompt
    )
    return response.text
