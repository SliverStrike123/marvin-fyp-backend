import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from hashing import Hasher
from jwttoken import create_access_token
from gemini import get_chatResponse
from datetime import datetime

app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8080",
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
users = db["users"]
chat = db["chats"]

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

@app.post("/register")
def create_user(request:User):
    user_exist = (db["users"].find_one({"email": request.email}) or db["users"].find_one({"username": request.username}))
    if(user_exist):
        raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="This email or username is associated with an exisitng account"
        )
    hashed_pass = Hasher.hashPassword(request.password)
    user_object = dict(request)
    user_object["password"] = hashed_pass
    user_db = users.insert_one(user_object)
    print(user_object)
    print(user_db.inserted_id)
    return {"res":"created"}

@app.post("/login")
def login(request:OAuth2PasswordRequestForm = Depends()):
	user = db["users"].find_one({"username":request.username})
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'No user found')
	if not Hasher.verifyPassword(request.password,user["password"]):
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'Wrong email or password')
	access_token = create_access_token(data={"sub": user["username"] })
	return {"access_token": access_token, "token_type": "bearer"}

@app.post("/chat")
def chat(prompt: ChatPrompt):
    try:
        msg = dict(prompt)
        msg["timestamp"] = datetime.now()
        msg["userrole"] = "user"
        chat.insert_one(msg)
        response = get_chatResponse(prompt.prompt)
        aiResponse = ChatPrompt(
            userrole="gemini",
            username=prompt.username,
            timestamp=datetime.now(),
            prompt=response
        )
        chat.insert_one(dict(aiResponse))
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))