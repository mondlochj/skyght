from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from extensions import db
from models.business import Business
from models.membership import Membership
from models.role import Role
from models.room import HotelRoom

onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')


@onboarding_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # Check if user already has a business
    membership = current_user.memberships.first()
    if membership:
        flash('Ya tienes un negocio configurado.', 'info')
        return redirect(url_for('dashboard.index'))

    step = request.args.get('step', 'basic')

    if request.method == 'POST':
        if step == 'basic':
            business_name = request.form.get('business_name')
            business_type = request.form.get('business_type')
            phone = request.form.get('phone')

            if not all([business_name, business_type, phone]):
                flash('Todos los campos son requeridos.', 'danger')
                return render_template('onboarding.html')

            if business_type not in ['restaurant', 'hotel', 'service']:
                flash('Tipo de negocio invalido.', 'danger')
                return render_template('onboarding.html')

            # Create business
            business = Business(
                business_name=business_name,
                business_type=business_type,
                owner_id=current_user.id,
                phone=phone,
                timezone='America/Guatemala'
            )
            db.session.add(business)
            db.session.flush()  # get ID

            # Create default owner role
            owner_role = Role.query.filter_by(name='owner').first()
            if not owner_role:
                owner_role = Role(name='owner', permissions_json={'all': True})
                db.session.add(owner_role)
                db.session.flush()

            # Link user to business as owner
            membership = Membership(
                user_id=current_user.id,
                business_id=business.id,
                role_id=owner_role.id
            )
            db.session.add(membership)
            db.session.commit()

            flash('Negocio creado. Ahora configura los detalles iniciales.', 'success')
            return redirect(url_for('onboarding.setup'))

    return render_template('onboarding.html')


@onboarding_bp.route('/setup', methods=['GET', 'POST'])
@login_required
def setup():
    membership = current_user.memberships.first()
    if not membership:
        return redirect(url_for('onboarding.index'))

    business = membership.business

    if request.method == 'POST':
        bt = business.business_type

        if bt == 'restaurant':
            try:
                num_tables = int(request.form.get('num_tables', 0))
                # For a proper restaurant, you'd create a Table model
                # For MVP, we just acknowledge
                flash(f"{num_tables} mesas configuradas.", "success")
            except ValueError:
                flash("Numero invalido de mesas.", "danger")
                return render_template('onboarding_setup.html', business=business)

        elif bt == 'hotel':
            try:
                num_rooms = int(request.form.get('num_rooms', 0))
                for i in range(1, num_rooms + 1):
                    room = HotelRoom(
                        business_id=business.id,
                        room_name=f"Habitacion {i}",
                        capacity=2,
                        status='available'
                    )
                    db.session.add(room)
                db.session.commit()
                flash(f"{num_rooms} habitaciones creadas.", "success")
            except ValueError:
                flash("Numero invalido de habitaciones.", "danger")
                return render_template('onboarding_setup.html', business=business)

        elif bt == 'service':
            flash("Servicio configurado. Puedes crear ordenes de trabajo.", "info")

        return redirect(url_for('dashboard.index'))

    return render_template('onboarding_setup.html', business=business)
