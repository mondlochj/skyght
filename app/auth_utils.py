from functools import wraps
from flask import request, jsonify, g
import jwt
from config import JWT_SECRET

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'message': 'No token'}), 401

        token = auth_header.split(' ')[1]
        try:
            decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            g.user = decoded
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if g.user.get('role') != 'admin':
            return jsonify({'message': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated
