from extensions import db
from datetime import datetime


class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(150), nullable=False)
    business_type = db.Column(db.String(20), nullable=False)  # restaurant, hotel, service
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    plan = db.Column(db.String(20), default='free')
    phone = db.Column(db.String(20))
    timezone = db.Column(db.String(50), default='America/Guatemala')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship('User', backref='owned_businesses')
    memberships = db.relationship('Membership', back_populates='business', lazy='dynamic')
