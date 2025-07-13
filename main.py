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
beginnerQuizDB = db["beginner_quiz"]
intermediateQuizDB = db["intermediate_quiz"]
expertQuizDB = db["expert_quiz"]
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
    userID: str
    timestamp: Optional[datetime] = None
    prompt: str

class QuizAttempt(BaseModel):
    userID: str
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
             detail="This email or username is associated with an existing account"
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
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'Wrong username or password')
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
            email_exist = usersDB.find_one({"email": data["email"], "username": {"$ne": username}})
            if email_exist:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This email is already associated with an existing account"
                )
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
        user = usersDB.find_one({"username": username})
        userID = user["_id"] if user else None
        result = usersDB.delete_one({"username": username})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found.")
        # Collections to clean up user data from
        collections = [
            chatDB,
            quizDB,
            beginnerDB,
            intermediateDB,
            expertDB,
            beginnerQuizDB,
            intermediateQuizDB,
            expertQuizDB
        ]

        # Delete user-related documents from each collection
        for collection in collections:
            collection.delete_many({"userID": userID})
        return {"message": f"User '{username}' has been deleted successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/chat")
def chat(prompt: ChatPrompt):
    try:
        user = usersDB.find_one({"username": prompt.userID})
        user_id = user["_id"]
        print("Prompt received:", prompt)
        msg = dict(prompt)
        msg["timestamp"] = datetime.now()
        msg["userrole"] = "user"
        msg["userID"] = user_id
        chatDB.insert_one(msg)
        print("Message inserted into chat collection:", msg)
        response = get_chatResponse(prompt.prompt)
        print("AI response received:", response)
        aiResponse = ChatPrompt(
            userrole="gemini",
            userID=str(user_id),  
            timestamp=datetime.now(),
            prompt=response
        )
        chatDB.insert_one({
            "userrole": aiResponse.userrole,
            "userID": ObjectId(aiResponse.userID),  
            "timestamp": aiResponse.timestamp,
            "prompt": aiResponse.prompt
        })
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
        user = usersDB.find_one({"username": username})
        user_id = user["_id"]
        messages = chatDB.find({"userID": user_id}).sort("timestamp", 1)
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
        user = usersDB.find_one({"username": attempt_data["userID"]})
        attempt_data["userID"] = user["_id"] if user else None
        attempt_data["timestamp"] = datetime.now()
        quizDB.insert_one(attempt_data)
        return {"message": "Quiz attempt saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/getquizattempts/{username}")
def get_quiz_attempts(username: str):
    try:
        user = usersDB.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        attempts = list(quizDB.find({"userID": user["_id"]}).sort("timestamp", DESCENDING))
        print(f"Retrieved {len(attempts)} quiz attempts for user {username}")
        for attempt in attempts:
            attempt["_id"] = str(attempt["_id"])  # Convert ObjectId to string for JSON serialization
            attempt["timestamp"] = attempt["timestamp"].isoformat()  # Convert datetime to string
            attempt["userID"] = str(attempt["userID"])
        return {"attempts": attempts}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

@app.get("/getquizattempt/{attempt_id}")
def get_quiz_attempt(attempt_id: str):
    try:
        print(attempt_id)
        attempt = quizDB.find_one({"_id": ObjectId(attempt_id)})

        if not attempt:
            raise HTTPException(status_code=404, detail="Quiz attempt not found")
        
        attempt["_id"] = str(attempt["_id"])
        attempt["timestamp"] = attempt["timestamp"].isoformat()
        attempt["userID"] = str(attempt["userID"])
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
        return {"username": username, "skill_level": skill_level}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/setuserskilllevel/{username}/{skill_level}")
