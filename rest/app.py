from flask import Flask, g, redirect, url_for, request
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from extensions import db, login_manager, mail
from config import Config
from models.user import User
from models.admin import Admin
from models.menu import MenuCategory, MenuItem
from models.floor_plan import FloorPlan, RestaurantTable
from models.order import Order, OrderItem
from models.bill import Bill, Payment
from models.photo import Photo
from models.waitlist import WaitlistEntry, WaitlistSettings
import os


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Handle reverse proxy headers (x_prefix handles X-Forwarded-Prefix for SCRIPT_NAME)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Register blueprints
    from modules.auth.routes import auth_bp
    from modules.onboarding.routes import onboarding_bp
    from modules.dashboard.routes import dashboard_bp
    from modules.crm.routes import crm_bp
    from modules.reservations.routes import reservations_bp
    from modules.hotel.routes import hotel_bp
    from modules.jobs.routes import jobs_bp
    from modules.whatsapp.routes import whatsapp_bp
    from modules.admin.routes import admin_bp
    from modules.restaurant.routes import restaurant_bp
    from modules.uploads.routes import uploads_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(onboarding_bp, url_prefix='/onboarding')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(crm_bp, url_prefix='/customers')
    app.register_blueprint(reservations_bp, url_prefix='/reservations')
    app.register_blueprint(hotel_bp, url_prefix='/hotel')
    app.register_blueprint(jobs_bp, url_prefix='/jobs')
    app.register_blueprint(whatsapp_bp, url_prefix='/webhook')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(restaurant_bp, url_prefix='/restaurant')
    app.register_blueprint(uploads_bp, url_prefix='/uploads')

    # Multi-tenant context
    @app.before_request
    def load_business_context():
        g.current_business = None
        g.current_role = None
        if current_user.is_authenticated:
            membership = current_user.memberships.first()
            if membership:
                g.current_business = membership.business
                g.current_role = membership.role

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    # Create tables on first run
    with app.app_context():
        db.create_all()

    return app


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


app = create_app()


@app.cli.command('create-admin')
def create_admin():
    """Create an admin account."""
    import click
    username = click.prompt('Username', default='admin')
    email = click.prompt('Email', default='admin@example.com')
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)

    with app.app_context():
        existing = Admin.query.filter(
            (Admin.username == username) | (Admin.email == email)
        ).first()
        if existing:
            click.echo('Error: Admin with that username or email already exists.')
            return

        admin = Admin(username=username, email=email, is_superadmin=True, is_active=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f'Admin "{username}" created successfully.')

if __name__ == '__main__':
    app.run(debug=True)
