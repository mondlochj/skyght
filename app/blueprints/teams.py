from flask import Blueprint, request, jsonify, g
import uuid
import secrets
from db import get_connection
from auth_utils import login_required
from email_utils import send_team_invitation

teams_bp = Blueprint('teams', __name__, url_prefix='/api/teams')


def is_team_owner(team_id, user_id):
    """Check if user is the owner of a team."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT owner_id FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    cur.close()
    conn.close()
    return team and team['owner_id'] == user_id


def is_team_member(team_id, user_id):
    """Check if user is a member of a team (includes owner)."""
    conn = get_connection()
    cur = conn.cursor()
    # Check if owner
    cur.execute('SELECT owner_id FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    if team and team['owner_id'] == user_id:
        cur.close()
        conn.close()
        return True
    # Check if member
    cur.execute('SELECT id FROM team_members WHERE team_id = %s AND user_id = %s', (team_id, user_id))
    member = cur.fetchone()
    cur.close()
    conn.close()
    return member is not None


@teams_bp.route('', methods=['POST'])
@login_required
def create_team():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Team name is required'}), 400

    team_id = str(uuid.uuid4())

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO teams(id, name, owner_id) VALUES(%s, %s, %s)',
        (team_id, name, g.user['id'])
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Team created', 'team_id': team_id})


@teams_bp.route('', methods=['GET'])
@login_required
def list_teams():
    conn = get_connection()
    cur = conn.cursor()

    # Get teams where user is owner
    cur.execute('''
        SELECT t.*, 'owner' as membership_role,
               (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) as member_count
        FROM teams t
        WHERE t.owner_id = %s
    ''', (g.user['id'],))
    owned_teams = cur.fetchall()

    # Get teams where user is a member
    cur.execute('''
        SELECT t.*, tm.role as membership_role,
               (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) as member_count
        FROM teams t
        JOIN team_members tm ON t.id = tm.team_id
        WHERE tm.user_id = %s
    ''', (g.user['id'],))
    member_teams = cur.fetchall()

    cur.close()
    conn.close()

    all_teams = owned_teams + member_teams
    return jsonify(all_teams)


@teams_bp.route('/<team_id>', methods=['GET'])
@login_required
def get_team(team_id):
    if not is_team_member(team_id, g.user['id']):
        return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    cur.close()
    conn.close()

    if not team:
        return jsonify({'error': 'Team not found'}), 404

    return jsonify(team)


@teams_bp.route('/<team_id>', methods=['DELETE'])
@login_required
def delete_team(team_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM teams WHERE id = %s AND owner_id = %s',
        (team_id, g.user['id'])
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Team not found or not authorized'}), 404

    return jsonify({'message': 'Team deleted'})


# ============== Team Members ==============

@teams_bp.route('/<team_id>/members', methods=['GET'])
@login_required
def list_members(team_id):
    if not is_team_member(team_id, g.user['id']):
        return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()

    # Get owner
    cur.execute('''
        SELECT u.id, u.email, 'owner' as role, t.created_at as joined_at
        FROM teams t
        JOIN users u ON t.owner_id = u.id
        WHERE t.id = %s
    ''', (team_id,))
    owner = cur.fetchone()

    # Get members
    cur.execute('''
        SELECT u.id, u.email, tm.role, tm.joined_at
        FROM team_members tm
        JOIN users u ON tm.user_id = u.id
        WHERE tm.team_id = %s
    ''', (team_id,))
    members = cur.fetchall()

    cur.close()
    conn.close()

    all_members = [owner] + members if owner else members
    return jsonify(all_members)


@teams_bp.route('/<team_id>/members/<user_id>', methods=['DELETE'])
@login_required
def remove_member(team_id, user_id):
    # Only owner can remove members
    if not is_team_owner(team_id, g.user['id']):
        # Members can remove themselves
        if user_id != g.user['id']:
            return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM team_members WHERE team_id = %s AND user_id = %s',
        (team_id, user_id)
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Member not found'}), 404

    return jsonify({'message': 'Member removed'})


# ============== Invitations ==============

@teams_bp.route('/<team_id>/invite', methods=['POST'])
@login_required
def invite_member(team_id):
    if not is_team_owner(team_id, g.user['id']):
        return jsonify({'error': 'Only team owner can invite members'}), 403

    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    conn = get_connection()
    cur = conn.cursor()

    # Get team info
    cur.execute('SELECT name FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    if not team:
        cur.close()
        conn.close()
        return jsonify({'error': 'Team not found'}), 404

    # Check if user is already a member
    cur.execute('SELECT id FROM users WHERE email = %s', (email,))
    existing_user = cur.fetchone()
    if existing_user:
        cur.execute(
            'SELECT id FROM team_members WHERE team_id = %s AND user_id = %s',
            (team_id, existing_user['id'])
        )
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'User is already a team member'}), 400

        # Check if user is the owner
        cur.execute('SELECT owner_id FROM teams WHERE id = %s', (team_id,))
        team_data = cur.fetchone()
        if team_data and team_data['owner_id'] == existing_user['id']:
            cur.close()
            conn.close()
            return jsonify({'error': 'Cannot invite the team owner'}), 400

    # Check for existing pending invitation
    cur.execute('''
        SELECT id FROM team_invitations
        WHERE team_id = %s AND email = %s AND status = 'pending' AND expires_at > NOW()
    ''', (team_id, email))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'error': 'An invitation is already pending for this email'}), 400

    # Create invitation
    invite_id = str(uuid.uuid4())
    invite_token = secrets.token_urlsafe(32)

    cur.execute('''
        INSERT INTO team_invitations (id, team_id, email, invited_by, token)
        VALUES (%s, %s, %s, %s, %s)
    ''', (invite_id, team_id, email, g.user['id'], invite_token))
    conn.commit()

    # Get inviter email
    cur.execute('SELECT email FROM users WHERE id = %s', (g.user['id'],))
    inviter = cur.fetchone()
    inviter_email = inviter['email'] if inviter else 'A team member'

    cur.close()
    conn.close()

    # Send invitation email
    email_sent = send_team_invitation(email, team['name'], inviter_email, invite_token)

    if email_sent:
        return jsonify({'message': 'Invitation sent successfully'})
    else:
        return jsonify({'message': 'Invitation created but email could not be sent', 'warning': True})


@teams_bp.route('/<team_id>/invitations', methods=['GET'])
@login_required
def list_invitations(team_id):
    if not is_team_owner(team_id, g.user['id']):
        return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT ti.id, ti.email, ti.status, ti.created_at, ti.expires_at,
               u.email as invited_by_email
        FROM team_invitations ti
        JOIN users u ON ti.invited_by = u.id
        WHERE ti.team_id = %s
        ORDER BY ti.created_at DESC
    ''', (team_id,))
    invitations = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(invitations)


@teams_bp.route('/<team_id>/invitations/<invite_id>', methods=['DELETE'])
@login_required
def cancel_invitation(team_id, invite_id):
    if not is_team_owner(team_id, g.user['id']):
        return jsonify({'error': 'Not authorized'}), 403

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM team_invitations WHERE id = %s AND team_id = %s',
        (invite_id, team_id)
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Invitation not found'}), 404

    return jsonify({'message': 'Invitation cancelled'})


# ============== User Invitations (for accepting) ==============

@teams_bp.route('/invitations/pending', methods=['GET'])
@login_required
def my_pending_invitations():
    """Get pending invitations for the current user."""
    conn = get_connection()
    cur = conn.cursor()

    # Get user email
    cur.execute('SELECT email FROM users WHERE id = %s', (g.user['id'],))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify([])

    cur.execute('''
        SELECT ti.id, ti.token, t.name as team_name, u.email as invited_by,
               ti.created_at, ti.expires_at
        FROM team_invitations ti
        JOIN teams t ON ti.team_id = t.id
        JOIN users u ON ti.invited_by = u.id
        WHERE ti.email = %s AND ti.status = 'pending' AND ti.expires_at > NOW()
    ''', (user['email'],))
    invitations = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(invitations)


@teams_bp.route('/invitations/accept', methods=['POST'])
@login_required
def accept_invitation():
    """Accept an invitation by token."""
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({'error': 'Token is required'}), 400

    conn = get_connection()
    cur = conn.cursor()

    # Get user email
    cur.execute('SELECT email FROM users WHERE id = %s', (g.user['id'],))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    # Find the invitation
    cur.execute('''
        SELECT ti.id, ti.team_id, ti.email
        FROM team_invitations ti
        WHERE ti.token = %s AND ti.status = 'pending' AND ti.expires_at > NOW()
    ''', (token,))
    invitation = cur.fetchone()

    if not invitation:
        cur.close()
        conn.close()
        return jsonify({'error': 'Invalid or expired invitation'}), 404

    # Verify email matches
    if invitation['email'].lower() != user['email'].lower():
        cur.close()
        conn.close()
        return jsonify({'error': 'This invitation was sent to a different email address'}), 403

    # Add user to team
    member_id = str(uuid.uuid4())
    try:
        cur.execute('''
            INSERT INTO team_members (id, team_id, user_id, role)
            VALUES (%s, %s, %s, 'member')
        ''', (member_id, invitation['team_id'], g.user['id']))

        # Update invitation status
        cur.execute(
            "UPDATE team_invitations SET status = 'accepted' WHERE id = %s",
            (invitation['id'],)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'You are already a member of this team'}), 400

    cur.close()
    conn.close()

    return jsonify({'message': 'Invitation accepted! You are now a team member.'})


@teams_bp.route('/invitations/decline', methods=['POST'])
@login_required
def decline_invitation():
    """Decline an invitation by token."""
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({'error': 'Token is required'}), 400

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE team_invitations SET status = 'declined' WHERE token = %s AND status = 'pending'",
        (token,)
    )
    updated = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if updated == 0:
        return jsonify({'error': 'Invitation not found or already processed'}), 404

    return jsonify({'message': 'Invitation declined'})


@teams_bp.route('/invitations/check/<token>', methods=['GET'])
def check_invitation(token):
    """Check if an invitation token is valid (public endpoint)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT ti.email, t.name as team_name, u.email as invited_by,
               ti.status, ti.expires_at
        FROM team_invitations ti
        JOIN teams t ON ti.team_id = t.id
        JOIN users u ON ti.invited_by = u.id
        WHERE ti.token = %s
    ''', (token,))
    invitation = cur.fetchone()
    cur.close()
    conn.close()

    if not invitation:
        return jsonify({'error': 'Invitation not found'}), 404

    if invitation['status'] != 'pending':
        return jsonify({'error': f"Invitation has already been {invitation['status']}"}), 400

    from datetime import datetime
    if invitation['expires_at'] < datetime.now():
        return jsonify({'error': 'Invitation has expired'}), 400

    return jsonify({
        'email': invitation['email'],
        'team_name': invitation['team_name'],
        'invited_by': invitation['invited_by']
    })
