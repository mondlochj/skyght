from extensions import db
from datetime import datetime
import secrets
import json


class WaitlistEntry(db.Model):
    __tablename__ = 'waitlist_entry'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)

    # Contact info
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))

    # Party details
    party_size = db.Column(db.Integer, default=2)
    high_chairs_needed = db.Column(db.Integer, default=0)
    wheelchair_accessible = db.Column(db.Boolean, default=False)
    seating_preference = db.Column(db.String(50))  # indoor, outdoor, booth, table, window, quiet
    special_occasion = db.Column(db.String(50))  # birthday, anniversary, none
    notes = db.Column(db.Text)

    # Status and queue
    status = db.Column(db.String(20), default='waiting')  # waiting, notified, seated, no_show, cancelled
    queue_position = db.Column(db.Integer)
    vip_priority = db.Column(db.Boolean, default=False)

    # Timestamps
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)
    quoted_wait_minutes = db.Column(db.Integer)
    notified_at = db.Column(db.DateTime)
    seated_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)

    # Seating info
    table_id = db.Column(db.Integer, db.ForeignKey('restaurant_table.id'), nullable=True)

    # Source tracking
    source = db.Column(db.String(20), default='host')  # host, whatsapp, qr_code
    confirmation_token = db.Column(db.String(64), unique=True)

    # No-show tracking
    no_show_count = db.Column(db.Integer, default=0)  # Historical count for this phone/email

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    business = db.relationship('Business')
    customer = db.relationship('Customer')
    table = db.relationship('RestaurantTable')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.confirmation_token:
            self.confirmation_token = secrets.token_urlsafe(32)

    @property
    def wait_time_minutes(self):
        """Calculate actual wait time from check-in to now or seated time"""
        if not self.check_in_time:
            return 0
        if self.seated_at:
            delta = self.seated_at - self.check_in_time
        else:
            delta = datetime.utcnow() - self.check_in_time
        return int(delta.total_seconds() / 60)

    @property
    def is_overdue(self):
        """Check if wait time exceeds quoted time"""
        if self.quoted_wait_minutes and self.status == 'waiting':
            return self.wait_time_minutes > self.quoted_wait_minutes
        return False

    @property
    def time_until_ready(self):
        """Estimated minutes until table ready"""
        if self.quoted_wait_minutes:
            remaining = self.quoted_wait_minutes - self.wait_time_minutes
            return max(0, remaining)
        return None

    def mark_notified(self):
        """Mark as notified (table ready)"""
        self.status = 'notified'
        self.notified_at = datetime.utcnow()

    def mark_seated(self, table_id=None):
        """Mark as seated"""
        self.status = 'seated'
        self.seated_at = datetime.utcnow()
        if table_id:
            self.table_id = table_id

    def mark_no_show(self):
        """Mark as no-show"""
        self.status = 'no_show'
        self.no_show_count += 1

    def mark_cancelled(self):
        """Mark as cancelled"""
        self.status = 'cancelled'
        self.cancelled_at = datetime.utcnow()

    def to_dict(self):
        """Convert to dictionary for JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'party_size': self.party_size,
            'high_chairs_needed': self.high_chairs_needed,
            'wheelchair_accessible': self.wheelchair_accessible,
            'seating_preference': self.seating_preference,
            'special_occasion': self.special_occasion,
            'notes': self.notes,
            'status': self.status,
            'queue_position': self.queue_position,
            'vip_priority': self.vip_priority,
            'check_in_time': self.check_in_time.isoformat() if self.check_in_time else None,
            'quoted_wait_minutes': self.quoted_wait_minutes,
            'wait_time_minutes': self.wait_time_minutes,
            'is_overdue': self.is_overdue,
            'time_until_ready': self.time_until_ready,
            'source': self.source,
            'token': self.confirmation_token
        }


class WaitlistSettings(db.Model):
    """Per-business waitlist configuration"""
    __tablename__ = 'waitlist_settings'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False, unique=True)

    # Auto-calculation settings
    avg_table_turnover_minutes = db.Column(db.Integer, default=45)
    buffer_minutes_per_party = db.Column(db.Integer, default=5)

    # Notification settings
    notify_via_whatsapp = db.Column(db.Boolean, default=True)
    notify_via_sms = db.Column(db.Boolean, default=False)
    notification_message = db.Column(db.Text, default="Hi {name}! Your table for {party_size} is ready at {restaurant}. Please check in with the host within 10 minutes.")

    # Self-service settings
    allow_self_checkin = db.Column(db.Boolean, default=True)
    max_party_size_self_checkin = db.Column(db.Integer, default=8)
    require_phone_self_checkin = db.Column(db.Boolean, default=True)

    # Display settings
    show_queue_position = db.Column(db.Boolean, default=True)
    show_estimated_wait = db.Column(db.Boolean, default=True)

    business = db.relationship('Business')

    @classmethod
    def get_or_create(cls, business_id):
        """Get settings for business, creating defaults if needed"""
        settings = cls.query.filter_by(business_id=business_id).first()
        if not settings:
            settings = cls(business_id=business_id)
            db.session.add(settings)
            db.session.commit()
        return settings
