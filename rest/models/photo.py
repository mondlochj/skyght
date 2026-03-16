from extensions import db
from datetime import datetime
import os


class Photo(db.Model):
    """Photo storage organized by business and type"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)

    # Type: menu_item, room, floor_plan, profile, etc.
    photo_type = db.Column(db.String(50), nullable=False)

    # Reference to the entity this photo belongs to
    entity_id = db.Column(db.Integer)  # e.g., menu_item.id, room.id

    # File info
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_extension = db.Column(db.String(10))
    file_size = db.Column(db.Integer)  # bytes
    mime_type = db.Column(db.String(100))

    # Image dimensions
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)

    # Organization
    display_order = db.Column(db.Integer, default=0)
    is_primary = db.Column(db.Boolean, default=False)

    # Metadata
    alt_text = db.Column(db.String(255))
    caption = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationships
    business = db.relationship('Business', backref='photos')

    @property
    def url(self):
        """Get the URL to access this photo"""
        return f'/uploads/{self.business_id}/{self.photo_type}/{self.filename}'

    @property
    def path(self):
        """Get the filesystem path to this photo"""
        from flask import current_app
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        return os.path.join(upload_folder, str(self.business_id), self.photo_type, self.filename)

    @property
    def thumbnail_url(self):
        """Get thumbnail URL (same as url for now, could add thumbnail generation)"""
        return self.url
