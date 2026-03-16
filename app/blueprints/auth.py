from flask import Blueprint, request, jsonify, current_app
import bcrypt
import jwt
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from db import get_connection
from config import JWT_SECRET
from email_utils import send_verification_email

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user_id = str(uuid.uuid4())
    verification_token = secrets.token_urlsafe(32)
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            '''INSERT INTO users(id, email, password, role, email_verified, verification_token, verification_expires)
               VALUES(%s, %s, %s, %s, %s, %s, %s)''',
            (user_id, email, hashed.decode(), 'user', False, verification_token, verification_expires)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({'error': 'Email already registered'}), 400
        return jsonify({'error': 'Registration failed'}), 500
    cur.close()
    conn.close()

    # Send verification email
    email_sent = send_verification_email(email, verification_token)

    if email_sent:
        return jsonify({
            'message': 'Account created! Please check your email to verify your account.',
            'requiresVerification': True
        })
    else:
        return jsonify({
            'message': 'Account created but verification email could not be sent. Please contact support.',
            'requiresVerification': True,
            'warning': True
        })


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({'error': 'Verification token is required'}), 400

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        'SELECT id, email_verified, verification_expires FROM users WHERE verification_token = %s',
        (token,)
    )
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'Invalid verification token'}), 400

    if user['email_verified']:
        cur.close()
        conn.close()
        return jsonify({'message': 'Email already verified'})

    # Check if token has expired
    if user['verification_expires'] and user['verification_expires'].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        cur.close()
        conn.close()
        return jsonify({'error': 'Verification link has expired. Please request a new one.'}), 400

    # Mark email as verified
    cur.execute(
        'UPDATE users SET email_verified = TRUE, verification_token = NULL WHERE id = %s',
        (user['id'],)
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Email verified successfully! You can now sign in.'})


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    conn = get_connection()
    cur = conn.cursor()

    cur.execute('SELECT id, email_verified FROM users WHERE email = %s', (email,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        # Don't reveal if user exists
        return jsonify({'message': 'If an account exists with this email, a verification link will be sent.'})

    if user['email_verified']:
        cur.close()
        conn.close()
        return jsonify({'message': 'This email is already verified. You can sign in.'})

    # Generate new token
    verification_token = secrets.token_urlsafe(32)
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    cur.execute(
        'UPDATE users SET verification_token = %s, verification_expires = %s WHERE id = %s',
        (verification_token, verification_expires, user['id'])
    )
    conn.commit()
    cur.close()
    conn.close()

    send_verification_email(email, verification_token)

    return jsonify({'message': 'If an account exists with this email, a verification link will be sent.'})


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password')

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid credentials'}), 400

    if not bcrypt.checkpw(password.encode(), user['password'].encode()):
        return jsonify({'error': 'Invalid credentials'}), 400

    # Check if email is verified
    if not user.get('email_verified', False):
        return jsonify({
            'error': 'Please verify your email before signing in.',
            'requiresVerification': True,
            'email': email
        }), 403

    token = jwt.encode(
        {
            'id': user['id'],
            'role': user['role'],
            'exp': datetime.now(timezone.utc) + timedelta(hours=1)
        },
        JWT_SECRET,
        algorithm='HS256'
    )

    return jsonify({'token': token})
