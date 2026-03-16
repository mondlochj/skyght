from flask import Blueprint, render_template, g, abort
from flask_login import login_required
from models.job import Job

jobs_bp = Blueprint('jobs', __name__, url_prefix='/jobs')


@jobs_bp.route('/')
@login_required
def index():
    if not g.get('current_business'):
        abort(403)

    if g.current_business.business_type != 'service':
        abort(403)

    jobs = Job.query.filter_by(business_id=g.current_business.id)\
        .order_by(Job.scheduled_time.desc())\
        .all()

    return render_template('jobs/index.html', jobs=jobs)