def set_user_skill_level(username: str, skill_level: str):
    try:
        # Define the hierarchy
        skill_hierarchy = {
            "beginner": 0,
            "intermediate": 1,
            "expert": 2
        }

        # Fetch the user
        user = usersDB.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        current_level = user.get("skill_level", "None").lower()
        compared_skill_level = skill_level.lower()

        # Compare current and new skill levels
        if current_level=="none" or skill_hierarchy[compared_skill_level] > skill_hierarchy.get(current_level, 0):
            result = usersDB.update_one(
                {"username": username},
                {"$set": {"skill_level": skill_level}}
            )
            print("Skill level updated in database:", result.modified_count)
        else:
            print(f"Skill level remains at {current_level}. No update performed.")
    
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
        user = usersDB.find_one({"username": username})
        badge = {
            "userID": user["_id"],
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
        case _:
            raise HTTPException(status_code=400, detail="Invalid badge name")

    try:
        user = usersDB.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        badge = badgeDB.find_one({"userID": user["_id"]})
        if not badge:
            raise HTTPException(status_code=404, detail="Badge not found")

        # ──► convert the non‑JSON types
        if isinstance(badge.get("_id"), ObjectId):
            badge["_id"] = str(badge["_id"])
        if isinstance(badge.get("userID"), ObjectId):
            badge["userID"] = str(badge["userID"])
        if isinstance(badge.get("timestamp"), datetime):
            badge["timestamp"] = badge["timestamp"].isoformat()

        return {"badge": badge}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/getbadges/{username}")
def get_all_badges(username: str):
    user = usersDB.find_one({"username": username})
    beginner = beginnerDB.find_one({"userID": user["_id"]})
    intermediate = intermediateDB.find_one({"userID": user["_id"]})
    expert = expertDB.find_one({"userID": user["_id"]})
    
    badges = []
    if beginner:
        badges.append("Beginner")
    if intermediate:
        badges.append("Intermediate")
    if expert:
        badges.append("Expert")

    return {"badges": badges}


@app.post("/saveLessonQuizScore/{username}/{skill_level}/{score}")
def save_lesson_quiz(username: str, skill_level: str, score: int):
    try:
        print("Looking for user:", username)
        user = usersDB.find_one({"username": username})
        match skill_level.lower():
            case "beginner":
                lessonQuizDB = beginnerQuizDB
            case "intermediate":
                lessonQuizDB = intermediateQuizDB
            case "expert":
                lessonQuizDB = expertQuizDB
        print(f"Saving score for user: {username}, skill level: {skill_level}, score: {score}")
        if not user:
            raise HTTPException(status_code=404, detail="User not found")   
        
        print(f"User found: {user['_id']}")
        if lessonQuizDB.find_one({"userID": user["_id"]}):
            result = beginnerQuizDB.find_one({"userID": user["_id"]})
            if result["score"] < score:
                lessonQuizDB.update_one(
                    {"userID": user["_id"]},
                    {"$set": {"score": score, "timestamp": datetime.now()}}
                )
            else:
                return {"message": "Score is not higher than the existing score."}
        else:
            lessonQuizDB.insert_one({
                "userID": user["_id"],
                "score": score,
                "timestamp": datetime.now()
            })
        return {"message": "Quiz score saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/leaderboard/{skill_level}")
def get_leaderboard(skill_level: str):
    try:
        match skill_level.lower():
            case "beginner":
                lessonQuizDB = beginnerQuizDB
            case "intermediate":
                lessonQuizDB = intermediateQuizDB
            case "expert":
                lessonQuizDB = expertQuizDB
            case _:
                raise HTTPException(status_code=400, detail="Invalid skill level")

        leaderboard = list(lessonQuizDB.find().sort("score", DESCENDING).limit(10))
        print(f"Retrieved {len(leaderboard)} entries from the leaderboard for skill level: {skill_level}")

        for entry in leaderboard:
            username_doc = usersDB.find_one({"_id": entry["userID"]}, {"username": 1})
            entry["_id"] = str(entry["_id"])
            entry["userID"] = str(entry["userID"])
            entry["username"] = username_doc["username"] if username_doc else "Unknown"
            entry["score"] = entry.get("score", 0)
            entry["timestamp"] = entry["timestamp"].isoformat()

        return {"leaderboard": leaderboard}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))