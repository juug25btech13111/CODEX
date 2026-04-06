from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user
from models import db, User, AuditLog, PasswordResetOTP
from urllib.parse import urlsplit
from app import limiter
from utils.email_utils import send_smtp_email
from datetime import datetime, timedelta, timezone
import re
import secrets

auth_bp = Blueprint('auth', __name__)


def log_audit(action, target=None, user_id=None):
    """Helper to log an audit event."""
    try:
        entry = AuditLog(
            user_id=user_id or (current_user.id if current_user.is_authenticated else None),
            action=action,
            target=target,
            ip_address=request.remote_addr
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print(f"[AUDIT] Failed to log: {e}", flush=True)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Block soft-deleted users
            if user.deleted_at is not None:
                flash('This account has been deactivated. Contact administration.', 'danger')
                return render_template('auth/login.html')
            
            # Check account lockout
            if user.is_locked():
                flash('Account is temporarily locked due to too many failed login attempts. Please try again later.', 'danger')
                log_audit('login_locked', target=email, user_id=user.id)
                return render_template('auth/login.html')
            
            if user.check_password(password):
                # Check email verification
                if not user.is_verified:
                    flash('Please verify your email address before logging in. Check your inbox for the verification code.', 'warning')
                    session['verify_email'] = user.email
                    return redirect(url_for('auth.verify_email'))
                
                # MFA check for Admin/HOD
                if user.role in ('Admin', 'HOD') and user.mfa_secret:
                    session['_mfa_user_id'] = user.id
                    user.failed_logins = 0
                    user.locked_until = None
                    db.session.commit()
                    return redirect(url_for('auth.verify_mfa'))
                
                # Session fixation prevention: clear old session before login
                session.clear()
                
                login_user(user)
                session.permanent = True
                
                # Reset failed login counter on success
                user.failed_logins = 0
                user.locked_until = None
                db.session.commit()
                
                log_audit('login', target=email)
                flash('Logged in successfully.', 'success')
                
                next_page = request.args.get('next')
                if not next_page or urlsplit(next_page).netloc != '':
                    next_page = url_for('dashboard.index')
                return redirect(next_page)
            else:
                # Increment failed login counter
                user.failed_logins = (user.failed_logins or 0) + 1
                if user.failed_logins >= current_app.config.get('MAX_FAILED_LOGINS', 5):
                    lockout_mins = current_app.config.get('LOCKOUT_DURATION_MINUTES', 15)
                    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_mins)
                    db.session.commit()
                    log_audit('account_locked', target=email, user_id=user.id)
                    flash('Too many failed attempts. Account locked for 15 minutes.', 'danger')
                    return render_template('auth/login.html')
                db.session.commit()
                log_audit('failed_login', target=email, user_id=user.id)
        else:
            log_audit('failed_login', target=email)
        
        flash('Invalid email or password.', 'danger')
            
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = 'Student'
        department = request.form.get('department', '').strip()
        
        # Input validation
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.register'))
        
        name = re.sub(r'<[^>]*>', '', name)
        
        if len(name) > 100:
            flash('Name must be 100 characters or less.', 'danger')
            return redirect(url_for('auth.register'))
        if len(email) > 120:
            flash('Email must be 120 characters or less.', 'danger')
            return redirect(url_for('auth.register'))
        
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            flash('Please enter a valid email address.', 'danger')
            return redirect(url_for('auth.register'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return redirect(url_for('auth.register'))
        if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
            flash('Password must contain both letters and numbers.', 'danger')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'danger')
            return redirect(url_for('auth.login'))
            
        new_user = User(name=name, email=email, role=role, department=department, is_verified=False)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Send email verification OTP
        otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        new_otp = PasswordResetOTP(user_id=new_user.id, otp=otp_code, expires_at=expires_at)
        db.session.add(new_otp)
        db.session.commit()
        
        subject = "Verify Your Email - NeuroSent"
        html_content = f"""
        <div style="font-family: 'Segoe UI', sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; background: #f9fafb; border-radius: 12px;">
            <h2 style="color: #1e40af; margin-bottom: 20px;">Email Verification</h2>
            <p style="color: #374151;">Hi {name}, your verification code is:</p>
            <div style="background: #1e40af; color: white; font-size: 32px; font-weight: bold; letter-spacing: 8px; text-align: center; padding: 20px; border-radius: 8px; margin: 20px 0;">{otp_code}</div>
            <p style="color: #6b7280; font-size: 14px;">This code expires in 10 minutes.</p>
        </div>
        """
        text_content = f"Hi {name}, your NeuroSent verification code is: {otp_code}. It expires in 10 minutes."
        
        try:
            send_smtp_email(new_user.email, subject, html_content, text_content)
        except Exception as e:
            print(f"[AUTH] Verification email failed: {e}", flush=True)
        
        log_audit('register', target=email, user_id=new_user.id)
        session['verify_email'] = email
        flash('Registration successful! Please check your email for the verification code.', 'success')
        return redirect(url_for('auth.verify_email'))
        
    return render_template('auth/register.html')


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def verify_email():
    email = session.get('verify_email')
    if not email:
        flash('Please register or login first.', 'info')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        otp_attempt = request.form.get('otp', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            active_otp = PasswordResetOTP.query.filter_by(
                user_id=user.id, otp=otp_attempt, is_used=False
            ).filter(PasswordResetOTP.expires_at > datetime.now(timezone.utc)).first()
            
            if active_otp:
                user.is_verified = True
                active_otp.is_used = True
                db.session.commit()
                session.pop('verify_email', None)
                log_audit('email_verified', target=email, user_id=user.id)
                flash('Email verified successfully! You can now login.', 'success')
                return redirect(url_for('auth.login'))
        
        flash('Invalid or expired verification code.', 'danger')
    
    return render_template('auth/verify_email.html', email=email)


@auth_bp.route('/resend-verification', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verification():
    email = session.get('verify_email')
    if not email:
        flash('Please register first.', 'info')
        return redirect(url_for('auth.register'))
    
    user = User.query.filter_by(email=email).first()
    if user and not user.is_verified:
        otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        new_otp = PasswordResetOTP(user_id=user.id, otp=otp_code, expires_at=expires_at)
        db.session.add(new_otp)
        db.session.commit()
        
        subject = "Verify Your Email - NeuroSent"
        html_content = f"""
        <div style="font-family: 'Segoe UI', sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; background: #f9fafb; border-radius: 12px;">
            <h2 style="color: #1e40af; margin-bottom: 20px;">Email Verification</h2>
            <p style="color: #374151;">Your new verification code is:</p>
            <div style="background: #1e40af; color: white; font-size: 32px; font-weight: bold; letter-spacing: 8px; text-align: center; padding: 20px; border-radius: 8px; margin: 20px 0;">{otp_code}</div>
            <p style="color: #6b7280; font-size: 14px;">This code expires in 10 minutes.</p>
        </div>
        """
        text_content = f"Your new NeuroSent verification code is: {otp_code}. It expires in 10 minutes."
        try:
            send_smtp_email(user.email, subject, html_content, text_content)
        except Exception as e:
            print(f"[AUTH] Resend verification failed: {e}", flush=True)
        
        flash('A new verification code has been sent to your email.', 'success')
    else:
        flash('Account not found or already verified.', 'info')
    
    return redirect(url_for('auth.verify_email'))


@auth_bp.route('/logout', methods=['POST'])
def logout():
    log_audit('logout')
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    response = redirect(url_for('auth.login'))
    response.delete_cookie(
        current_app.config.get('SESSION_COOKIE_NAME', 'session'),
        path='/',
        samesite='Lax'
    )
    return response


@auth_bp.route('/verify-mfa', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def verify_mfa():
    user_id = session.get('_mfa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        import pyotp
        code = request.form.get('code', '').strip()
        user = User.query.get(user_id)
        
        if user and user.mfa_secret:
            totp = pyotp.TOTP(user.mfa_secret)
            if totp.verify(code, valid_window=1):
                session.pop('_mfa_user_id', None)
                session.clear()
                login_user(user)
                session.permanent = True
                log_audit('login_mfa', target=user.email)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('dashboard.index'))
        
        flash('Invalid verification code. Please try again.', 'danger')
    
    return render_template('auth/verify_mfa.html')


@auth_bp.route('/setup-mfa', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def setup_mfa():
    from flask_login import login_required as lr
    if not current_user.is_authenticated:
        flash('Please log in first.', 'info')
        return redirect(url_for('auth.login'))
    
    if current_user.role not in ('Admin', 'HOD'):
        flash('MFA is only available for Admin and HOD roles.', 'warning')
        return redirect(url_for('dashboard.index'))
    
    import pyotp
    import qrcode
    import io
    import base64
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        pending_secret = session.get('_mfa_setup_secret')
        
        if pending_secret:
            totp = pyotp.TOTP(pending_secret)
            if totp.verify(code, valid_window=1):
                current_user.mfa_secret = pending_secret
                db.session.commit()
                session.pop('_mfa_setup_secret', None)
                log_audit('mfa_enabled', target=current_user.email)
                flash('Two-factor authentication enabled successfully!', 'success')
                return redirect(url_for('profile.index'))
            else:
                flash('Invalid code. Please scan the QR code again and enter the current code.', 'danger')
    
    # Generate new secret
    secret = pyotp.random_base32()
    session['_mfa_setup_secret'] = secret
    
    # Generate QR code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.email, issuer_name='NeuroSent')
    
    qr = qrcode.make(uri)
    buffer = io.BytesIO()
    qr.save(buffer, format='PNG')
    buffer.seek(0)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return render_template('auth/setup_mfa.html', qr_code=qr_base64, secret=secret)

