from flask import Blueprint, render_template, redirect, url_for, flash, request, session, make_response
from functools import wraps
from extensions import db
from models.admin import Admin
from models.business import Business
from models.user import User
from models.customer import Customer
from models.membership import Membership
from models.role import Role
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get('admin_id')
        if not admin_id:
            flash('Acceso denegado. Inicia sesion como administrador.', 'danger')
            return redirect(url_for('admin.login'))
        admin = Admin.query.get(admin_id)
        if not admin or not admin.is_active:
            session.pop('admin_id', None)
            flash('Sesion invalida.', 'danger')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_id'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password) and admin.is_active:
            session.permanent = True
            session['admin_id'] = admin.id
            admin.last_login = datetime.utcnow()
            db.session.commit()
            flash('Bienvenido al panel de administracion.', 'success')
            return redirect(url_for('admin.dashboard'), code=303)
        flash('Credenciales invalidas.', 'danger')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    flash('Sesion cerrada.', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@admin_required
def dashboard():
    stats = {
        'total_businesses': Business.query.count(),
        'total_users': User.query.count(),
        'total_customers': Customer.query.count(),
        'businesses_by_type': {
            'restaurant': Business.query.filter_by(business_type='restaurant').count(),
            'hotel': Business.query.filter_by(business_type='hotel').count(),
            'service': Business.query.filter_by(business_type='service').count(),
        }
    }
    recent_businesses = Business.query.order_by(Business.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    return render_template('admin/dashboard.html', stats=stats,
                          recent_businesses=recent_businesses,
                          recent_users=recent_users)


@admin_bp.route('/businesses')
@admin_required
def businesses():
    businesses = Business.query.order_by(Business.created_at.desc()).all()
    return render_template('admin/businesses.html', businesses=businesses)


@admin_bp.route('/businesses/create', methods=['GET', 'POST'])
@admin_required
def create_business():
    if request.method == 'POST':
        # Business info
        business_name = request.form.get('business_name', '').strip()
        business_type = request.form.get('business_type')
        phone = request.form.get('phone', '').strip()

        # Owner info
        owner_option = request.form.get('owner_option')  # 'new' or 'existing'
        owner_id = None

        if not business_name:
            flash('El nombre del negocio es requerido.', 'danger')
            return render_template('admin/create_business.html', users=User.query.all())

        if business_type not in ['restaurant', 'hotel', 'service']:
            flash('Tipo de negocio invalido.', 'danger')
            return render_template('admin/create_business.html', users=User.query.all())

        if owner_option == 'new':
            owner_name = request.form.get('owner_name', '').strip()
            owner_email = request.form.get('owner_email', '').strip()
            owner_password = request.form.get('owner_password', '')

            if not all([owner_name, owner_email, owner_password]):
                flash('Todos los campos del propietario son requeridos.', 'danger')
                return render_template('admin/create_business.html', users=User.query.all())

            if len(owner_password) < 6:
                flash('La contrasena debe tener al menos 6 caracteres.', 'danger')
                return render_template('admin/create_business.html', users=User.query.all())

            if User.query.filter_by(email=owner_email).first():
                flash('Ya existe un usuario con ese email.', 'danger')
                return render_template('admin/create_business.html', users=User.query.all())

            # Create new user
            owner = User(name=owner_name, email=owner_email)
            owner.set_password(owner_password)
            db.session.add(owner)
            db.session.flush()
            owner_id = owner.id

        elif owner_option == 'existing':
            owner_id = request.form.get('existing_owner_id')
            if not owner_id:
                flash('Selecciona un propietario existente.', 'danger')
                return render_template('admin/create_business.html', users=User.query.all())
            owner_id = int(owner_id)

        # Create business
        business = Business(
            business_name=business_name,
            business_type=business_type,
            owner_id=owner_id,
            phone=phone,
            timezone='America/Guatemala'
        )
        db.session.add(business)
        db.session.flush()

        # Create owner role if not exists
        owner_role = Role.query.filter_by(name='owner').first()
        if not owner_role:
            owner_role = Role(name='owner', permissions_json={'all': True})
            db.session.add(owner_role)
            db.session.flush()

        # Create membership
        if owner_id:
            membership = Membership(
                user_id=owner_id,
                business_id=business.id,
                role_id=owner_role.id
            )
            db.session.add(membership)

        db.session.commit()
        flash(f'Negocio "{business_name}" creado exitosamente.', 'success')
        return redirect(url_for('admin.businesses'))

    users = User.query.order_by(User.name).all()
    return render_template('admin/create_business.html', users=users)


@admin_bp.route('/businesses/<int:business_id>')
@admin_required
def business_detail(business_id):
    business = Business.query.get_or_404(business_id)
    members = Membership.query.filter_by(business_id=business_id).all()
    customers = Customer.query.filter_by(business_id=business_id).count()
    return render_template('admin/business_detail.html', business=business,
                          members=members, customer_count=customers)


@admin_bp.route('/businesses/<int:business_id>/toggle', methods=['POST'])
@admin_required
def toggle_business(business_id):
    business = Business.query.get_or_404(business_id)
    # Toggle plan between 'free' and 'suspended'
    if business.plan == 'suspended':
        business.plan = 'free'
        flash(f'Negocio {business.business_name} activado.', 'success')
    else:
        business.plan = 'suspended'
        flash(f'Negocio {business.business_name} suspendido.', 'warning')
    db.session.commit()
    return redirect(url_for('admin.businesses'))


@admin_bp.route('/users')
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    memberships = Membership.query.filter_by(user_id=user_id).all()
    return render_template('admin/user_detail.html', user=user, memberships=memberships)


@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    admin = Admin.query.get(session.get('admin_id'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_password':
            current = request.form.get('current_password')
            new_pass = request.form.get('new_password')
            confirm = request.form.get('confirm_password')

            if not admin.check_password(current):
                flash('Contrasena actual incorrecta.', 'danger')
            elif new_pass != confirm:
                flash('Las contrasenas no coinciden.', 'danger')
            elif len(new_pass) < 6:
                flash('La contrasena debe tener al menos 6 caracteres.', 'danger')
            else:
                admin.set_password(new_pass)
                db.session.commit()
                flash('Contrasena actualizada.', 'success')

        elif action == 'create_admin' and admin.is_superadmin:
            username = request.form.get('new_username')
            email = request.form.get('new_email')
            password = request.form.get('new_admin_password')

            if Admin.query.filter_by(username=username).first():
                flash('El usuario ya existe.', 'danger')
            elif Admin.query.filter_by(email=email).first():
                flash('El email ya existe.', 'danger')
            else:
                new_admin = Admin(username=username, email=email)
                new_admin.set_password(password)
                db.session.add(new_admin)
                db.session.commit()
                flash(f'Administrador {username} creado.', 'success')

    admins = Admin.query.all() if admin.is_superadmin else []
    return render_template('admin/settings.html', admin=admin, admins=admins)
