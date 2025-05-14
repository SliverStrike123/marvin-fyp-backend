import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

uri = os.environ.get("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client.user_db
users_collection = db.users

passwordHasher = CryptContext(schemes=["bcrypt"], deprecated="auto")



def hashPassword(password):
    return passwordHasher.hash(password)

def verifyPassword(plain,hashed):
    return passwordHasher.verify(plain,hashed)

async def get_user(email):
    user = await users_collection.find_one({"email":email})
    if user:
        return UserInDB(**user)

async def authenticate_user(email, password):
    user = await get_user(email)
