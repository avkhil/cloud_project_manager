from functools import wraps
from flask import request, jsonify
from app.services.auth import decode_token
from app.models import User

def current_user():
    header=request.headers.get('Authorization','')
    if not header.startswith('Bearer '): return None
    try: return User.query.get(decode_token(header.split(' ',1)[1])['user_id'])
    except Exception: return None

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user=current_user()
        if not user: return jsonify({'error':'Authentication required'}), 401
        return fn(user, *args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user=current_user()
        if not user: return jsonify({'error':'Authentication required'}), 401
        if user.role != 'ADMIN': return jsonify({'error':'Admin access required'}), 403
        return fn(user, *args, **kwargs)
    return wrapper
