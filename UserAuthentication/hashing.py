from passlib.context import CryptContext

passwordHasher = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Hasher:
    def hashPassword(password):
        return passwordHasher.hash(password)

    def verifyPassword(plain,hashed):
        return passwordHasher.verify(plain,hashed)