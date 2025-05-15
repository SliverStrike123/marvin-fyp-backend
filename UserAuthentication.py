from fastapi import FastAPI,HTTPException,status
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

load_dotenv()

uri = os.environ.get("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client.user_db
users_collection = db.users

passwordHasher = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(BaseModel):
    email: EmailStr
    username: str

class UserInDB(BaseModel):
    email: EmailStr
    hashed_password: str
    username: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str

def hashPassword(password):
    return passwordHasher.hash(password)

def verifyPassword(plain,hashed):
    return passwordHasher.verify(plain,hashed)

async def get_user(email):
    user = await users_collection.find_one({"email":email})
    if user:
        return user
    else:
        return None

async def authenticate_user(email, password):
    user = await get_user(email)
    if user and verifyPassword(password, user['password']):
        return user
    else:
        return False

@app.post("/register", response_model=User)
async def register_user(userData: UserRegister):
    #check if user exist
    existing_user = users_collection.find_one({email:userData.email})
    if(existing_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            details="EMAIL ALREADY EXIST"
        )

    hashedpassword = hashPassword(userData.password)

    registered_user = UserInDB(
        email=userData.email,
        hashed_password=hashedpassword,
        username=userData.username
    )

    await users_collection.insert_one(registered_user.model_dump())

    return User(email=userData.email,username=userData.username)

