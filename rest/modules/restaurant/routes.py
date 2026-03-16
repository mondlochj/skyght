from flask import Blueprint, render_template, redirect, url_for, flash, request, g, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.menu import MenuCategory, MenuItem
from models.floor_plan import FloorPlan, RestaurantTable
from models.order import Order, OrderItem
from models.bill import Bill, Payment
from models.photo import Photo
from modules.auth.decorators import owner_required, permission_required
from utils.photos import save_photo, get_photos, get_primary_photo
from datetime import datetime
import json

restaurant_bp = Blueprint('restaurant', __name__)


def restaurant_required(f):
    """Decorator to ensure business is a restaurant"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not g.current_business or g.current_business.business_type != 'restaurant':
            flash('Esta funcion solo esta disponible para restaurantes.', 'warning')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


# ============== MENU MANAGEMENT ==============

@restaurant_bp.route('/menu')
@restaurant_required
def menu():
    """Display menu with categories and items"""
    categories = MenuCategory.query.filter_by(
        business_id=g.current_business.id,
        is_active=True
    ).order_by(MenuCategory.display_order).all()
    return render_template('restaurant/menu.html', categories=categories)


@restaurant_bp.route('/menu/category/new', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def new_category():
    """Create new menu category"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('El nombre es requerido.', 'danger')
            return render_template('restaurant/category_form.html')

        max_order = db.session.query(db.func.max(MenuCategory.display_order)).filter_by(
            business_id=g.current_business.id
        ).scalar() or 0

        category = MenuCategory(
            business_id=g.current_business.id,
            name=name,
            description=description,
            display_order=max_order + 1
        )
        db.session.add(category)
        db.session.commit()
        flash(f'Categoria "{name}" creada.', 'success')
        return redirect(url_for('restaurant.menu'))

    return render_template('restaurant/category_form.html')


@restaurant_bp.route('/menu/category/<int:cat_id>/edit', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def edit_category(cat_id):
    """Edit menu category"""
    category = MenuCategory.query.filter_by(
        id=cat_id, business_id=g.current_business.id
    ).first_or_404()

    if request.method == 'POST':
        category.name = request.form.get('name', '').strip()
        category.description = request.form.get('description', '').strip()
        db.session.commit()
        flash('Categoria actualizada.', 'success')
        return redirect(url_for('restaurant.menu'))

    return render_template('restaurant/category_form.html', category=category)


@restaurant_bp.route('/menu/category/<int:cat_id>/delete', methods=['POST'])
@restaurant_required
@owner_required
def delete_category(cat_id):
    """Delete menu category"""
    category = MenuCategory.query.filter_by(
        id=cat_id, business_id=g.current_business.id
    ).first_or_404()

    # Soft delete - just deactivate
    category.is_active = False
    for item in category.items:
        item.is_active = False
    db.session.commit()
    flash('Categoria eliminada.', 'success')
    return redirect(url_for('restaurant.menu'))


@restaurant_bp.route('/menu/item/new', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def new_item():
    """Create new menu item"""
    categories = MenuCategory.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id')
        price = request.form.get('price', '0')
        description = request.form.get('description', '').strip()

        if not name or not category_id or not price:
            flash('Nombre, categoria y precio son requeridos.', 'danger')
            return render_template('restaurant/item_form.html', categories=categories)

        try:
            price = float(price)
        except ValueError:
            flash('Precio invalido.', 'danger')
            return render_template('restaurant/item_form.html', categories=categories)

        item = MenuItem(
            business_id=g.current_business.id,
            category_id=int(category_id),
            name=name,
            description=description,
            price=price
        )
        db.session.add(item)
        db.session.flush()  # Get the ID

        # Handle photo upload
        if 'photo' in request.files and request.files['photo'].filename:
            photo = save_photo(
                file=request.files['photo'],
                business_id=g.current_business.id,
                photo_type='menu_item',
                entity_id=item.id,
                user_id=current_user.id,
                is_primary=True
            )
            if photo:
                item.image_url = photo.url

        db.session.commit()
        flash(f'Producto "{name}" creado.', 'success')
        return redirect(url_for('restaurant.menu'))

    return render_template('restaurant/item_form.html', categories=categories)


@restaurant_bp.route('/menu/item/<int:item_id>/edit', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def edit_item(item_id):
    """Edit menu item"""
    item = MenuItem.query.filter_by(
        id=item_id, business_id=g.current_business.id
    ).first_or_404()

    categories = MenuCategory.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).all()

    photos = get_photos(g.current_business.id, 'menu_item', item.id)

    if request.method == 'POST':
        item.name = request.form.get('name', '').strip()
        item.category_id = int(request.form.get('category_id'))
        item.description = request.form.get('description', '').strip()
        item.price = float(request.form.get('price', '0'))
        item.is_available = request.form.get('is_available') == 'on'

        # Handle photo upload
        if 'photo' in request.files and request.files['photo'].filename:
            photo = save_photo(
                file=request.files['photo'],
                business_id=g.current_business.id,
                photo_type='menu_item',
                entity_id=item.id,
                user_id=current_user.id,
                is_primary=True
            )
            if photo:
                item.image_url = photo.url

        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('restaurant.menu'))

    return render_template('restaurant/item_form.html', item=item, categories=categories, photos=photos)


@restaurant_bp.route('/menu/item/<int:item_id>/toggle', methods=['POST'])
@restaurant_required
def toggle_item_availability(item_id):
    """Toggle item availability"""
    item = MenuItem.query.filter_by(
        id=item_id, business_id=g.current_business.id
    ).first_or_404()
    item.is_available = not item.is_available
    db.session.commit()
    return jsonify({'available': item.is_available})


# ============== FLOOR PLAN EDITOR ==============

@restaurant_bp.route('/floor-plan')
@restaurant_bp.route('/floor-plan/<int:room_id>')
@restaurant_required
def floor_plan_view(room_id=None):
    """Display floor plan operations view"""
    rooms = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).order_by(FloorPlan.display_order).all()

    if not rooms:
        return redirect(url_for('restaurant.floor_plan_edit'))

    if room_id:
        plan = FloorPlan.query.filter_by(
            id=room_id, business_id=g.current_business.id, is_active=True
        ).first_or_404()
    else:
        plan = rooms[0]

    tables_query = RestaurantTable.query.filter_by(
        floor_plan_id=plan.id, is_active=True
    ).all()

    tables = [{
        'id': t.id,
        'table_number': t.table_number,
        'label': t.label or '',
        'x': t.x,
        'y': t.y,
        'width': t.width,
        'height': t.height,
        'shape': t.shape,
        'capacity': t.capacity,
        'color': t.color,
        'status': t.status,
        'rotation': t.rotation or 0,
        'seats': t.get_seats_data()
    } for t in tables_query]

    return render_template('restaurant/floor_plan_view.html', plan=plan, tables=tables, rooms=rooms)


