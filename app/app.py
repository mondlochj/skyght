import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from blueprints.auth import auth_bp
from blueprints.teams import teams_bp
from blueprints.admin import admin_bp
from blueprints.documents import documents_bp
from blueprints.extraction import extraction_bp
from config import PORT

app = Flask(__name__, static_url_path='/ocr/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)
CORS(app)

# SMTP Configuration
app.config['SMTP_SERVER'] = 'mail.jetoko.com'
app.config['SMTP_PORT'] = int(os.getenv('SMTP_PORT', 587))
app.config['SMTP_USE_TLS'] = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 'yes')
app.config['SMTP_USERNAME'] = 'noreply@aroaero.com'
app.config['SMTP_PASSWORD'] = '{,81,WntIaB'
app.config['FROM_EMAIL'] = 'noreply@aroaero.com'
app.config['APP_URL'] = os.getenv('APP_URL', 'https://skyght.com/ocr')

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per 15 minutes"]
)

app.register_blueprint(auth_bp)
app.register_blueprint(teams_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(documents_bp)
app.register_blueprint(extraction_bp)

@app.route('/api/health')
def health():
    return jsonify({'status': 'Skyght Enterprise Running'})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(port=PORT, debug=True)
