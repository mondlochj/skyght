import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
from flask import current_app
from extensions import db
from models.photo import Photo

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMBNAIL_SIZE = (300, 300)
MAX_IMAGE_SIZE = (1920, 1920)  # Max dimensions for full image


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_folder(business_id, photo_type):
    """Get the upload folder path for a business and type"""
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    folder = os.path.join(upload_folder, str(business_id), photo_type)
    os.makedirs(folder, exist_ok=True)
    return folder


def generate_unique_filename(original_filename):
    """Generate a unique filename while preserving extension"""
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    return unique_name


def resize_image(image_path, max_size=MAX_IMAGE_SIZE):
    """Resize image if it exceeds max dimensions"""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Only resize if larger than max
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                img.save(image_path, quality=85, optimize=True)

            return img.width, img.height
    except Exception as e:
        current_app.logger.error(f"Error resizing image: {e}")
        return None, None


def save_photo(file, business_id, photo_type, entity_id=None, user_id=None, is_primary=False):
    """
    Save an uploaded photo file and create database record.

    Args:
        file: werkzeug FileStorage object
        business_id: ID of the business
        photo_type: Type of photo (menu_item, room, floor_plan, etc.)
        entity_id: Optional ID of the related entity
        user_id: ID of the user uploading
        is_primary: Whether this is the primary photo

    Returns:
        Photo object or None if failed
    """
    if not file or not file.filename:
        return None

    if not allowed_file(file.filename):
        return None

    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return None

    # Generate unique filename
    original_filename = secure_filename(file.filename)
    filename = generate_unique_filename(original_filename)
    ext = filename.rsplit('.', 1)[1].lower()

    # Get upload folder and save file
    folder = get_upload_folder(business_id, photo_type)
    filepath = os.path.join(folder, filename)
    file.save(filepath)

    # Resize if needed and get dimensions
    width, height = resize_image(filepath)

    # Get mime type
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }

    # If setting as primary, unset other primaries
    if is_primary and entity_id:
        Photo.query.filter_by(
            business_id=business_id,
            photo_type=photo_type,
            entity_id=entity_id,
            is_primary=True
        ).update({'is_primary': False})

    # Create database record
    photo = Photo(
        business_id=business_id,
        photo_type=photo_type,
        entity_id=entity_id,
        filename=filename,
        original_filename=original_filename,
        file_extension=ext,
        file_size=file_size,
        mime_type=mime_types.get(ext, 'application/octet-stream'),
        width=width,
        height=height,
        is_primary=is_primary,
        created_by=user_id
    )

    db.session.add(photo)
    db.session.commit()

    return photo


def delete_photo(photo_id, business_id):
    """
    Delete a photo file and database record.

    Args:
        photo_id: ID of the photo
        business_id: ID of the business (for security check)

    Returns:
        True if deleted, False otherwise
    """
    photo = Photo.query.filter_by(id=photo_id, business_id=business_id).first()
    if not photo:
        return False

    # Delete file
    try:
        if os.path.exists(photo.path):
            os.remove(photo.path)
    except Exception as e:
        current_app.logger.error(f"Error deleting photo file: {e}")

    # Delete database record
    db.session.delete(photo)
    db.session.commit()

    return True


def get_photos(business_id, photo_type, entity_id=None):
    """
    Get photos for a business/type/entity.

    Returns:
        List of Photo objects
    """
    query = Photo.query.filter_by(
        business_id=business_id,
        photo_type=photo_type
    )

    if entity_id:
        query = query.filter_by(entity_id=entity_id)

    return query.order_by(Photo.is_primary.desc(), Photo.display_order).all()


def get_primary_photo(business_id, photo_type, entity_id):
    """Get the primary photo for an entity"""
    photo = Photo.query.filter_by(
        business_id=business_id,
        photo_type=photo_type,
        entity_id=entity_id,
        is_primary=True
    ).first()

    if not photo:
        # Fall back to first photo
        photo = Photo.query.filter_by(
            business_id=business_id,
            photo_type=photo_type,
            entity_id=entity_id
        ).first()

    return photo
