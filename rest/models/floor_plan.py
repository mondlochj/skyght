from extensions import db
from datetime import datetime
import json


class FloorPlan(db.Model):
    """Restaurant floor plan - represents a room/area"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False, default='Salon Principal')

    # Canvas dimensions (in pixels)
    canvas_width = db.Column(db.Integer, default=1000)
    canvas_height = db.Column(db.Integer, default=800)

    # Scale: pixels per meter (e.g., 100 means 100px = 1 meter)
    scale = db.Column(db.Float, default=50.0)  # 50px = 1 meter by default

    # Room polygon data (JSON array of polygons, each with points)
    room_data = db.Column(db.Text)

    # Visual settings
    background_color = db.Column(db.String(20), default='#f5f5f5')
    wall_color = db.Column(db.String(20), default='#374151')
    floor_color = db.Column(db.String(20), default='#ffffff')

    # Display order for multiple rooms
    display_order = db.Column(db.Integer, default=0)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = db.relationship('Business', backref='floor_plans')
    tables = db.relationship('RestaurantTable', back_populates='floor_plan', lazy='dynamic')

    def get_room_data(self):
        """Parse room data JSON"""
        if self.room_data:
            return json.loads(self.room_data)
        return []

    def set_room_data(self, data):
        """Set room data as JSON"""
        self.room_data = json.dumps(data)

    def pixels_to_meters(self, pixels):
        """Convert pixels to meters"""
        return pixels / self.scale

    def meters_to_pixels(self, meters):
        """Convert meters to pixels"""
        return meters * self.scale

    def pixels_to_cm(self, pixels):
        """Convert pixels to centimeters"""
        return (pixels / self.scale) * 100


class RestaurantTable(db.Model):
    """Restaurant table with position and properties"""
    id = db.Column(db.Integer, primary_key=True)
    floor_plan_id = db.Column(db.Integer, db.ForeignKey('floor_plan.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    table_number = db.Column(db.String(20), nullable=False)
    label = db.Column(db.String(50))  # Optional label like "VIP", "Terraza", etc.

    # Position on canvas
    x = db.Column(db.Float, default=0)
    y = db.Column(db.Float, default=0)
    rotation = db.Column(db.Float, default=0)  # degrees

    # Shape: circle, square, rectangle
    shape = db.Column(db.String(20), default='rectangle')
    width = db.Column(db.Float, default=80)
    height = db.Column(db.Float, default=60)

    # Table properties
    capacity = db.Column(db.Integer, default=4)
    min_capacity = db.Column(db.Integer, default=1)

    # Place settings data (JSON array of seat positions)
    seats_data = db.Column(db.Text)

    # Status: available, occupied, reserved, dirty, inactive
    status = db.Column(db.String(20), default='available')

    # Visual customization
    color = db.Column(db.String(20), default='#8B4513')
    label_color = db.Column(db.String(20), default='#ffffff')

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    floor_plan = db.relationship('FloorPlan', back_populates='tables')
    business = db.relationship('Business', backref='restaurant_tables')

    def get_seats_data(self):
        """Parse seats data JSON"""
        if self.seats_data:
            return json.loads(self.seats_data)
        # Default seats around the table
        return self._generate_default_seats()

    def set_seats_data(self, data):
        """Set seats data as JSON"""
        self.seats_data = json.dumps(data)

    def _generate_default_seats(self):
        """Generate default seat positions based on capacity and shape"""
        seats = []
        if self.shape == 'circle':
            import math
            for i in range(self.capacity):
                angle = (2 * math.pi * i) / self.capacity
                seats.append({
                    'x': math.cos(angle) * (self.width / 2 + 15),
                    'y': math.sin(angle) * (self.height / 2 + 15),
                    'occupied': False
                })
        else:
            # Rectangle/square - distribute seats on sides
            per_side = max(1, self.capacity // 4)
            remainder = self.capacity % 4
            # Simplified: just track seat count
            for i in range(self.capacity):
                seats.append({'index': i, 'occupied': False})
        return seats

    @property
    def status_color(self):
        """Return color based on status"""
        colors = {
            'available': '#10b981',
            'occupied': '#ef4444',
            'reserved': '#f59e0b',
            'dirty': '#6b7280',
            'inactive': '#374151'
        }
        return colors.get(self.status, '#6b7280')
