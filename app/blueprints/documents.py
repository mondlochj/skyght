from flask import Blueprint, request, jsonify, g
import uuid
import json
from datetime import datetime
from db import get_connection
from auth_utils import login_required

documents_bp = Blueprint('documents', __name__, url_prefix='/api/documents')


def get_user_team_role(team_id, user_id):
    """Get user's role in a team (owner, admin, editor, viewer, or None)."""
    conn = get_connection()
    cur = conn.cursor()

    # Check if owner
    cur.execute('SELECT owner_id FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    if team and team['owner_id'] == user_id:
        cur.close()
        conn.close()
        return 'owner'

    # Check membership
    cur.execute(
        'SELECT role FROM team_members WHERE team_id = %s AND user_id = %s',
        (team_id, user_id)
    )
    member = cur.fetchone()
    cur.close()
    conn.close()

    return member['role'] if member else None


def can_view(role):
    return role in ('owner', 'admin', 'editor', 'viewer')


def can_edit(role):
    return role in ('owner', 'admin', 'editor')


def can_admin(role):
    return role in ('owner', 'admin')


# ============== Documents ==============

@documents_bp.route('/team/<team_id>', methods=['GET'])
@login_required
def list_documents(team_id):
    """List documents in a team, optionally filtered by folder."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_view(role):
        return jsonify({'error': 'Not authorized'}), 403

    folder_id = request.args.get('folder_id')

    conn = get_connection()
    cur = conn.cursor()

    if folder_id:
        cur.execute('''
            SELECT d.*, u.email as uploaded_by_email
            FROM documents d
            LEFT JOIN users u ON d.uploaded_by = u.id
            WHERE d.team_id = %s AND d.folder_id = %s
            ORDER BY d.created_at DESC
        ''', (team_id, folder_id))
    else:
        # Root level (no folder)
        cur.execute('''
            SELECT d.*, u.email as uploaded_by_email
            FROM documents d
            LEFT JOIN users u ON d.uploaded_by = u.id
            WHERE d.team_id = %s AND d.folder_id IS NULL
            ORDER BY d.created_at DESC
        ''', (team_id,))

    documents = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(documents)


@documents_bp.route('/team/<team_id>/all', methods=['GET'])
@login_required
def list_all_documents(team_id):
    """List all documents in a team (regardless of folder)."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_view(role):
        return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
        SELECT d.*, u.email as uploaded_by_email, f.name as folder_name
        FROM documents d
        LEFT JOIN users u ON d.uploaded_by = u.id
        LEFT JOIN folders f ON d.folder_id = f.id
        WHERE d.team_id = %s
        ORDER BY d.created_at DESC
        LIMIT 100
    ''', (team_id,))

    documents = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(documents)


@documents_bp.route('/team/<team_id>', methods=['POST'])
@login_required
def create_document(team_id):
    """Save an OCR result as a document."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_edit(role):
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json()
    filename = data.get('filename')
    ocr_text = data.get('ocr_text')
    file_type = data.get('file_type')
    file_size = data.get('file_size')
    ocr_language = data.get('ocr_language', 'eng')
    preprocessing_options = data.get('preprocessing_options')
    folder_id = data.get('folder_id')

    if not filename or not ocr_text:
        return jsonify({'error': 'Filename and OCR text are required'}), 400

    doc_id = str(uuid.uuid4())

    conn = get_connection()
    cur = conn.cursor()

    # Verify folder belongs to team if specified
    if folder_id:
        cur.execute('SELECT id FROM folders WHERE id = %s AND team_id = %s', (folder_id, team_id))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Folder not found'}), 404

    cur.execute('''
        INSERT INTO documents (id, team_id, folder_id, uploaded_by, filename, file_type,
                              file_size, ocr_text, ocr_language, preprocessing_options)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (doc_id, team_id, folder_id, g.user['id'], filename, file_type,
          file_size, ocr_text, ocr_language,
          json.dumps(preprocessing_options) if preprocessing_options else None))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Document saved', 'id': doc_id})


