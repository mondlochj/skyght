from extensions import db
from datetime import datetime


class MenuCategory(db.Model):
    """Menu category (e.g., Appetizers, Main Course, Drinks)"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    business = db.relationship('Business', backref='menu_categories')
    items = db.relationship('MenuItem', back_populates='category', lazy='dynamic',
                           order_by='MenuItem.display_order')


class MenuItem(db.Model):
    """Individual menu item"""
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('menu_category.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_url = db.Column(db.String(500))  # Legacy field, prefer using photos
    display_order = db.Column(db.Integer, default=0)
    is_available = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    preparation_time = db.Column(db.Integer)  # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('MenuCategory', back_populates='items')
    business = db.relationship('Business', backref='menu_items')

    @property
    def primary_photo(self):
        """Get the primary photo for this menu item"""
        from models.photo import Photo
        photo = Photo.query.filter_by(
            business_id=self.business_id,
            photo_type='menu_item',
            entity_id=self.id,
            is_primary=True
        ).first()
        if not photo:
            photo = Photo.query.filter_by(
                business_id=self.business_id,
                photo_type='menu_item',
                entity_id=self.id
            ).first()
        return photo

    @property
    def photo_url(self):
        """Get the URL for the primary photo, falling back to image_url"""
        photo = self.primary_photo
        if photo:
            return photo.url
        return self.image_url

    def get_photos(self):
        """Get all photos for this menu item"""
        from models.photo import Photo
        return Photo.query.filter_by(
            business_id=self.business_id,
            photo_type='menu_item',
            entity_id=self.id
        ).order_by(Photo.is_primary.desc(), Photo.display_order).all()
