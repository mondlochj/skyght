from models.user import User
from extensions import db
from flask_mail import Message
from flask import current_app
import secrets


def create_user(name, email, password):
    if User.query.filter_by(email=email).first():
        return None, "Email already registered"
    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, None


def create_invite(business_id, email, role_name='staff'):
    token = secrets.token_urlsafe(32)
    # In real app you'd save this in an Invite model with expiration
    # For MVP we just generate link
    invite_link = f"http://127.0.0.1:5000/auth/invite/accept?token={token}&email={email}&business={business_id}&role={role_name}"
    return token, invite_link


def send_invite_email(email, invite_link, business_name):
    from extensions import mail
    msg = Message(
        subject=f"Invitacion para unirte a {business_name} en Skyght",
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[email]
    )
    msg.body = f"""
Hola,

Has sido invitado a unirte al equipo de {business_name} en Skyght Business.

Usa este enlace para aceptar la invitacion y registrarte/unirte:

{invite_link}

El enlace es valido por 7 dias.

Nos vemos dentro!
Skyght Team
    """
    mail.send(msg)
