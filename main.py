import os
import shutil
import json
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Form, Body
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient, DESCENDING, ReturnDocument
from pymongo.server_api import ServerApi
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from hashing import Hasher
from jwttoken import create_access_token
from gemini import get_chatResponse, is_this_math_related, generate_quiz, evaluate_user_skill
from datetime import datetime
from pathlib import Path
from bson import ObjectId

class QuestionAnswer(BaseModel):
    question: str
    options: List[str]
    selected: str

class EvaluationRequest(BaseModel):
    responses: List[QuestionAnswer]

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
beginnerDB = db["beginner"]
intermediateDB = db["intermediate"]
expertDB = db["expert"]
UPLOAD_DIR = "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)

class User(BaseModel):
    email: EmailStr
    username: str
    password: str
    skill_level: Optional[str] = None

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
    user_object["skill_level"] = "None"
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

@app.get("/getuserdetails/{username}")
def get_user_details(username: str):
    try:
        user = usersDB.find_one({"username": username}, {"_id": 0, "username": 1, "email": 1})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  
        
@app.put("/updateuser/{username}")
def update_user(username: str, data: dict = Body(...)):
    try:
        update_fields = {}
        if "username" in data:
            new_username = data["username"]
            if new_username != username:
                user_exist = usersDB.find_one({"username": new_username})
                if user_exist:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="This username is already associated with an existing account"
                    )
                update_fields["username"] = new_username
        if "email" in data:
            update_fields["email"] = data["email"]

        if not update_fields:
            raise HTTPException(status_code=400, detail="No valid fields to update.")

        updated_user = usersDB.find_one_and_update(
            {"username": username},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "username": 1, "email": 1}
        )

        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found.")

        return {"message": "User updated successfully", "user": updated_user}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.delete("/deleteuser/{username}")
def delete_user(username: str):
    try:
        result = usersDB.delete_one({"username": username})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found.")

        return {"message": f"User '{username}' has been deleted successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

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
def generate_quiz_from_pdf(file: UploadFile = File(...),message: Optional[str] = Form(None)):
    fileType = file.filename.split(".")[-1]
    if fileType not in ["pdf"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type. Only PDF and TXT files are allowed.")
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if not is_this_math_related(file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The provided file is not math-related.")
    
    quiz = generate_quiz(file_path, message)
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

@app.get("/getquizattempts/{username}")
def get_quiz_attempts(username: str):
    try:
        attempts = list(quizDB.find({"username": username}).sort("timestamp", DESCENDING))
        for attempt in attempts:
            attempt["_id"] = str(attempt["_id"])  # Convert ObjectId to string for JSON serialization
            attempt["timestamp"] = attempt["timestamp"].isoformat()  # Convert datetime to string
        return {"attempts": attempts}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

@app.get("/getquizattempt/{attempt_id}")
def get_quiz_attempt(attempt_id: str):
    try:
        attempt = quizDB.find_one({"_id": ObjectId(attempt_id)})
        if not attempt:
            raise HTTPException(status_code=404, detail="Quiz attempt not found")
        
        attempt["_id"] = str(attempt["_id"])
        attempt["timestamp"] = attempt["timestamp"].isoformat()
        return attempt
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/getuserskilllevel/{username}")
def get_user_skill_level(username: str):
    try:
        user = usersDB.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")  
        
        skill_level = user.get("skill_level", "None")
        result = usersDB.update_one(
            {"username": username},
            {"$set": {"skill_level": skill_level}}
        )
        print("Skill level updated in database:", result.modified_count)
        return {"username": username, "skill_level": skill_level}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/setuserskilllevel/{username}/{skill_level}")
def set_user_skill_level(username: str, skill_level: str):
    try:
        result = usersDB.update_one(
            {"username": username},
            {"$set": {"skill_level": skill_level}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  


@app.post("/evaluate-skill")
def evaluate_skill_user(req: EvaluationRequest):
    return evaluate_user_skill(req)

@app.post("/awardbadge/{username}/{badge_name}")
def award_badge(username: str, badge_name: str):
    
    if not username or not badge_name:
        raise HTTPException(status_code=400, detail="Username and badge name are required.")
    match badge_name.lower():
        case "beginner":
            badgeDB = beginnerDB
        case "intermediate":
            badgeDB = intermediateDB
        case "expert":
            badgeDB = expertDB
    try:
        badge = {
            "username": username,
            "timestamp": datetime.now()
        }
        badgeDB.insert_one(badge)
        return {"message": f"Badge '{badge_name}' awarded to {username}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/getbadge/{username}/{badge_name}")
def get_badges(username: str, badge_name: str):
    if not username or not badge_name:
        raise HTTPException(status_code=400, detail="Username and badge name are required.")
    match badge_name.lower():
        case "beginner":
            badgeDB = beginnerDB
        case "intermediate":
            badgeDB = intermediateDB
        case "expert":
            badgeDB = expertDB
    print(badgeDB)
    try:
        badge = badgeDB.find_one({"username": username})
        print(f"Retrieved badge for {username}: {badge}")
        if not badge:
            raise HTTPException(status_code=404, detail="Badge not found")
        print(f"Badge found: {badge}")
        badge["timestamp"] = badge["timestamp"].isoformat()  # Convert datetime to string
        if "timestamp" in badge and isinstance(badge["timestamp"], datetime):
            badge["timestamp"] = badge["timestamp"].isoformat()
        else:
            badge["timestamp"] = None
        return {"badge": badge}
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/getbadges/{username}")
def get_all_badges(username: str):
    beginner = beginnerDB.find_one({"username": username})
    intermediate = intermediateDB.find_one({"username": username})
    expert = expertDB.find_one({"username": username})

    badges = []
    if beginner:
        badges.append("Beginner")
    if intermediate:
        badges.append("Intermediate")
    if expert:
        badges.append("Expert")

    return {"badges": badges}