@restaurant_bp.route('/floor-plan/edit')
@restaurant_bp.route('/floor-plan/edit/<int:room_id>')
@restaurant_required
def floor_plan_edit(room_id=None):
    """Display floor plan editor"""
    # Get all rooms for this business
    rooms = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).order_by(FloorPlan.display_order).all()

    if not rooms:
        # Create default room
        plan = FloorPlan(
            business_id=g.current_business.id,
            name='Salon Principal',
            scale=50.0
        )
        db.session.add(plan)
        db.session.commit()
        rooms = [plan]

    # Select specific room or first one
    if room_id:
        plan = FloorPlan.query.filter_by(
            id=room_id, business_id=g.current_business.id, is_active=True
        ).first_or_404()
    else:
        plan = rooms[0]

    tables_query = RestaurantTable.query.filter_by(
        floor_plan_id=plan.id, is_active=True
    ).all()

    # Serialize tables for JSON in template
    tables = [{
        'id': t.id,
        'table_number': t.table_number,
        'label': t.label or '',
        'x': t.x,
        'y': t.y,
        'width': t.width,
        'height': t.height,
        'shape': t.shape,
        'capacity': t.capacity,
        'color': t.color,
        'status': t.status,
        'rotation': t.rotation or 0,
        'seats_data': t.get_seats_data()
    } for t in tables_query]

    return render_template('restaurant/floor_plan.html', plan=plan, tables=tables, rooms=rooms)


@restaurant_bp.route('/rooms')
@restaurant_required
def manage_rooms():
    """Manage restaurant rooms/areas"""
    rooms = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).order_by(FloorPlan.display_order).all()

    return render_template('restaurant/rooms.html', rooms=rooms)


