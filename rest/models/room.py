from extensions import db
from datetime import datetime


class HotelRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    room_name = db.Column(db.String(50), nullable=False)
    capacity = db.Column(db.Integer, default=2)
    status = db.Column(db.String(20), default='available')  # available, occupied, maintenance
    price_per_night = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    business = db.relationship('Business')
    bookings = db.relationship('HotelBooking', backref='room', lazy=True)
