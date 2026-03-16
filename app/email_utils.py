import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def send_email(to_email, subject, html_body, text_body=None):
    """Send an email using SMTP configuration from Flask app config."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = current_app.config['FROM_EMAIL']
        msg['To'] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP(
            current_app.config['SMTP_SERVER'],
            current_app.config['SMTP_PORT']
        )

        if current_app.config['SMTP_USE_TLS']:
            server.starttls()

        server.login(
            current_app.config['SMTP_USERNAME'],
            current_app.config['SMTP_PASSWORD']
        )

        server.sendmail(
            current_app.config['FROM_EMAIL'],
            to_email,
            msg.as_string()
        )
        server.quit()
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False


def send_verification_email(to_email, verification_token):
    """Send an email verification link."""
    app_url = current_app.config['APP_URL']
    verify_link = f"{app_url}?verify={verification_token}"

    subject = "Verify your Skyght account"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; border-top: none; }}
            .button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
            .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">Skyght</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Enterprise OCR Platform</p>
            </div>
            <div class="content">
                <h2>Verify Your Email</h2>
                <p>Thank you for creating a Skyght account! Please verify your email address by clicking the button below:</p>
                <p style="text-align: center;">
                    <a href="{verify_link}" class="button">Verify Email Address</a>
                </p>
                <p style="color: #64748b; font-size: 14px;">This link will expire in 24 hours.</p>
                <p style="color: #64748b; font-size: 14px;">If you didn't create a Skyght account, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>Skyght - Enterprise OCR Platform</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
Verify Your Skyght Account

Thank you for creating a Skyght account! Please verify your email address by visiting:

{verify_link}

This link will expire in 24 hours.

If you didn't create a Skyght account, you can safely ignore this email.
    """

    return send_email(to_email, subject, html_body, text_body)


def send_team_invitation(to_email, team_name, inviter_email, invite_token):
    """Send a team invitation email."""
    app_url = current_app.config['APP_URL']
    invite_link = f"{app_url}?invite={invite_token}"

    subject = f"You've been invited to join {team_name} on Skyght"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; border-top: none; }}
            .button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
            .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">Skyght</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Enterprise OCR Platform</p>
            </div>
            <div class="content">
                <h2>You're Invited!</h2>
                <p><strong>{inviter_email}</strong> has invited you to join the team <strong>{team_name}</strong> on Skyght.</p>
                <p>Click the button below to accept the invitation and join the team:</p>
                <p style="text-align: center;">
                    <a href="{invite_link}" class="button">Accept Invitation</a>
                </p>
                <p style="color: #64748b; font-size: 14px;">This invitation will expire in 7 days.</p>
                <p style="color: #64748b; font-size: 14px;">If you don't have a Skyght account yet, you'll be able to create one when you accept the invitation.</p>
            </div>
            <div class="footer">
                <p>If you didn't expect this invitation, you can safely ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
You've been invited to join {team_name} on Skyght!

{inviter_email} has invited you to join their team.

Accept the invitation by visiting: {invite_link}

This invitation will expire in 7 days.

If you don't have a Skyght account yet, you'll be able to create one when you accept the invitation.
    """

    return send_email(to_email, subject, html_body, text_body)