@restaurant_bp.route('/rooms/new', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def new_room():
    """Create new room"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        width = int(request.form.get('width', 1000))
        height = int(request.form.get('height', 800))
        scale = float(request.form.get('scale', 50))

        if not name:
            flash('El nombre es requerido.', 'danger')
            return render_template('restaurant/room_form.html')

        max_order = db.session.query(db.func.max(FloorPlan.display_order)).filter_by(
            business_id=g.current_business.id
        ).scalar() or 0

        room = FloorPlan(
            business_id=g.current_business.id,
            name=name,
            canvas_width=width,
            canvas_height=height,
            scale=scale,
            display_order=max_order + 1
        )
        db.session.add(room)
        db.session.commit()

        flash(f'Sala "{name}" creada.', 'success')
        return redirect(url_for('restaurant.floor_plan_edit', room_id=room.id))

    return render_template('restaurant/room_form.html')


@restaurant_bp.route('/rooms/<int:room_id>/edit', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def edit_room(room_id):
    """Edit room"""
    room = FloorPlan.query.filter_by(
        id=room_id, business_id=g.current_business.id
    ).first_or_404()

    if request.method == 'POST':
        room.name = request.form.get('name', '').strip()
        room.canvas_width = int(request.form.get('width', 1000))
        room.canvas_height = int(request.form.get('height', 800))
        room.scale = float(request.form.get('scale', 50))
        db.session.commit()

        flash('Sala actualizada.', 'success')
        return redirect(url_for('restaurant.manage_rooms'))

    return render_template('restaurant/room_form.html', room=room)


@restaurant_bp.route('/rooms/<int:room_id>/delete', methods=['POST'])
@restaurant_required
@owner_required
def delete_room(room_id):
    """Delete room"""
    room = FloorPlan.query.filter_by(
        id=room_id, business_id=g.current_business.id
    ).first_or_404()

    # Check if this is the last room
    count = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).count()

    if count <= 1:
        flash('No puedes eliminar la ultima sala.', 'danger')
        return redirect(url_for('restaurant.manage_rooms'))

    room.is_active = False
    # Also deactivate tables in this room
    RestaurantTable.query.filter_by(floor_plan_id=room.id).update({'is_active': False})
    db.session.commit()

    flash('Sala eliminada.', 'success')
    return redirect(url_for('restaurant.manage_rooms'))


@restaurant_bp.route('/floor-plan/save', methods=['POST'])
@restaurant_required
@owner_required
def save_floor_plan():
    """Save floor plan data (AJAX)"""
    data = request.get_json()

    plan_id = data.get('plan_id')
    if plan_id:
        plan = FloorPlan.query.filter_by(
            id=plan_id, business_id=g.current_business.id, is_active=True
        ).first()
    else:
        plan = FloorPlan.query.filter_by(
            business_id=g.current_business.id, is_active=True
        ).first()

    if not plan:
        return jsonify({'error': 'Floor plan not found'}), 404

    # Save scale
    if 'scale' in data:
        plan.scale = float(data['scale'])

    # Save room polygons
    if 'room_data' in data:
        plan.set_room_data(data['room_data'])

    if 'canvas_width' in data:
        plan.canvas_width = data['canvas_width']
    if 'canvas_height' in data:
        plan.canvas_height = data['canvas_height']

    # Save tables
    if 'tables' in data:
        for table_data in data['tables']:
            if table_data.get('id'):
                # Update existing table
                table = RestaurantTable.query.get(table_data['id'])
                if table and table.business_id == g.current_business.id:
                    table.x = table_data.get('x', table.x)
                    table.y = table_data.get('y', table.y)
                    table.width = table_data.get('width', table.width)
                    table.height = table_data.get('height', table.height)
                    table.rotation = table_data.get('rotation', table.rotation)
                    table.shape = table_data.get('shape', table.shape)
                    table.capacity = table_data.get('capacity', table.capacity)
                    table.color = table_data.get('color', table.color)
                    table.label = table_data.get('label', table.label)
                    if 'seats' in table_data:
                        table.set_seats_data(table_data['seats'])
            else:
                # Create new table
                table = RestaurantTable(
                    floor_plan_id=plan.id,
                    business_id=g.current_business.id,
                    table_number=table_data.get('table_number', f'T{RestaurantTable.query.filter_by(floor_plan_id=plan.id).count() + 1}'),
                    x=table_data.get('x', 100),
                    y=table_data.get('y', 100),
                    width=table_data.get('width', 80),
                    height=table_data.get('height', 60),
                    rotation=table_data.get('rotation', 0),
                    shape=table_data.get('shape', 'rectangle'),
                    capacity=table_data.get('capacity', 4),
                    color=table_data.get('color', '#8B4513'),
                    label=table_data.get('label', '')
                )
                if 'seats' in table_data:
                    table.set_seats_data(table_data['seats'])
                db.session.add(table)

    db.session.commit()
    return jsonify({'success': True})


@restaurant_bp.route('/floor-plan/table/add', methods=['POST'])
@restaurant_required
@owner_required
def add_table():
    """Add a new table to floor plan"""
    data = request.get_json()

    plan = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).first()

    if not plan:
        return jsonify({'error': 'Floor plan not found'}), 404

    # Get next table number
    count = RestaurantTable.query.filter_by(floor_plan_id=plan.id).count()

    table = RestaurantTable(
        floor_plan_id=plan.id,
        business_id=g.current_business.id,
        table_number=data.get('table_number', f'{count + 1}'),
        x=data.get('x', 100),
        y=data.get('y', 100),
        width=data.get('width', 80),
        height=data.get('height', 60),
        shape=data.get('shape', 'rectangle'),
        capacity=data.get('capacity', 4),
        color=data.get('color', '#8B4513')
    )
    db.session.add(table)
    db.session.commit()

    return jsonify({
        'success': True,
        'table': {
            'id': table.id,
            'table_number': table.table_number,
            'x': table.x,
            'y': table.y,
            'width': table.width,
            'height': table.height,
            'shape': table.shape,
            'capacity': table.capacity,
            'color': table.color,
            'status': table.status
        }
    })


@restaurant_bp.route('/floor-plan/table/<int:table_id>/delete', methods=['POST'])
@restaurant_required
@owner_required
def delete_table(table_id):
    """Delete a table"""
    table = RestaurantTable.query.filter_by(
        id=table_id, business_id=g.current_business.id
    ).first_or_404()
    table.is_active = False
    db.session.commit()
    return jsonify({'success': True})


@restaurant_bp.route('/floor-plan/table/<int:table_id>/status', methods=['POST'])
@restaurant_required
def update_floor_table_status(table_id):
    """Update table status from floor plan view"""
    table = RestaurantTable.query.filter_by(
        id=table_id, business_id=g.current_business.id
    ).first_or_404()

    data = request.get_json()
    if 'status' in data:
        table.status = data['status']
    if 'seats' in data:
        table.set_seats_data(data['seats'])
        # Update capacity to match number of seats
        table.capacity = len(data['seats'])

    db.session.commit()
    return jsonify({'success': True, 'capacity': table.capacity})


# ============== TABLE MANAGEMENT ==============

@restaurant_bp.route('/tables')
@restaurant_required
def tables():
    """Display table list and status"""
    plan = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).first()

    tables = []
    if plan:
        tables = RestaurantTable.query.filter_by(
            floor_plan_id=plan.id, is_active=True
        ).order_by(RestaurantTable.table_number).all()

    return render_template('restaurant/tables.html', tables=tables)


@restaurant_bp.route('/tables/<int:table_id>/status', methods=['POST'])
@restaurant_required
def update_table_status(table_id):
    """Update table status"""
    table = RestaurantTable.query.filter_by(
        id=table_id, business_id=g.current_business.id
    ).first_or_404()

    new_status = request.form.get('status') or request.json.get('status')
    if new_status in ['available', 'occupied', 'reserved', 'dirty', 'inactive']:
        table.status = new_status
        db.session.commit()

        if request.is_json:
            return jsonify({'success': True, 'status': table.status})
        flash(f'Mesa {table.table_number} actualizada.', 'success')

    return redirect(url_for('restaurant.tables'))


# ============== ORDER MANAGEMENT ==============

@restaurant_bp.route('/orders')
@restaurant_required
def orders():
    """Display active orders"""
    active_orders = Order.query.filter(
        Order.business_id == g.current_business.id,
        Order.status.in_(['pending', 'preparing', 'ready', 'served'])
    ).order_by(Order.created_at.desc()).all()

    return render_template('restaurant/orders.html', orders=active_orders)


@restaurant_bp.route('/orders/new', methods=['GET', 'POST'])
@restaurant_required
def new_order():
    """Create new order"""
    plan = FloorPlan.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).first()

    tables = []
    if plan:
        tables = RestaurantTable.query.filter_by(
            floor_plan_id=plan.id, is_active=True
        ).filter(RestaurantTable.status.in_(['available', 'occupied'])).all()

    categories = MenuCategory.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).order_by(MenuCategory.display_order).all()

    if request.method == 'POST':
        table_id = request.form.get('table_id')
        guests = request.form.get('guests_count', 1)

        # Generate order number
        today = datetime.now().strftime('%Y%m%d')
        count = Order.query.filter(
            Order.business_id == g.current_business.id,
            Order.order_number.like(f'{today}%')
        ).count()
        order_number = f'{today}{count + 1:04d}'

        order = Order(
            business_id=g.current_business.id,
            table_id=int(table_id) if table_id else None,
            order_number=order_number,
            guests_count=int(guests),
            server_id=current_user.id
        )
        db.session.add(order)

        # Update table status
        if table_id:
            table = RestaurantTable.query.get(int(table_id))
            if table:
                table.status = 'occupied'

        db.session.commit()
        return redirect(url_for('restaurant.edit_order', order_id=order.id))

    return render_template('restaurant/order_form.html', tables=tables, categories=categories)


@restaurant_bp.route('/orders/<int:order_id>')
@restaurant_required
def view_order(order_id):
    """View order details"""
    order = Order.query.filter_by(
        id=order_id, business_id=g.current_business.id
    ).first_or_404()
    return render_template('restaurant/order_detail.html', order=order)


@restaurant_bp.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@restaurant_required
def edit_order(order_id):
    """Edit order - add/remove items"""
    order = Order.query.filter_by(
        id=order_id, business_id=g.current_business.id
    ).first_or_404()

    categories = MenuCategory.query.filter_by(
        business_id=g.current_business.id, is_active=True
    ).order_by(MenuCategory.display_order).all()

    return render_template('restaurant/order_edit.html', order=order, categories=categories)


@restaurant_bp.route('/orders/<int:order_id>/add-item', methods=['POST'])
@restaurant_required
def add_order_item(order_id):
    """Add item to order (AJAX)"""
    order = Order.query.filter_by(
        id=order_id, business_id=g.current_business.id
    ).first_or_404()

    data = request.get_json()
    menu_item = MenuItem.query.get(data.get('menu_item_id'))

    if not menu_item or menu_item.business_id != g.current_business.id:
        return jsonify({'error': 'Item not found'}), 404

    item = OrderItem(
        order_id=order.id,
        menu_item_id=menu_item.id,
        quantity=data.get('quantity', 1),
        unit_price=menu_item.price,
        notes=data.get('notes', '')
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({
        'success': True,
        'item': {
            'id': item.id,
            'name': menu_item.name,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total': item.total
        },
        'order_subtotal': float(order.subtotal)
    })


@restaurant_bp.route('/orders/<int:order_id>/remove-item/<int:item_id>', methods=['POST'])
@restaurant_required
def remove_order_item(order_id, item_id):
    """Remove item from order"""
    item = OrderItem.query.filter_by(id=item_id, order_id=order_id).first_or_404()
    db.session.delete(item)
    db.session.commit()

    order = Order.query.get(order_id)
    return jsonify({
        'success': True,
        'order_subtotal': float(order.subtotal)
    })


@restaurant_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@restaurant_required
def update_order_status(order_id):
    """Update order status"""
    order = Order.query.filter_by(
        id=order_id, business_id=g.current_business.id
    ).first_or_404()

    new_status = request.form.get('status') or request.json.get('status')

    if new_status in ['pending', 'preparing', 'ready', 'served', 'completed', 'cancelled']:
        order.status = new_status

        if new_status == 'preparing':
            order.started_at = datetime.utcnow()
        elif new_status == 'ready':
            order.ready_at = datetime.utcnow()
        elif new_status == 'served':
            order.served_at = datetime.utcnow()
        elif new_status == 'completed':
            order.completed_at = datetime.utcnow()
            if order.table:
                order.table.status = 'dirty'

        db.session.commit()

        if request.is_json:
            return jsonify({'success': True, 'status': order.status})
        flash('Estado actualizado.', 'success')

    return redirect(url_for('restaurant.orders'))


@restaurant_bp.route('/kitchen')
@restaurant_required
def kitchen_display():
    """Kitchen display - show pending and preparing orders"""
    orders = Order.query.filter(
        Order.business_id == g.current_business.id,
        Order.status.in_(['pending', 'preparing'])
    ).order_by(Order.created_at).all()

    return render_template('restaurant/kitchen.html', orders=orders)


# ============== BILLING ==============

@restaurant_bp.route('/bills')
@restaurant_required
def bills():
    """Display bills"""
    open_bills = Bill.query.filter(
        Bill.business_id == g.current_business.id,
        Bill.status.in_(['open', 'partial'])
    ).order_by(Bill.created_at.desc()).all()

    return render_template('restaurant/bills.html', bills=open_bills)


@restaurant_bp.route('/orders/<int:order_id>/bill', methods=['GET', 'POST'])
@restaurant_required
def create_bill(order_id):
    """Create bill from order"""
    order = Order.query.filter_by(
        id=order_id, business_id=g.current_business.id
    ).first_or_404()

    # Check if bill already exists
    existing = Bill.query.filter_by(order_id=order.id, status='open').first()
    if existing:
        return redirect(url_for('restaurant.view_bill', bill_id=existing.id))

    # Generate bill number
    today = datetime.now().strftime('%Y%m%d')
    count = Bill.query.filter(
        Bill.business_id == g.current_business.id,
        Bill.bill_number.like(f'F{today}%')
    ).count()
    bill_number = f'F{today}{count + 1:04d}'

    bill = Bill(
        business_id=g.current_business.id,
        order_id=order.id,
        table_id=order.table_id,
        customer_id=order.customer_id,
        bill_number=bill_number,
        created_by=current_user.id,
        subtotal=order.subtotal  # Set subtotal directly from order
    )
    bill.calculate_totals()
    db.session.add(bill)
    db.session.commit()

    return redirect(url_for('restaurant.view_bill', bill_id=bill.id))


@restaurant_bp.route('/bills/<int:bill_id>')
@restaurant_required
def view_bill(bill_id):
    """View bill details"""
    bill = Bill.query.filter_by(
        id=bill_id, business_id=g.current_business.id
    ).first_or_404()

    # Recalculate if totals are zero but order has items
    if bill.order and (not bill.subtotal or float(bill.subtotal) == 0):
        bill.subtotal = bill.order.subtotal
        bill.calculate_totals()
        db.session.commit()

    return render_template('restaurant/bill_detail.html', bill=bill)


@restaurant_bp.route('/bills/<int:bill_id>/pay', methods=['POST'])
@restaurant_required
def pay_bill(bill_id):
    """Record payment for bill"""
    bill = Bill.query.filter_by(
        id=bill_id, business_id=g.current_business.id
    ).first_or_404()

    amount = float(request.form.get('amount', 0))
    method = request.form.get('payment_method', 'cash')
    reference = request.form.get('reference', '')

    if amount <= 0:
        flash('Monto invalido.', 'danger')
        return redirect(url_for('restaurant.view_bill', bill_id=bill.id))

    payment = Payment(
        bill_id=bill.id,
        business_id=g.current_business.id,
        amount=amount,
        payment_method=method,
        reference=reference,
        received_by=current_user.id
    )
    db.session.add(payment)

    bill.paid_amount = float(bill.paid_amount) + amount
    if bill.balance_due <= 0:
        bill.status = 'paid'
        bill.paid_at = datetime.utcnow()

        # Complete the order
        if bill.order:
            bill.order.status = 'completed'
            bill.order.completed_at = datetime.utcnow()

        # Set table to dirty
        if bill.table:
            bill.table.status = 'dirty'
    else:
        bill.status = 'partial'

    db.session.commit()
    flash('Pago registrado.', 'success')
    return redirect(url_for('restaurant.view_bill', bill_id=bill.id))


@restaurant_bp.route('/bills/<int:bill_id>/print')
@restaurant_required
def print_bill(bill_id):
    """Print-friendly bill view"""
    bill = Bill.query.filter_by(
        id=bill_id, business_id=g.current_business.id
    ).first_or_404()
    return render_template('restaurant/bill_print.html', bill=bill)


# ============== WAITLIST MANAGEMENT ==============

@restaurant_bp.route('/waitlist')
@restaurant_required
def waitlist():
    """Display waitlist for host/hostess"""
    from models.waitlist import WaitlistEntry, WaitlistSettings

    settings = WaitlistSettings.get_or_create(g.current_business.id)

    # Get active waitlist entries (waiting or notified)
    entries = WaitlistEntry.query.filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.status.in_(['waiting', 'notified'])
    ).order_by(
        WaitlistEntry.vip_priority.desc(),
        WaitlistEntry.queue_position
    ).all()

    # Get available tables for seating
    tables = RestaurantTable.query.filter_by(
        business_id=g.current_business.id,
        is_active=True,
        status='available'
    ).all()

    # Calculate stats
    stats = {
        'total_waiting': len([e for e in entries if e.status == 'waiting']),
        'total_notified': len([e for e in entries if e.status == 'notified']),
        'avg_wait': calculate_avg_wait_time(g.current_business.id),
        'total_seated_today': get_seated_today_count(g.current_business.id)
    }

    # Convert entries to dicts for JavaScript
    entries_dict = [e.to_dict() for e in entries]

    return render_template('restaurant/waitlist.html',
                           entries=entries,
                           entries_dict=entries_dict,
                           tables=tables,
                           settings=settings,
                           stats=stats)


@restaurant_bp.route('/waitlist/add', methods=['POST'])
@restaurant_required
def add_to_waitlist():
    """Add entry to waitlist"""
    from models.waitlist import WaitlistEntry, WaitlistSettings
    from models.customer import Customer

    data = request.form if request.form else request.get_json()

    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    party_size_input = data.get('party_size', 2)
    party_size = int(party_size_input) if party_size_input and str(party_size_input).strip() else 2

    if not name:
        if request.is_json:
            return jsonify({'error': 'Name is required'}), 400
        flash('El nombre es requerido.', 'danger')
        return redirect(url_for('restaurant.waitlist'))

    # Find or create customer
    customer = None
    if phone:
        customer = Customer.query.filter_by(
            business_id=g.current_business.id,
            phone=phone
        ).first()
        if not customer:
            customer = Customer(
                business_id=g.current_business.id,
                name=name,
                phone=phone,
                email=email
            )
            db.session.add(customer)
            db.session.flush()

    # Get next queue position
    max_pos = db.session.query(db.func.max(WaitlistEntry.queue_position)).filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.status.in_(['waiting', 'notified'])
    ).scalar() or 0

    # Calculate estimated wait time
    settings = WaitlistSettings.get_or_create(g.current_business.id)
    quoted_wait = calculate_estimated_wait(g.current_business.id, party_size, settings)

    # Check for previous no-shows
    no_show_count = 0
    if phone:
        no_show_count = WaitlistEntry.query.filter(
            WaitlistEntry.business_id == g.current_business.id,
            WaitlistEntry.phone == phone,
            WaitlistEntry.status == 'no_show'
        ).count()

    # Parse optional numeric fields safely
    high_chairs = data.get('high_chairs', 0)
    high_chairs = int(high_chairs) if high_chairs and str(high_chairs).strip() else 0

    quoted_wait_input = data.get('quoted_wait', '')
    quoted_wait_final = int(quoted_wait_input) if quoted_wait_input and str(quoted_wait_input).strip() else quoted_wait

    entry = WaitlistEntry(
        business_id=g.current_business.id,
        customer_id=customer.id if customer else None,
        name=name,
        phone=phone,
        email=email,
        party_size=party_size,
        high_chairs_needed=high_chairs,
        wheelchair_accessible=data.get('wheelchair') in ['true', 'on', True, '1'],
        seating_preference=data.get('seating_preference', ''),
        special_occasion=data.get('special_occasion', ''),
        notes=data.get('notes', ''),
        vip_priority=data.get('vip') in ['true', 'on', True, '1'],
        queue_position=max_pos + 1,
        quoted_wait_minutes=quoted_wait_final,
        source=data.get('source', 'host'),
        no_show_count=no_show_count
    )
    db.session.add(entry)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'entry': entry.to_dict()})

    flash(f'{name} agregado a la lista de espera.', 'success')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/update', methods=['POST'])
@restaurant_required
def update_waitlist_entry(entry_id):
    """Update waitlist entry"""
    from models.waitlist import WaitlistEntry

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    data = request.form if request.form else request.get_json()

    if 'name' in data:
        entry.name = data['name']
    if 'phone' in data:
        entry.phone = data['phone']
    if 'email' in data:
        entry.email = data['email']
    if 'party_size' in data:
        entry.party_size = int(data['party_size'])
    if 'high_chairs' in data:
        entry.high_chairs_needed = int(data['high_chairs'])
    if 'wheelchair' in data:
        entry.wheelchair_accessible = data['wheelchair'] in ['true', 'on', True, '1']
    if 'seating_preference' in data:
        entry.seating_preference = data['seating_preference']
    if 'special_occasion' in data:
        entry.special_occasion = data['special_occasion']
    if 'notes' in data:
        entry.notes = data['notes']
    if 'vip' in data:
        entry.vip_priority = data['vip'] in ['true', 'on', True, '1']
    if 'quoted_wait' in data:
        entry.quoted_wait_minutes = int(data['quoted_wait'])

    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'entry': entry.to_dict()})

    flash('Entrada actualizada.', 'success')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/notify', methods=['POST'])
@restaurant_required
def notify_waitlist_entry(entry_id):
    """Send notification that table is ready"""
    from models.waitlist import WaitlistEntry, WaitlistSettings

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    entry.mark_notified()
    db.session.commit()

    # Send notification via WhatsApp if configured
    settings = WaitlistSettings.get_or_create(g.current_business.id)
    notification_sent = False

    if settings.notify_via_whatsapp and entry.phone:
        message = settings.notification_message.format(
            name=entry.name,
            party_size=entry.party_size,
            restaurant=g.current_business.business_name
        )
        # TODO: Integrate with WhatsApp sending
        notification_sent = True

    if request.is_json:
        return jsonify({'success': True, 'notification_sent': notification_sent})

    flash(f'{entry.name} notificado - mesa lista.', 'success')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/seat', methods=['POST'])
@restaurant_required
def seat_waitlist_entry(entry_id):
    """Mark entry as seated"""
    from models.waitlist import WaitlistEntry

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    data = request.form if request.form else request.get_json()
    table_id = data.get('table_id')

    entry.mark_seated(table_id=int(table_id) if table_id else None)

    # Update table status if specified
    if table_id:
        table = RestaurantTable.query.get(int(table_id))
        if table and table.business_id == g.current_business.id:
            table.status = 'occupied'

    # Reorder queue positions
    reorder_queue(g.current_business.id)

    db.session.commit()

    if request.is_json:
        return jsonify({'success': True})

    flash(f'{entry.name} sentado.', 'success')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/no-show', methods=['POST'])
@restaurant_required
def noshow_waitlist_entry(entry_id):
    """Mark entry as no-show"""
    from models.waitlist import WaitlistEntry

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    entry.mark_no_show()
    reorder_queue(g.current_business.id)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True})

    flash(f'{entry.name} marcado como no-show.', 'warning')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/cancel', methods=['POST'])
@restaurant_required
def cancel_waitlist_entry(entry_id):
    """Cancel waitlist entry"""
    from models.waitlist import WaitlistEntry

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    entry.mark_cancelled()
    reorder_queue(g.current_business.id)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True})

    flash(f'{entry.name} cancelado.', 'info')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/<int:entry_id>/delete', methods=['POST'])
@restaurant_required
def delete_waitlist_entry(entry_id):
    """Delete waitlist entry"""
    from models.waitlist import WaitlistEntry

    entry = WaitlistEntry.query.filter_by(
        id=entry_id, business_id=g.current_business.id
    ).first_or_404()

    db.session.delete(entry)
    reorder_queue(g.current_business.id)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True})

    flash('Entrada eliminada.', 'info')
    return redirect(url_for('restaurant.waitlist'))


@restaurant_bp.route('/waitlist/join/<token>')
def waitlist_self_checkin(token):
    """Public page for self check-in via QR code"""
    from models.waitlist import WaitlistSettings

    # Find business from token or use a default landing
    # For now, we'll need a business_id in the URL
    business_id = request.args.get('b')
    if not business_id:
        return render_template('restaurant/waitlist_join.html', error='Invalid link')

    from models.business import Business
    business = Business.query.get(int(business_id))
    if not business or business.business_type != 'restaurant':
        return render_template('restaurant/waitlist_join.html', error='Restaurant not found')

    settings = WaitlistSettings.get_or_create(business.id)
    if not settings.allow_self_checkin:
        return render_template('restaurant/waitlist_join.html', error='Self check-in not available')

    return render_template('restaurant/waitlist_join.html',
                           business=business,
                           settings=settings,
                           token=token)


@restaurant_bp.route('/waitlist/join', methods=['POST'])
def waitlist_self_add():
    """Public endpoint for self-adding to waitlist"""
    from models.waitlist import WaitlistEntry, WaitlistSettings
    from models.business import Business
    from models.customer import Customer

    data = request.form if request.form else request.get_json()
    business_id = data.get('business_id')

    if not business_id:
        return jsonify({'error': 'Invalid request'}), 400

    business = Business.query.get(int(business_id))
    if not business:
        return jsonify({'error': 'Restaurant not found'}), 404

    settings = WaitlistSettings.get_or_create(business.id)
    if not settings.allow_self_checkin:
        return jsonify({'error': 'Self check-in not available'}), 403

    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    party_size = int(data.get('party_size', 2))

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if settings.require_phone_self_checkin and not phone:
        return jsonify({'error': 'Phone is required'}), 400

    if party_size > settings.max_party_size_self_checkin:
        return jsonify({'error': f'For parties larger than {settings.max_party_size_self_checkin}, please speak with host'}), 400

    # Find or create customer
    customer = None
    if phone:
        customer = Customer.query.filter_by(business_id=business.id, phone=phone).first()
        if not customer:
            customer = Customer(
                business_id=business.id,
                name=name,
                phone=phone,
                email=data.get('email', '')
            )
            db.session.add(customer)
            db.session.flush()

    # Get next queue position
    max_pos = db.session.query(db.func.max(WaitlistEntry.queue_position)).filter(
        WaitlistEntry.business_id == business.id,
        WaitlistEntry.status.in_(['waiting', 'notified'])
    ).scalar() or 0

    # Calculate estimated wait
    quoted_wait = calculate_estimated_wait(business.id, party_size, settings)

    entry = WaitlistEntry(
        business_id=business.id,
        customer_id=customer.id if customer else None,
        name=name,
        phone=phone,
        email=data.get('email', ''),
        party_size=party_size,
        high_chairs_needed=int(data.get('high_chairs', 0)),
        seating_preference=data.get('seating_preference', ''),
        notes=data.get('notes', ''),
        queue_position=max_pos + 1,
        quoted_wait_minutes=quoted_wait,
        source='qr_code'
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'success': True,
        'position': entry.queue_position,
        'estimated_wait': entry.quoted_wait_minutes,
        'token': entry.confirmation_token
    })


@restaurant_bp.route('/waitlist/status/<token>')
def waitlist_check_status(token):
    """Public page to check waitlist status"""
    from models.waitlist import WaitlistEntry, WaitlistSettings

    entry = WaitlistEntry.query.filter_by(confirmation_token=token).first()
    if not entry:
        return render_template('restaurant/waitlist_status.html', error='Entry not found')

    settings = WaitlistSettings.get_or_create(entry.business_id)

    return render_template('restaurant/waitlist_status.html',
                           entry=entry,
                           settings=settings)


@restaurant_bp.route('/waitlist/analytics')
@restaurant_required
@owner_required
def waitlist_analytics():
    """View waitlist analytics"""
    from models.waitlist import WaitlistEntry
    from sqlalchemy import func
    from datetime import timedelta

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)

    # Get stats for the past week
    daily_stats = db.session.query(
        func.date(WaitlistEntry.check_in_time).label('date'),
        func.count(WaitlistEntry.id).label('total'),
        func.avg(
            func.extract('epoch', WaitlistEntry.seated_at - WaitlistEntry.check_in_time) / 60
        ).label('avg_wait')
    ).filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.check_in_time >= week_ago,
        WaitlistEntry.status == 'seated'
    ).group_by(func.date(WaitlistEntry.check_in_time)).all()

    # No-show rate
    total_entries = WaitlistEntry.query.filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.check_in_time >= week_ago
    ).count()

    no_shows = WaitlistEntry.query.filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.check_in_time >= week_ago,
        WaitlistEntry.status == 'no_show'
    ).count()

    no_show_rate = (no_shows / total_entries * 100) if total_entries > 0 else 0

    # Peak hours
    hourly_stats = db.session.query(
        func.extract('hour', WaitlistEntry.check_in_time).label('hour'),
        func.count(WaitlistEntry.id).label('count')
    ).filter(
        WaitlistEntry.business_id == g.current_business.id,
        WaitlistEntry.check_in_time >= week_ago
    ).group_by(func.extract('hour', WaitlistEntry.check_in_time)).all()

    return render_template('restaurant/waitlist_analytics.html',
                           daily_stats=daily_stats,
                           hourly_stats=hourly_stats,
                           no_show_rate=no_show_rate,
                           total_entries=total_entries)


@restaurant_bp.route('/waitlist/settings', methods=['GET', 'POST'])
@restaurant_required
@owner_required
def waitlist_settings():
    """Configure waitlist settings"""
    from models.waitlist import WaitlistSettings

    settings = WaitlistSettings.get_or_create(g.current_business.id)

    if request.method == 'POST':
        settings.avg_table_turnover_minutes = int(request.form.get('turnover', 45))
        settings.buffer_minutes_per_party = int(request.form.get('buffer', 5))
        settings.notify_via_whatsapp = request.form.get('notify_whatsapp') == 'on'
        settings.notify_via_sms = request.form.get('notify_sms') == 'on'
        settings.notification_message = request.form.get('notification_message', settings.notification_message)
        settings.allow_self_checkin = request.form.get('allow_self_checkin') == 'on'
        settings.max_party_size_self_checkin = int(request.form.get('max_party', 8))
        settings.require_phone_self_checkin = request.form.get('require_phone') == 'on'
        settings.show_queue_position = request.form.get('show_position') == 'on'
        settings.show_estimated_wait = request.form.get('show_wait') == 'on'

        db.session.commit()
        flash('Configuracion guardada.', 'success')
        return redirect(url_for('restaurant.waitlist_settings'))

    return render_template('restaurant/waitlist_settings.html', settings=settings)


@restaurant_bp.route('/waitlist/qr-code')
@restaurant_required
def waitlist_qr_code():
    """Generate QR code for self check-in"""
    import qrcode
    import io
    import base64

    # Generate URL for self check-in
    checkin_url = url_for('restaurant.waitlist_self_checkin',
                          token='join',
                          b=g.current_business.id,
                          _external=True)

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(checkin_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template('restaurant/waitlist_qr.html',
                           qr_code=qr_base64,
                           checkin_url=checkin_url)


# ============== WAITLIST HELPER FUNCTIONS ==============

def calculate_estimated_wait(business_id, party_size, settings):
    """Calculate estimated wait time based on current queue and table availability"""
    from models.waitlist import WaitlistEntry

    # Count parties ahead in queue
    parties_ahead = WaitlistEntry.query.filter(
        WaitlistEntry.business_id == business_id,
        WaitlistEntry.status == 'waiting'
    ).count()

    # Count available tables that could fit this party
    available_tables = RestaurantTable.query.filter(
        RestaurantTable.business_id == business_id,
        RestaurantTable.is_active == True,
        RestaurantTable.status == 'available',
        RestaurantTable.capacity >= party_size
    ).count()

    # If tables available now, minimal wait
    if available_tables > 0 and parties_ahead == 0:
        return 5

    # Calculate based on turnover
    base_wait = settings.avg_table_turnover_minutes
    buffer = settings.buffer_minutes_per_party * parties_ahead

    # Estimate: (parties ahead / available tables) * turnover + buffer
    occupied_tables = RestaurantTable.query.filter(
        RestaurantTable.business_id == business_id,
        RestaurantTable.is_active == True,
        RestaurantTable.status == 'occupied'
    ).count()

    if occupied_tables > 0:
        estimated = int((parties_ahead / max(occupied_tables, 1)) * base_wait + buffer)
    else:
        estimated = base_wait + buffer

    return max(5, min(estimated, 120))  # Between 5 and 120 minutes


def calculate_avg_wait_time(business_id):
    """Calculate average wait time from recent seated entries"""
    from models.waitlist import WaitlistEntry
    from sqlalchemy import func

    today = datetime.utcnow().date()

    result = db.session.query(
        func.avg(
            func.extract('epoch', WaitlistEntry.seated_at - WaitlistEntry.check_in_time) / 60
        )
    ).filter(
        WaitlistEntry.business_id == business_id,
        func.date(WaitlistEntry.check_in_time) == today,
        WaitlistEntry.status == 'seated'
    ).scalar()

    return int(result) if result else 0


def get_seated_today_count(business_id):
    """Get count of parties seated today"""
    from models.waitlist import WaitlistEntry
    from sqlalchemy import func

    today = datetime.utcnow().date()

    return WaitlistEntry.query.filter(
        WaitlistEntry.business_id == business_id,
        func.date(WaitlistEntry.seated_at) == today,
        WaitlistEntry.status == 'seated'
    ).count()


def reorder_queue(business_id):
    """Reorder queue positions after changes"""
    from models.waitlist import WaitlistEntry

    entries = WaitlistEntry.query.filter(
        WaitlistEntry.business_id == business_id,
        WaitlistEntry.status.in_(['waiting', 'notified'])
    ).order_by(
        WaitlistEntry.vip_priority.desc(),
        WaitlistEntry.check_in_time
    ).all()

    for i, entry in enumerate(entries, 1):
        entry.queue_position = i
