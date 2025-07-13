from typing import List
from google import genai
from google.genai import types
from PIL import Image
import os
from dotenv import load_dotenv
from pydantic import BaseModel
import pytesseract
import fitz  
from fastapi import HTTPException


load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_api_key)

class QuestionAnswer(BaseModel):
    question: str
    options: List[str]
    selected: str

class EvaluationRequest(BaseModel):
    responses: List[QuestionAnswer]

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
        # Render image at higher resolution
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
        # OCR with better config
        page_text = pytesseract.image_to_string(img, lang="eng", config="--oem 3")
        text += page_text

    doc.close()

    text = text[:12000] 
    prompt = f"""
        You are a strict classifier. Carefully analyze the content below. 
        If it contains any mathematical topics, even in part — such as formulas, equations, expressions, numerical problems, definitions, or topics from algebra, geometry, trigonometry, calculus, etc. — respond with 'yes'.

        If the content is completely unrelated to math, respond with 'no'.

        Content:
        {text}
        """
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(),
        contents=prompt
    )

    return "yes" in response.text.lower() 

def generate_quiz(pdf: str, message: str = None):
    # Extract text from PDF
    doc = fitz.open(pdf)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    # Ensure text is within Gemini's context limit
    truncated_text = text[:12000]

    # Prepare prompt
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
            }}
        ]
        }}

        Here is the content:
        {truncated_text}

        Here is an additional message from the user (optional):
        {message if message else ""}
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are a math tutor and only answer math-related questions."
        ),
        contents=input_content
    )

    return response.text


def evaluate_user_skill(req: EvaluationRequest):
    prompt = "You're an educational evaluator. Based on the following questions and user's answers, determine whether the user is a Beginner, Intermediate, or Expert in mathematics. Return ONLY the skill level.\n\n"

    for i, qa in enumerate(req.responses, start=1):
        prompt += f"Q{i}: {qa.question}\nOptions: {', '.join(qa.options)}\nUser's Answer: {qa.selected}\n\n"

    prompt += "\nYour response should be only one word: Beginner, Intermediate, or Expert."

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config=types.GenerateContentConfig(
                system_instruction="You are a math tutor evaluating a user's skill level based on their responses to math questions."
            ),
            contents=prompt
        )
        skill_level = response.text.strip().split()[0]  
        print(skill_level)
        return { "skill_level": skill_level }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))