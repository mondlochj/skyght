from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from flask_login import login_required
from extensions import db
from models.reservation import RestaurantReservation
from models.booking import HotelBooking
from models.job import Job
from models.room import HotelRoom
from models.customer import Customer

reservations_bp = Blueprint('reservations', __name__, url_prefix='/reservations')


@reservations_bp.route('/')
@login_required
def list():
    if not g.get('current_business'):
        abort(403)

    bt = g.current_business.business_type
    items = []

    if bt == 'restaurant':
        items = RestaurantReservation.query.filter_by(business_id=g.current_business.id)\
            .order_by(RestaurantReservation.reservation_date.desc())\
            .all()
        return render_template('reservations/list_restaurant.html', items=items)

    elif bt == 'hotel':
        items = HotelBooking.query.join(HotelRoom)\
            .filter(HotelRoom.business_id == g.current_business.id)\
            .order_by(HotelBooking.check_in.desc())\
            .all()
        return render_template('reservations/list_hotel.html', items=items)

    elif bt == 'service':
        items = Job.query.filter_by(business_id=g.current_business.id)\
            .order_by(Job.scheduled_time.desc())\
            .all()
        return render_template('reservations/list_jobs.html', items=items)

    return render_template('reservations/index.html', items=items, business_type=bt)


@reservations_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    if not g.get('current_business'):
        flash("No tienes un negocio configurado.", "danger")
        return redirect(url_for('dashboard.index'))

    bt = g.current_business.business_type
    customers = Customer.query.filter_by(business_id=g.current_business.id).all()

    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        customer = Customer.query.get(customer_id) if customer_id else None

        if bt == 'restaurant':
            res = RestaurantReservation(
                business_id=g.current_business.id,
                customer_id=customer.id if customer else None,
                reservation_date=request.form.get('date'),
                reservation_time=request.form.get('time'),
                party_size=int(request.form.get('party_size', 2)),
                status='pending',
                notes=request.form.get('notes', '')
            )
            db.session.add(res)
            flash("Reservacion creada.", "success")

        elif bt == 'hotel':
            room_id = request.form.get('room_id')
            room = HotelRoom.query.get(room_id)
            if room and room.business_id == g.current_business.id:
                booking = HotelBooking(
                    room_id=room.id,
                    customer_id=customer.id if customer else None,
                    check_in=request.form.get('check_in'),
                    check_out=request.form.get('check_out'),
                    status='pending'
                )
                db.session.add(booking)
                flash("Reserva de habitacion creada.", "success")

        elif bt == 'service':
            job = Job(
                business_id=g.current_business.id,
                customer_id=customer.id if customer else None,
                service_type=request.form.get('service_type'),
                address=request.form.get('address'),
                scheduled_time=request.form.get('scheduled_time'),
                status='pending'
            )
            db.session.add(job)
            flash("Trabajo/servicio creado.", "success")

        db.session.commit()
        return redirect(url_for('reservations.list'))

    rooms = []
    if bt == 'hotel':
        rooms = HotelRoom.query.filter_by(business_id=g.current_business.id).all()

    return render_template('reservations/create.html',
                           business_type=bt,
                           customers=customers,
                           rooms=rooms)
