from extensions import db
from datetime import datetime
import json


class Bill(db.Model):
    """Bill/check for an order or table"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    table_id = db.Column(db.Integer, db.ForeignKey('restaurant_table.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))

    # Bill identification
    bill_number = db.Column(db.String(20), nullable=False)

    # Amounts
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=12.00)  # IVA default 12%
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    discount_reason = db.Column(db.String(200))
    tip_amount = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), default=0)

    # Payment
    # Status: open, partial, paid, void
    status = db.Column(db.String(20), default='open')
    paid_amount = db.Column(db.Numeric(10, 2), default=0)

    # Split bill info (JSON array of split amounts)
    split_data = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    voided_at = db.Column(db.DateTime)

    # Staff
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    voided_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    void_reason = db.Column(db.String(200))

    # Relationships
    business = db.relationship('Business', backref='bills')
    order = db.relationship('Order', backref='bills')
    table = db.relationship('RestaurantTable', backref='bills')
    customer = db.relationship('Customer', backref='bills')
    payments = db.relationship('Payment', back_populates='bill', lazy='dynamic')

    def calculate_totals(self):
        """Recalculate bill totals from order"""
        if self.order:
            self.subtotal = self.order.subtotal or 0

        subtotal = float(self.subtotal or 0)
        tax_rate = float(self.tax_rate if self.tax_rate is not None else 12.0)
        discount = float(self.discount_amount or 0)
        tip = float(self.tip_amount or 0)

        self.tax_amount = subtotal * (tax_rate / 100)
        self.total = subtotal + float(self.tax_amount) - discount + tip

    @property
    def balance_due(self):
        """Amount still owed"""
        return float(self.total or 0) - float(self.paid_amount or 0)

    @property
    def is_paid(self):
        return self.status == 'paid' or self.balance_due <= 0

    def get_split_data(self):
        if self.split_data:
            return json.loads(self.split_data)
        return []

    def set_split_data(self, data):
        self.split_data = json.dumps(data)


class Payment(db.Model):
    """Payment record for a bill"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)

    # Payment details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    # Method: cash, card, transfer, other
    payment_method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(100))  # Card last 4, transfer ref, etc.

    # For split payments by seat
    seat_number = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    received_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationships
    bill = db.relationship('Bill', back_populates='payments')
    business = db.relationship('Business', backref='payments')
