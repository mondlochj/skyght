from extensions import db
from datetime import datetime


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    service_type = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255))
    scheduled_time = db.Column(db.DateTime)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='pending')  # pending, assigned, in_progress, completed, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    business = db.relationship('Business')
    customer = db.relationship('Customer')
    technician = db.relationship('User')
