from functools import wraps
from flask import g, flash, redirect, url_for
from flask_login import login_required


def owner_required(f):
    @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('current_business') or not g.get('current_role') or g.current_role.name != 'owner':
            flash("Solo el propietario puede realizar esta accion.", "danger")
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    def decorator(f):
        @login_required
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.get('current_role'):
                flash("No tienes permisos para esta accion.", "danger")
                return redirect(url_for('dashboard.index'))

            # Owner has all permissions
            if g.current_role.name == 'owner':
                return f(*args, **kwargs)

            # Check specific permission
            permissions = g.current_role.permissions_json or {}
            if not permissions.get(permission, False):
                flash("No tienes permisos para esta accion.", "danger")
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
