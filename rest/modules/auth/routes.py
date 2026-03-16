from flask import Blueprint, render_template, redirect, url_for, flash, request, g, abort, current_app
from flask_login import login_user, logout_user, current_user, login_required
from .forms import LoginForm, RegisterForm
from .services import create_user, create_invite, send_invite_email
from .decorators import owner_required
from models.user import User
from models.business import Business
from models.membership import Membership
from models.role import Role
from extensions import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Public registration disabled - users must be invited by admin or business owner
    flash('El registro publico esta deshabilitado. Contacta a tu administrador para obtener acceso.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/invite', methods=['GET', 'POST'])
@owner_required
def invite():
    if request.method == 'POST':
        email = request.form.get('email')
        role_name = request.form.get('role', 'staff')

        if not email:
            flash("Email requerido.", "danger")
            return render_template('users/invite.html')

        # Create token/link
        token, link = create_invite(g.current_business.id, email, role_name)

        # Try to send real email
        try:
            send_invite_email(email, link, g.current_business.business_name)
            flash(f"Invitacion enviada correctamente a {email}", "success")
        except Exception as e:
            flash(f"No se pudo enviar email. Enlace de invitacion: {link}", "warning")
            current_app.logger.error(f"Email send failed: {e}")

    roles = Role.query.all()
    return render_template('users/invite.html', roles=roles)


@auth_bp.route('/invite/accept', methods=['GET', 'POST'])
def accept_invite():
    email = request.args.get('email')
    business_id = request.args.get('business')
    role_name = request.args.get('role')
    token = request.args.get('token')

    if not all([email, business_id, role_name]):
        flash("Enlace invalido.", "danger")
        return redirect(url_for('auth.login'))

    business = Business.query.get(business_id)
    if not business:
        abort(404)

    user = User.query.filter_by(email=email).first()

    # If user doesn't exist, show registration form
    if not user:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '')
            password2 = request.form.get('password2', '')

            if not name or len(name) < 2:
                flash("El nombre debe tener al menos 2 caracteres.", "danger")
            elif not password or len(password) < 6:
                flash("La contrasena debe tener al menos 6 caracteres.", "danger")
            elif password != password2:
                flash("Las contrasenas no coinciden.", "danger")
            else:
                user, error = create_user(name=name, email=email, password=password)
                if error:
                    flash(error, "danger")
                else:
                    # Continue to add membership below
                    pass

        if not user:
            return render_template('invite_register.html',
                                   email=email,
                                   business=business,
                                   business_id=business_id,
                                   role_name=role_name,
                                   token=token)

    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.commit()

    existing = Membership.query.filter_by(user_id=user.id, business_id=business.id).first()
    if existing:
        flash("Ya eres miembro de este negocio.", "info")
    else:
        mem = Membership(user_id=user.id, business_id=business.id, role_id=role.id)
        db.session.add(mem)
        db.session.commit()
        flash("Te has unido al equipo!", "success")

    login_user(user)
    return redirect(url_for('dashboard.index'))
