import os
from flask import Flask, render_template, jsonify, request, session, flash, redirect, url_for
from markupsafe import Markup
from config import DevelopmentConfig, ProductionConfig
from models import db, bcrypt, login_manager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

# Initialize extensions outside create_app so blueprints can import them if needed
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
migrate = Migrate()

def create_app(config_class=DevelopmentConfig):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    # API-aware unauthorized handler: return 401 JSON for AJAX, redirect for browser
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.accept_mimetypes.best == 'application/json':
            return jsonify({'error': 'Authentication required'}), 401
        from flask import redirect, url_for, flash
        flash('Please log in to access this page.', 'info')
        return redirect(url_for('auth.login', next=request.url))

    # Create upload directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Session management: idle timeout + absolute timeout
    @app.before_request
    def enforce_session_timeout():
        from flask_login import current_user
        import time
        session.permanent = True  # Enables PERMANENT_SESSION_LIFETIME idle check
        
        # Absolute timeout: force re-login after 12 hours regardless of activity
        if current_user.is_authenticated:
            login_time = session.get('_login_time')
            if login_time is None:
                session['_login_time'] = time.time()
            elif time.time() - login_time > app.config.get('SESSION_ABSOLUTE_TIMEOUT', 43200):
                from flask_login import logout_user
                logout_user()
                session.clear()
                flash('Session expired. Please log in again.', 'info')
                return redirect(url_for('auth.login'))
    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.feedback import feedback_bp
    from routes.reports import reports_bp
    from routes.upload import upload_bp
    from routes.admin import admin_bp
    from routes.profile import profile_bp
    from routes.training import training_bp
    from routes.recovery import recovery_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(feedback_bp, url_prefix='/feedback')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(training_bp, url_prefix='/admin/ai')
    app.register_blueprint(recovery_bp, url_prefix='/recovery')

    # Root route redirects to dashboard or login
    @app.route('/')
    def index():
        from flask import redirect, url_for
        from flask_login import current_user
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    # Health check endpoint for load balancers
    @app.route('/health')
    def health_check():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'healthy', 'database': 'connected'}), 200
        except Exception as e:
            return jsonify({'status': 'unhealthy', 'database': str(e)}), 503

    @app.after_request
    def add_security_headers(response):
        # Prevent browser caching to secure the "back" button after logout
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        # Industry-standard security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Content Security Policy
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://code.jquery.com https://cdn.datatables.net; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.datatables.net; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        return response

    # ===== Custom Error Handlers =====
    @app.errorhandler(403)
    def forbidden_handler(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_handler(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_error_handler(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # Custom Jinja filters
    @app.template_filter('sentiment_color')
    def sentiment_color(sentiment):
        return {
            'Positive': 'text-green-500',
            'Negative': 'text-red-500',
            'Neutral': 'text-gray-500'
        }.get(sentiment, 'text-gray-500')

    @app.template_filter('sentiment_badge')
    def sentiment_badge(sentiment):
        valid_sentiments = {'Positive', 'Negative', 'Neutral'}
        safe_sentiment = sentiment if sentiment in valid_sentiments else 'Neutral'
        colors = {
            'Positive': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
            'Negative': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
            'Neutral': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
        }
        classes = colors[safe_sentiment]
        return Markup(f'<span class="px-2 py-1 text-xs font-medium rounded-full {classes}">{safe_sentiment}</span>')

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8080)
