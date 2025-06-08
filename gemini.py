from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import fitz  


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

def is_this_math_related(pdf: str):
    doc = fitz.open(pdf)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are a math tutor and only answer to math-related questions, " \
            "based on the provided PDF content. Determine if the content is math-related or not." \
            "Your response should contain either 'yes' or 'no'."
        ), 
        contents=doc
    )
    print(response.text)
    return "yes" in response 

def generate_quiz(pdf: str):
    # Extract text from PDF
    doc = fitz.open(pdf)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    # Ensure text is within Gemini's context limit
    truncated_text = text[:12000]  # Optional: Trim to fit token limits

    # Initialize Gemini model
    model = genai.GenerativeModel("gemini-1.5-flash")  # or "gemini-pro" or other supported model

    # Prepare input as `Content` object
    input_content = f"""
    You are a math tutor and only answer math-related questions.
    The user will provide you with the content of a math-based PDF file (slides or notes).
    Your task is to generate a quiz based on the provided content.

    Respond strictly in JSON format like this:
    {{
    "questions": [
        {{
        "question": "What is the derivative of x^2?",
        "options": ["1", "2x", "x^2", "2"],
        "answer": "2x"
        }},
        ...
    ]
    }}

    Here is the content:
    {truncated_text}
    """

    # Generate response
    response = model.generate_content(input_content)

    return response.text
