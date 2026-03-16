from flask import Blueprint, render_template, g, abort
from flask_login import login_required
from models.customer import Customer
from models.conversation import Conversation
from models.message import Message

crm_bp = Blueprint('crm', __name__, url_prefix='/customers')


@crm_bp.route('/')
@login_required
def index():
    if not g.get('current_business'):
        abort(403)

    customers = Customer.query.filter_by(business_id=g.current_business.id)\
        .order_by(Customer.created_at.desc())\
        .all()

    return render_template('customers/index.html', customers=customers)


@crm_bp.route('/<int:customer_id>')
@login_required
def view(customer_id):
    if not g.get('current_business'):
        abort(403)

    customer = Customer.query.filter_by(
        id=customer_id,
        business_id=g.current_business.id
    ).first_or_404()

    conversations = Conversation.query.filter_by(customer_id=customer.id)\
        .order_by(Conversation.last_message_at.desc())\
        .all()

    # For MVP: show messages from the most recent conversation only
    messages = []
    if conversations:
        latest_conv = conversations[0]
        messages = Message.query.filter_by(conversation_id=latest_conv.id)\
            .order_by(Message.timestamp.asc())\
            .all()

    return render_template('customers/view.html',
                           customer=customer,
                           conversations=conversations,
                           messages=messages)