@documents_bp.route('/<doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    """Get a specific document."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
        SELECT d.*, u.email as uploaded_by_email
        FROM documents d
        LEFT JOIN users u ON d.uploaded_by = u.id
        WHERE d.id = %s
    ''', (doc_id,))
    doc = cur.fetchone()

    if not doc:
        cur.close()
        conn.close()
        return jsonify({'error': 'Document not found'}), 404

    # Check access
    role = get_user_team_role(doc['team_id'], g.user['id'])
    if not can_view(role):
        cur.close()
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    cur.close()
    conn.close()

    return jsonify(doc)


@documents_bp.route('/<doc_id>', methods=['PUT'])
@login_required
def update_document(doc_id):
    """Update a document (move to folder, rename, update text)."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('SELECT team_id, uploaded_by FROM documents WHERE id = %s', (doc_id,))
    doc = cur.fetchone()

    if not doc:
        cur.close()
        conn.close()
        return jsonify({'error': 'Document not found'}), 404

    role = get_user_team_role(doc['team_id'], g.user['id'])
    if not can_edit(role):
        cur.close()
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json()
    updates = []
    params = []

    if 'filename' in data:
        updates.append('filename = %s')
        params.append(data['filename'])
    if 'ocr_text' in data:
        updates.append('ocr_text = %s')
        params.append(data['ocr_text'])
    if 'folder_id' in data:
        updates.append('folder_id = %s')
        params.append(data['folder_id'] if data['folder_id'] else None)

    if updates:
        updates.append('updated_at = %s')
        params.append(datetime.utcnow())
        params.append(doc_id)

        cur.execute(f'''
            UPDATE documents SET {', '.join(updates)} WHERE id = %s
        ''', params)
        conn.commit()

    cur.close()
    conn.close()

    return jsonify({'message': 'Document updated'})


@documents_bp.route('/<doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    """Delete a document."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('SELECT team_id, uploaded_by FROM documents WHERE id = %s', (doc_id,))
    doc = cur.fetchone()

    if not doc:
        cur.close()
        conn.close()
        return jsonify({'error': 'Document not found'}), 404

    role = get_user_team_role(doc['team_id'], g.user['id'])
    # Allow delete if admin/owner OR if user uploaded it
    if not can_admin(role) and doc['uploaded_by'] != g.user['id']:
        cur.close()
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    cur.execute('DELETE FROM documents WHERE id = %s', (doc_id,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Document deleted'})


# ============== Folders ==============

@documents_bp.route('/team/<team_id>/folders', methods=['GET'])
@login_required
def list_folders(team_id):
    """List folders in a team."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_view(role):
        return jsonify({'error': 'Not authorized'}), 403

    parent_id = request.args.get('parent_id')

    conn = get_connection()
    cur = conn.cursor()

    if parent_id:
        cur.execute('''
            SELECT f.*, u.email as created_by_email,
                   (SELECT COUNT(*) FROM documents WHERE folder_id = f.id) as document_count,
                   (SELECT COUNT(*) FROM folders WHERE parent_id = f.id) as subfolder_count
            FROM folders f
            LEFT JOIN users u ON f.created_by = u.id
            WHERE f.team_id = %s AND f.parent_id = %s
            ORDER BY f.name
        ''', (team_id, parent_id))
    else:
        cur.execute('''
            SELECT f.*, u.email as created_by_email,
                   (SELECT COUNT(*) FROM documents WHERE folder_id = f.id) as document_count,
                   (SELECT COUNT(*) FROM folders WHERE parent_id = f.id) as subfolder_count
            FROM folders f
            LEFT JOIN users u ON f.created_by = u.id
            WHERE f.team_id = %s AND f.parent_id IS NULL
            ORDER BY f.name
        ''', (team_id,))

    folders = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(folders)


@documents_bp.route('/team/<team_id>/folders', methods=['POST'])
@login_required
def create_folder(team_id):
    """Create a new folder."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_edit(role):
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json()
    name = data.get('name', '').strip()
    parent_id = data.get('parent_id')

    if not name:
        return jsonify({'error': 'Folder name is required'}), 400

    folder_id = str(uuid.uuid4())

    conn = get_connection()
    cur = conn.cursor()

    # Verify parent folder belongs to team if specified
    if parent_id:
        cur.execute('SELECT id FROM folders WHERE id = %s AND team_id = %s', (parent_id, team_id))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Parent folder not found'}), 404

    cur.execute('''
        INSERT INTO folders (id, team_id, parent_id, name, created_by)
        VALUES (%s, %s, %s, %s, %s)
    ''', (folder_id, team_id, parent_id, name, g.user['id']))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Folder created', 'id': folder_id})


@documents_bp.route('/folders/<folder_id>', methods=['PUT'])
@login_required
def update_folder(folder_id):
    """Rename or move a folder."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('SELECT team_id FROM folders WHERE id = %s', (folder_id,))
    folder = cur.fetchone()

    if not folder:
        cur.close()
        conn.close()
        return jsonify({'error': 'Folder not found'}), 404

    role = get_user_team_role(folder['team_id'], g.user['id'])
    if not can_edit(role):
        cur.close()
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json()
    updates = []
    params = []

    if 'name' in data:
        updates.append('name = %s')
        params.append(data['name'].strip())
    if 'parent_id' in data:
        # Prevent circular references
        if data['parent_id'] == folder_id:
            cur.close()
            conn.close()
            return jsonify({'error': 'Cannot move folder into itself'}), 400
        updates.append('parent_id = %s')
        params.append(data['parent_id'] if data['parent_id'] else None)

    if updates:
        params.append(folder_id)
        cur.execute(f'''
            UPDATE folders SET {', '.join(updates)} WHERE id = %s
        ''', params)
        conn.commit()

    cur.close()
    conn.close()

    return jsonify({'message': 'Folder updated'})


@documents_bp.route('/folders/<folder_id>', methods=['DELETE'])
@login_required
def delete_folder(folder_id):
    """Delete a folder (moves contents to parent or root)."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('SELECT team_id, parent_id FROM folders WHERE id = %s', (folder_id,))
    folder = cur.fetchone()

    if not folder:
        cur.close()
        conn.close()
        return jsonify({'error': 'Folder not found'}), 404

    role = get_user_team_role(folder['team_id'], g.user['id'])
    if not can_admin(role):
        cur.close()
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    # Move documents to parent folder (or root)
    cur.execute(
        'UPDATE documents SET folder_id = %s WHERE folder_id = %s',
        (folder['parent_id'], folder_id)
    )

    # Move subfolders to parent
    cur.execute(
        'UPDATE folders SET parent_id = %s WHERE parent_id = %s',
        (folder['parent_id'], folder_id)
    )

    # Delete the folder
    cur.execute('DELETE FROM folders WHERE id = %s', (folder_id,))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Folder deleted'})


# ============== Team Member Roles ==============

@documents_bp.route('/team/<team_id>/members/<user_id>/role', methods=['PUT'])
@login_required
def update_member_role(team_id, user_id):
    """Update a team member's role."""
    role = get_user_team_role(team_id, g.user['id'])
    if not can_admin(role):
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json()
    new_role = data.get('role')

    if new_role not in ('viewer', 'editor', 'admin'):
        return jsonify({'error': 'Invalid role. Must be viewer, editor, or admin'}), 400

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        'UPDATE team_members SET role = %s WHERE team_id = %s AND user_id = %s',
        (new_role, team_id, user_id)
    )

    if cur.rowcount == 0:
        cur.close()
        conn.close()
        return jsonify({'error': 'Member not found'}), 404

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Role updated'})
