from flask import Blueprint, request, jsonify, current_app
from extensions import db
from models.customer import Customer
from models.conversation import Conversation
from models.message import Message
from models.business import Business
from .intent_engine import detect_intent
from datetime import datetime

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/webhook')


@whatsapp_bp.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json() or request.form

    # Simplified payload: {"from": "50212345678", "to": "50299999999", "text": "Hola quiero reservar mesa"}
    # In production, use the actual WhatsApp Cloud API structure

    sender_phone = data.get('from')      # customer's WhatsApp number
    business_phone = data.get('to')      # your business WhatsApp number
    message_text = data.get('text', '').strip()

    if not all([sender_phone, business_phone, message_text]):
        return jsonify({"status": "missing fields"}), 400

    # Find business by phone
    business = Business.query.filter_by(phone=business_phone).first()
    if not business:
        current_app.logger.warning(f"No business found for phone {business_phone}")
        return jsonify({"status": "business not found"}), 404

    # Find or create customer
    customer = Customer.query.filter_by(business_id=business.id, phone=sender_phone).first()
    if not customer:
        customer = Customer(
            business_id=business.id,
            phone=sender_phone,
            name="WhatsApp User"
        )
        db.session.add(customer)
        db.session.flush()

    # Find or create conversation
    conversation = Conversation.query.filter_by(customer_id=customer.id).first()
    if not conversation:
        conversation = Conversation(
            customer_id=customer.id,
            status='active',
            last_message_at=datetime.utcnow()
        )
        db.session.add(conversation)
        db.session.flush()

    # Save message
    msg = Message(
        conversation_id=conversation.id,
        direction='inbound',
        message_text=message_text,
        timestamp=datetime.utcnow()
    )
    db.session.add(msg)

    # Detect intent
    intent = detect_intent(message_text)
    conversation.last_message_at = datetime.utcnow()

    db.session.commit()

    return jsonify({"status": "received", "intent": intent}), 200


@whatsapp_bp.route('/whatsapp', methods=['GET'])
def whatsapp_verify():
    """Webhook verification for WhatsApp Cloud API."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    verify_token = current_app.config.get('WHATSAPP_VERIFY_TOKEN', 'skyght_verify_token')

    if mode == 'subscribe' and token == verify_token:
        return challenge, 200

    return 'Forbidden', 403
