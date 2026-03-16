from flask import Blueprint, send_from_directory, current_app, jsonify, request, g, abort
from flask_login import login_required, current_user
from utils.photos import save_photo, delete_photo, get_photos
from models.photo import Photo
import os

uploads_bp = Blueprint('uploads', __name__)


@uploads_bp.route('/<int:business_id>/<photo_type>/<filename>')
def serve_photo(business_id, photo_type, filename):
    """Serve uploaded photos"""
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    directory = os.path.join(upload_folder, str(business_id), photo_type)

    if not os.path.exists(os.path.join(directory, filename)):
        abort(404)

    return send_from_directory(directory, filename)


@uploads_bp.route('/upload', methods=['POST'])
@login_required
def upload_photo():
    """Upload a photo (AJAX endpoint)"""
    if not g.current_business:
        return jsonify({'error': 'No business context'}), 403

    if 'photo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['photo']
    photo_type = request.form.get('photo_type', 'general')
    entity_id = request.form.get('entity_id')
    is_primary = request.form.get('is_primary', 'false').lower() == 'true'

    if entity_id:
        entity_id = int(entity_id)

    photo = save_photo(
        file=file,
        business_id=g.current_business.id,
        photo_type=photo_type,
        entity_id=entity_id,
        user_id=current_user.id,
        is_primary=is_primary
    )

    if not photo:
        return jsonify({'error': 'Failed to upload photo. Check file type and size.'}), 400

    return jsonify({
        'success': True,
        'photo': {
            'id': photo.id,
            'url': photo.url,
            'filename': photo.filename,
            'is_primary': photo.is_primary
        }
    })


@uploads_bp.route('/delete/<int:photo_id>', methods=['POST'])
@login_required
def delete_photo_route(photo_id):
    """Delete a photo"""
    if not g.current_business:
        return jsonify({'error': 'No business context'}), 403

    success = delete_photo(photo_id, g.current_business.id)

    if not success:
        return jsonify({'error': 'Photo not found'}), 404

    return jsonify({'success': True})


@uploads_bp.route('/list/<photo_type>')
@login_required
def list_photos(photo_type):
    """List photos for current business by type"""
    if not g.current_business:
        return jsonify({'error': 'No business context'}), 403

    entity_id = request.args.get('entity_id')
    if entity_id:
        entity_id = int(entity_id)

    photos = get_photos(g.current_business.id, photo_type, entity_id)

    return jsonify({
        'photos': [{
            'id': p.id,
            'url': p.url,
            'filename': p.filename,
            'is_primary': p.is_primary,
            'width': p.width,
            'height': p.height
        } for p in photos]
    })


@uploads_bp.route('/set-primary/<int:photo_id>', methods=['POST'])
@login_required
def set_primary_photo(photo_id):
    """Set a photo as primary"""
    if not g.current_business:
        return jsonify({'error': 'No business context'}), 403

    photo = Photo.query.filter_by(
        id=photo_id,
        business_id=g.current_business.id
    ).first()

    if not photo:
        return jsonify({'error': 'Photo not found'}), 404

    # Unset other primaries for same entity
    Photo.query.filter_by(
        business_id=g.current_business.id,
        photo_type=photo.photo_type,
        entity_id=photo.entity_id,
        is_primary=True
    ).update({'is_primary': False})

    photo.is_primary = True

    from extensions import db
    db.session.commit()

    return jsonify({'success': True})
