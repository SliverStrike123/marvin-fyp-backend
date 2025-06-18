import os
import shutil
import json
from typing import Optional
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from hashing import Hasher
from jwttoken import create_access_token
from gemini import get_chatResponse, is_this_math_related, generate_quiz
from datetime import datetime
from pathlib import Path

app = FastAPI()
origins = [
    "http://localhost:3000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get('/')
def index():
    return {'data':'Hello World'}

load_dotenv()

uri = os.environ.get("MONGO_URI")
port = int(os.environ.get("DEVPORT"))
client = MongoClient(uri,server_api=ServerApi('1'))
db = client["FYP"]
usersDB = db["users"]
chatDB = db["chats"]
quizDB = db["quiz"]
UPLOAD_DIR = "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)

class User(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class ChatPrompt(BaseModel):
    userrole: Optional[str] = None
    username: str
    timestamp: Optional[datetime] = None
    prompt: str

class QuizAttempt(BaseModel):
    username: str
    questions: list
    answers: dict
    score: int
    timestamp: Optional[datetime] = None

@app.post("/register")
def create_user(request:User):
    user_exist = (usersDB.find_one({"email": request.email}) or db["users"].find_one({"username": request.username}))
    if(user_exist):
        raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="This email or username is associated with an exisitng account"
        )
    hashed_pass = Hasher.hashPassword(request.password)
    user_object = dict(request)
    user_object["password"] = hashed_pass
    user_db = usersDB.insert_one(user_object)
    print(user_object)
    print(user_db.inserted_id)
    return {"res":"created"}

@app.post("/login")
def login(request:OAuth2PasswordRequestForm = Depends()):
	user = usersDB.find_one({"username":request.username})
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'No user found')
	if not Hasher.verifyPassword(request.password,user["password"]):
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'Wrong email or password')
	access_token = create_access_token(data={"sub": user["username"] })
	return {"access_token": access_token, "token_type": "bearer"}

@app.post("/chat")
def chat(prompt: ChatPrompt):
    try:
        print("Prompt received:", prompt)
        msg = dict(prompt)
        msg["timestamp"] = datetime.now()
        msg["userrole"] = "user"
        chatDB.insert_one(msg)
        print("Message inserted into chat collection:", msg)
        response = get_chatResponse(prompt.prompt)
        aiResponse = ChatPrompt(
            userrole="gemini",
            username=prompt.username,
            timestamp=datetime.now(),
            prompt=response
        )
        chatDB.insert_one(dict(aiResponse))
        print("AI response inserted into chat collection:", aiResponse)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Reformat chat message retrieved from MongoDB
def reformat_chat_message(message):
    return {
        "id": str(message.get("_id")),
        "userrole": message.get("userrole"),
        "username": message.get("username"),
        "timestamp": message.get("timestamp").isoformat() if message.get("timestamp") else None,
        "prompt": message.get("prompt"),
    }

@app.get("/chats/{username}")
def get_chats(username: str):
    try:
        print(f"Retrieving messages for user: {username}")
        messages = chatDB.find({"username": username}).sort("timestamp", 1)
        print(f"Retrieved messages for user {username}: {messages}")
        formatted_messages = [reformat_chat_message(m) for m in messages]
        return formatted_messages
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@app.post("/generatequiz")
def generate_quiz_from_pdf(file: UploadFile = File(...),message: Optional[str] = None):
    fileType = file.filename.split(".")[-1]
    if fileType not in ["pdf"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type. Only PDF and TXT files are allowed.")
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if not is_this_math_related(file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The provided file is not math-related.")
    
    quiz = generate_quiz(file_path)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate quiz.")
    
    quiz = quiz.strip().replace("```json", "").replace("```", "").strip()

    try:
        quiz_dict = json.loads(quiz)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid quiz format: {str(e)}"
        )

    # Return the parsed JSON object
    return {"quiz": quiz_dict}


@app.post("/savequizattempt")
def save_quiz_attempt(attempt: QuizAttempt):
    try:
        attempt_data = dict(attempt)
        attempt_data["timestamp"] = datetime.now()
        quizDB.insert_one(attempt_data)
        return {"message": "Quiz attempt saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
