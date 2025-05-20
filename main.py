import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from hashing import Hasher
from jwttoken import create_access_token


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
client = MongoClient(uri,port)
db = client["Users"]

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

@app.post("/register")
def create_user(request:User):
	hashed_pass = Hasher.hashPassword(request.password)
	user_object = dict(request)
	user_object["password"] = hashed_pass
	print(user_object)
	return {"res":"created"}

@app.post("/login")
def login(request:OAuth2PasswordRequestForm = Depends()):
	user = db["users"].find_one({"username":request.username})
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'No user found with this {request.username} username')
	if not Hasher.verifyPassword(user["password"],request.password):
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail = f'Wrong Username or password')
	access_token = create_access_token(data={"sub": user["username"] })
	return {"access_token": access_token, "token_type": "bearer"}