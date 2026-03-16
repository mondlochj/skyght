from extensions import db


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # owner, manager, staff, cleaner, technician
    permissions_json = db.Column(db.JSON, default=dict)  # e.g. {"can_create_reservation": true, ...}
