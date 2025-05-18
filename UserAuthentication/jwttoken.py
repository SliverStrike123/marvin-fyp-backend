from datetime import datetime, timedelta
from jose import JWTError, jwt
from main import TokenData
import os
from dotenv import load_dotenv

load_dotenv()

SECRETKEY = os.environ.get("SECRETKEY")
ALG = "HS256"
EXPIRE_TIME_MINS = 30

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_TIME_MINS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRETKEY, algorithm=ALG)
    return encoded_jwt

def verify_token(token:str,credentials_exception):
    try:
        payload = jwt.decode(token, SECRETKEY, algorithms=[ALG])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

