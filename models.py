from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin, LoginManager
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('Admin', 'HOD', 'Staff', 'Student'), nullable=False, default='Student')
    department = db.Column(db.String(100))
    is_verified = db.Column(db.Boolean, default=False)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    mfa_secret = db.Column(db.String(32), nullable=True)  # TOTP secret for MFA
    deleted_at = db.Column(db.DateTime, nullable=True)  # Soft delete timestamp
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    feedbacks = db.relationship('Feedback', backref='author', lazy=True, cascade="all, delete-orphan")
    uploads = db.relationship('Upload', backref='uploader', lazy=True)

    @property
    def is_active(self):
        """Override Flask-Login: soft-deleted users cannot login."""
        return self.deleted_at is None

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

class Upload(db.Model):
    __tablename__ = 'uploads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    total_rows = db.Column(db.Integer, default=0)
    processed_rows = db.Column(db.Integer, default=0)
    status = db.Column(db.Enum('Pending', 'Processing', 'Completed', 'Failed'), default='Pending')
    upload_date = db.Column(db.DateTime, default=db.func.current_timestamp())

    feedbacks = db.relationship('Feedback', backref='upload_source', lazy=True, cascade="all, delete-orphan")

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('uploads.id'), nullable=True)
    original_text = db.Column(db.Text, nullable=False)
    cleaned_text = db.Column(db.Text)
    sentiment = db.Column(db.Enum('Positive', 'Negative', 'Neutral'), nullable=False)
    sentiment_score = db.Column(db.Float, nullable=False)
    department_category = db.Column(db.String(100))
    is_anonymous = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='New')  # New, Under Review, Resolved, Dismissed
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    replies = db.relationship('FeedbackReply', backref='feedback', lazy=True, cascade='all, delete-orphan')

class PasswordResetOTP(db.Model):
    __tablename__ = 'password_reset_otps'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref=db.backref('reset_otps', lazy=True, cascade="all, delete-orphan"))

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    target = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))

class FeedbackReply(db.Model):
    __tablename__ = 'feedback_replies'
    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('feedback.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    admin = db.relationship('User', backref=db.backref('admin_replies', lazy=True))
