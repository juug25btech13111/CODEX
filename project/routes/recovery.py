from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from utils.email_utils import send_smtp_email
from models import db, User, PasswordResetOTP, AuditLog
from app import limiter
import secrets
from datetime import datetime, timedelta, timezone

recovery_bp = Blueprint('recovery', __name__)

def generate_otp():
    """Generate a 6-digit cryptographic OTP."""
    return ''.join(secrets.choice('0123456789') for _ in range(6))

@recovery_bp.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("5 per hour") # Prevent someone from spamming email inboxes
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        # We always say the email was sent to prevent user enumeration attacks
        flash('If an account exists with that email, a password reset link has been sent.', 'info')
        
        if user:
            # Invalidate any old unused OTPs
            PasswordResetOTP.query.filter_by(user_id=user.id, is_used=False).update({'is_used': True})
            
            # Generate new OTP
            otp_code = generate_otp()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            
            new_otp = PasswordResetOTP(user_id=user.id, otp=otp_code, expires_at=expires_at)
            db.session.add(new_otp)
            db.session.commit()
            
            # Save email in session to verify OTP against
            session['reset_email'] = user.email
            
            # Print OTP to console for local testing / development
            print(f"\n{'='*60}")
            print(f"[DEBUG] GENERATED OTP FOR {user.email}: {otp_code}")
            print(f"   (Use this code if Resend email delivery fails)")
            print(f"{'='*60}\n")
            
            # Send Email via SMTP
            subject = '[Action Required] Password Reset Code - NeuroSent Security'
            text_content = (
                f"NEUROSENT SECURITY ALERT\n"
                f"========================\n\n"
                f"Hello,\n\n"
                f"We received a request to reset the password associated with your NeuroSent account.\n\n"
                f"Your One-Time Password (OTP): {otp_code}\n\n"
                f"This code expires in 10 minutes. Do not share this code with anyone.\n"
                f"If you did not request this, please ignore this email.\n\n"
                f"-- NeuroSent Security Team\n"
                f"Powered by NeuroSent AI Platform"
            )
            
            html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5; padding: 40px 0;">
                    <tr><td align="center">
                        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.08);">
                            
                            <!-- Header Banner -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); padding: 40px 40px 30px 40px; text-align: center;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                        <tr><td align="center">
                                            <div style="width: 64px; height: 64px; background-color: rgba(255,255,255,0.15); border-radius: 50%; margin: 0 auto 16px; line-height: 64px; font-size: 28px;">
                                                &#128274;
                                            </div>
                                            <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0 0 8px; letter-spacing: -0.5px;">Password Reset Request</h1>
                                            <p style="color: #c7d2fe; font-size: 14px; margin: 0;">NeuroSent Security Verification</p>
                                        </td></tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Body Content -->
                            <tr>
                                <td style="padding: 36px 40px 20px;">
                                    <p style="color: #1f2937; font-size: 16px; margin: 0 0 16px; line-height: 1.6;">Hello,</p>
                                    <p style="color: #4b5563; font-size: 15px; line-height: 1.7; margin: 0 0 28px;">
                                        We received a request to reset the password for your <strong style="color: #1f2937;">NeuroSent</strong> account. 
                                        Use the verification code below to complete the process. This code is valid for <strong style="color: #dc2626;">10 minutes</strong> only.
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- OTP Code Box -->
                            <tr>
                                <td style="padding: 0 40px;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                        <tr><td style="background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); border: 2px solid #c7d2fe; border-radius: 12px; padding: 28px; text-align: center;">
                                            <p style="color: #6366f1; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 12px;">Your Verification Code</p>
                                            <p style="font-size: 40px; font-weight: 800; letter-spacing: 12px; color: #1e1b4b; margin: 0; font-family: 'Courier New', monospace;">{otp_code}</p>
                                        </td></tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Security Tips -->
                            <tr>
                                <td style="padding: 28px 40px 16px;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 0 8px 8px 0; padding: 16px 20px;">
                                        <tr><td>
                                            <p style="color: #92400e; font-size: 13px; font-weight: 700; margin: 0 0 6px;">Security Tips</p>
                                            <p style="color: #78350f; font-size: 12px; line-height: 1.6; margin: 0;">
                                                &#8226; Never share this code with anyone, including NeuroSent staff.<br>
                                                &#8226; NeuroSent will never ask for your password via email.<br>
                                                &#8226; If you did not request this reset, no action is needed.
                                            </p>
                                        </td></tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Divider -->
                            <tr>
                                <td style="padding: 12px 40px;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                        <tr><td style="border-top: 1px solid #e5e7eb;"></td></tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding: 8px 40px 32px; text-align: center;">
                                    <p style="font-size: 12px; color: #9ca3af; margin: 0 0 6px;">&copy; {datetime.now(timezone.utc).year} NeuroSent AI Platform. All rights reserved.</p>
                                    <p style="font-size: 11px; color: #d1d5db; margin: 0;">Empowering Intelligent Feedback Analysis</p>
                                </td>
                            </tr>
                            
                        </table>
                    </td></tr>
                </table>
            </body>
            </html>
            """
            
            try:
                result = send_smtp_email(user.email, subject, html_content, text_content, priority="high")
                if not result:
                    print(f"[RECOVERY] send_smtp_email returned False for {user.email}. OTP is saved in DB.", flush=True)
            except Exception as e:
                print(f"[RECOVERY] Email sending failed but OTP is saved: {e}", flush=True)
                
        # Redirect to OTP verification page (if they supplied an email, let them *try* to enter an OTP)
        if email: 
            session['reset_email'] = email # store even if non-existent to avoid enumeration
            return redirect(url_for('recovery.verify_otp'))
            
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@recovery_bp.route('/verify_otp', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def verify_otp():
    """Verify the 6-digit OTP."""
    email = session.get('reset_email')
    if not email:
        flash('Session expired or invalid. Please request a new password reset.', 'danger')
        return redirect(url_for('recovery.forgot_password'))
        
    if request.method == 'POST':
        otp_attempt = request.form.get('otp', '').strip()
        user = User.query.filter_by(email=email).first()
        
        # If user doesn't exist but we want to prevent enumeration, act like wrong OTP
        if not user:
            flash('Invalid or expired OTP code.', 'danger')
            return render_template('auth/verify_otp.html')
            
        # Find active OTP for user
        active_otp = PasswordResetOTP.query.filter_by(
            user_id=user.id, 
            otp=otp_attempt, 
            is_used=False
        ).filter(PasswordResetOTP.expires_at > datetime.now(timezone.utc)).first()
        
        if active_otp:
            # Mark as used and authenticate session for password reset
            active_otp.is_used = True
            db.session.commit()
            
            session['otp_verified'] = True
            flash('OTP Verified! Create your new password.', 'success')
            return redirect(url_for('recovery.reset_password'))
        else:
            flash('Invalid or expired OTP code.', 'danger')
            
    return render_template('auth/verify_otp.html')

@recovery_bp.route('/reset_password', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def reset_password():
    email = session.get('reset_email')
    is_verified = session.get('otp_verified')
    
    if not email or not is_verified:
        flash('Unauthorized. Please verify your OTP code first.', 'danger')
        return redirect(url_for('recovery.forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid user associated with this session.', 'danger')
        session.pop('reset_email', None)
        session.pop('otp_verified', None)
        return redirect(url_for('recovery.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if password != confirm_password:
            flash('Passwords must match.', 'danger')
            return redirect(url_for('recovery.reset_password'))
        
        # Password strength validation
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return redirect(url_for('recovery.reset_password'))
        if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
            flash('Password must contain both letters and numbers.', 'danger')
            return redirect(url_for('recovery.reset_password'))
        
        user.set_password(password)
        
        # Audit log
        entry = AuditLog(user_id=user.id, action='password_reset', target=user.email, ip_address=request.remote_addr)
        db.session.add(entry)
        db.session.commit()
        
        # Clear session upon success
        session.pop('reset_email', None)
        session.pop('otp_verified', None)
        
        flash('Your password has been securely updated! You may now log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html')
