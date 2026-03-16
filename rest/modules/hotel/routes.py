from flask import Blueprint, render_template, g, abort, request, flash, redirect, url_for
from flask_login import login_required
from extensions import db
from models.room import HotelRoom
from models.booking import HotelBooking

hotel_bp = Blueprint('hotel', __name__, url_prefix='/hotel')


@hotel_bp.route('/rooms')
@login_required
def rooms():
    if not g.get('current_business'):
        abort(403)

    if g.current_business.business_type != 'hotel':
        abort(403)

    rooms = HotelRoom.query.filter_by(business_id=g.current_business.id).all()
    return render_template('hotel/rooms.html', rooms=rooms)


@hotel_bp.route('/rooms/add', methods=['GET', 'POST'])
@login_required
def add_room():
    if not g.get('current_business') or g.current_business.business_type != 'hotel':
        abort(403)

    if request.method == 'POST':
        room = HotelRoom(
            business_id=g.current_business.id,
            room_name=request.form.get('room_name'),
            capacity=int(request.form.get('capacity', 2)),
            price_per_night=float(request.form.get('price', 0)),
            status='available'
        )
        db.session.add(room)
        db.session.commit()
        flash('Habitacion agregada.', 'success')
        return redirect(url_for('hotel.rooms'))

    return render_template('hotel/add_room.html')


@hotel_bp.route('/bookings')
@login_required
def bookings():
    if not g.get('current_business'):
        abort(403)

    if g.current_business.business_type != 'hotel':
        abort(403)

    bookings = HotelBooking.query.join(HotelRoom)\
        .filter(HotelRoom.business_id == g.current_business.id)\
        .order_by(HotelBooking.check_in.desc())\
        .all()

    return render_template('hotel/bookings.html', bookings=bookings)
