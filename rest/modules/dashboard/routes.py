from flask import Blueprint, render_template, redirect, url_for, g
from flask_login import login_required

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
@login_required
def index():
    if not g.get('current_business'):
        return redirect(url_for('onboarding.index'))

    business = g.current_business
    return render_template('dashboard.html', business=business)
