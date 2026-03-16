from flask import Blueprint, jsonify, request
from db import get_connection
from auth_utils import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, email, role FROM users')
    users = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(users)

@admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@admin_required
def update_user_role(user_id):
    data = request.get_json()
    new_role = data.get('role')

    if new_role not in ['user', 'admin']:
        return jsonify({'error': 'Invalid role'}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE users SET role = %s WHERE id = %s',
        (new_role, user_id)
    )
    updated = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if updated == 0:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'message': 'Role updated'})
