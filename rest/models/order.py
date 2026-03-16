from extensions import db
from datetime import datetime


class Order(db.Model):
    """Restaurant order linked to a table"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('restaurant_table.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))

    # Order identification
    order_number = db.Column(db.String(20), nullable=False)

    # Status: pending, preparing, ready, served, completed, cancelled
    status = db.Column(db.String(20), default='pending')

    # Order type: dine_in, takeout, delivery
    order_type = db.Column(db.String(20), default='dine_in')

    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)  # When kitchen started preparing
    ready_at = db.Column(db.DateTime)    # When ready to serve
    served_at = db.Column(db.DateTime)   # When served to customer
    completed_at = db.Column(db.DateTime)

    # Staff
    server_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Notes
    notes = db.Column(db.Text)
    guests_count = db.Column(db.Integer, default=1)

    # Relationships
    business = db.relationship('Business', backref='orders')
    table = db.relationship('RestaurantTable', backref='orders')
    customer = db.relationship('Customer', backref='orders')
    server = db.relationship('User', backref='served_orders')
    items = db.relationship('OrderItem', back_populates='order', lazy='dynamic')

    @property
    def subtotal(self):
        """Calculate order subtotal"""
        return sum(item.total for item in self.items)

    @property
    def status_color(self):
        colors = {
            'pending': '#f59e0b',
            'preparing': '#3b82f6',
            'ready': '#10b981',
            'served': '#8b5cf6',
            'completed': '#6b7280',
            'cancelled': '#ef4444'
        }
        return colors.get(self.status, '#6b7280')


class OrderItem(db.Model):
    """Individual item in an order"""
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)

    # Quantity and pricing
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)  # Price at time of order

    # Status: pending, preparing, ready, served, cancelled
    status = db.Column(db.String(20), default='pending')

    # Customizations
    notes = db.Column(db.Text)  # Special instructions
    modifiers = db.Column(db.Text)  # JSON: extra toppings, substitutions, etc.

    # Seat assignment (for split bills)
    seat_number = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    order = db.relationship('Order', back_populates='items')
    menu_item = db.relationship('MenuItem', backref='order_items')

    @property
    def total(self):
        """Calculate item total"""
        return float(self.unit_price) * self.quantity

    @property
    def item_name(self):
        return self.menu_item.name if self.menu_item else 'Unknown Item'
