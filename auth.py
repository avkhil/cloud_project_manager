from datetime import datetime, timedelta, timezone
import jwt
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User

def hash_password(password): return generate_password_hash(password)
def verify_password(user, password): return check_password_hash(user.password_hash, password)

def make_token(user):
    payload = {'user_id': user.id, 'role': user.role, 'exp': datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')

def decode_token(token):
    return jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
