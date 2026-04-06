from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, Response
from flask_login import login_required, current_user
from markupsafe import escape
import random
import string
import re
import secrets
import csv
import io
from threading import Thread
from utils.email_utils import send_smtp_email
from utils.decorators import requires_roles
from models import db, User, AuditLog, Feedback, FeedbackReply

admin_bp = Blueprint('admin', __name__)

def _generate_strong_password(length=12):
    """Generate a strong random password with letters, digits, and special characters."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one uppercase, one lowercase, one digit, one special
        if (any(c.isupper() for c in password) and
            any(c.islower() for c in password) and
            any(c.isdigit() for c in password) and
            any(c in "!@#$%&*" for c in password)):
            return password

def send_async_email(app, to_email, subject, html_content, text_content=None):
    with app.app_context():
        send_smtp_email(to_email, subject, html_content, text_content)

def _build_welcome_email(name, email, password, role):
    """Build the enterprise-grade welcome email for a newly created user."""
    subject = "Welcome to NeuroSent - Your Account Has Been Provisioned"
    text_body = (
        f"NEUROSENT ACCOUNT PROVISIONED\n"
        f"=============================\n\n"
        f"Hello {name},\n\n"
        f"An administrator has created a {role} account for you on the NeuroSent platform.\n\n"
        f"Login Credentials:\n"
        f"  Email: {email}\n"
        f"  Temporary Password: {password}\n\n"
        f"IMPORTANT: Please login and change your password immediately.\n\n"
        f"-- NeuroSent Security Team"
    )
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5; padding: 40px 0;">
            <tr><td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.08);">
                    <tr>
                        <td style="background: linear-gradient(135deg, #065f46 0%, #047857 50%, #059669 100%); padding: 40px 40px 30px; text-align: center;">
                            <div style="width: 64px; height: 64px; background-color: rgba(255,255,255,0.15); border-radius: 50%; margin: 0 auto 16px; line-height: 64px; font-size: 28px;">&#127881;</div>
                            <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0 0 8px;">Welcome to NeuroSent</h1>
                            <p style="color: #a7f3d0; font-size: 14px; margin: 0;">Your {role} account is ready</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 36px 40px 20px;">
                            <p style="color: #1f2937; font-size: 16px; margin: 0 0 16px;">Hello <strong>{name}</strong>,</p>
                            <p style="color: #4b5563; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                                An administrator has provisioned a new <strong style="color: #059669;">{role}</strong> account for you on the NeuroSent AI-Powered Feedback Analysis Platform.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 40px 24px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr><td style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 24px;">
                                    <p style="color: #166534; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 14px;">Login Credentials</p>
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px; width: 130px;">Email</td>
                                            <td style="padding: 6px 0; color: #111827; font-size: 14px; font-weight: 600;">{email}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px;">Temporary Password</td>
                                            <td style="padding: 6px 0; font-family: 'Courier New', monospace; font-size: 15px; font-weight: 700; color: #1e1b4b; letter-spacing: 1px;">{password}</td>
                                        </tr>
                                    </table>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 40px 24px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 0 8px 8px 0; padding: 14px 18px;">
                                <tr><td>
                                    <p style="color: #991b1b; font-size: 13px; font-weight: 600; margin: 0;">&#9888; For security, please change your password immediately after your first login.</p>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 40px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="border-top: 1px solid #e5e7eb;"></td></tr></table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 40px 32px; text-align: center;">
                            <p style="font-size: 12px; color: #9ca3af; margin: 0 0 4px;">&copy; NeuroSent AI Platform. All rights reserved.</p>
                            <p style="font-size: 11px; color: #d1d5db; margin: 0;">This is an automated message. Please do not reply.</p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """
    return subject, html_body, text_body

@admin_bp.route('/create-user', methods=['GET', 'POST'])
@login_required
@requires_roles('Admin')
def create_user():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        department = request.form.get('department')
        
        if not all([name, email, password, role]):
            flash('Please fill in all required fields.', 'warning')
            return redirect(url_for('admin.create_user'))
        
        # Input validation: email format
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            flash('Please enter a valid email address.', 'warning')
            return redirect(url_for('admin.create_user'))
        
        # Input validation: field length limits
        if len(name) > 100 or len(email) > 120:
            flash('Name or email exceeds maximum allowed length.', 'warning')
            return redirect(url_for('admin.create_user'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'warning')
            return redirect(url_for('admin.create_user'))
            
        if User.query.filter_by(email=email).first():
            flash('A user with that email already exists.', 'danger')
            return redirect(url_for('admin.create_user'))
            
        try:
            new_user = User(name=name, email=email, role=role, department=department)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            # Send Welcome Email asynchronously using shared builder
            subject, html_body, text_body = _build_welcome_email(name, email, password, role)
            Thread(target=send_async_email, args=(current_app._get_current_object(), email, subject, html_body, text_body)).start()
            
            flash(f'Successfully created {escape(role)} account for {escape(name)}. Welcome email queued.', 'success')
            return redirect(url_for('admin.create_user'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the user. Please try again.', 'danger')
            
    return render_template('admin/create_user.html')

@admin_bp.route('/manage-users', methods=['GET'])
@login_required
@requires_roles('Admin')
def manage_users():
    users = User.query.filter(User.deleted_at.is_(None)).all()
    return render_template('admin/manage_users.html', users=users)

@admin_bp.route('/reset-password/<int:user_id>', methods=['POST'])
@login_required
@requires_roles('Admin')
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    
    custom_password = request.form.get('new_password', '').strip()
    
    if custom_password:
        new_password = custom_password
    else:
        # Generate cryptographically strong password
        new_password = _generate_strong_password()
    
    msg = f'Password for {escape(user.email)} has been reset successfully. An email notification has been sent.'
    
    try:
        user.set_password(new_password)
        db.session.commit()
        
        # Send Notification Email asynchronously
        subject = "Security Alert: Your NeuroSent Password Has Been Reset"
        text_body = (
            f"NEUROSENT SECURITY ALERT\n"
            f"========================\n\n"
            f"Hello {user.name},\n\n"
            f"Your password has been reset by an administrator.\n\n"
            f"New Password: {new_password}\n\n"
            f"Please login and change this password immediately.\n"
            f"If you did not request this, contact IT support.\n\n"
            f"-- NeuroSent Security Team"
        )
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5; padding: 40px 0;">
                <tr><td align="center">
                    <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.08);">
                        
                        <!-- Header Banner -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #78350f 0%, #92400e 50%, #b45309 100%); padding: 40px 40px 30px; text-align: center;">
                                <div style="width: 64px; height: 64px; background-color: rgba(255,255,255,0.15); border-radius: 50%; margin: 0 auto 16px; line-height: 64px; font-size: 28px;">&#9888;</div>
                                <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0 0 8px;">Password Reset Notice</h1>
                                <p style="color: #fde68a; font-size: 14px; margin: 0;">NeuroSent Security Alert</p>
                            </td>
                        </tr>
                        
                        <!-- Body -->
                        <tr>
                            <td style="padding: 36px 40px 20px;">
                                <p style="color: #1f2937; font-size: 16px; margin: 0 0 16px;">Hello <strong>{escape(user.name)}</strong>,</p>
                                <p style="color: #4b5563; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                                    Your password for the <strong style="color: #1f2937;">NeuroSent</strong> platform has been reset by a system administrator. Your new credentials are below.
                                </p>
                            </td>
                        </tr>
                        
                        <!-- New Password Box -->
                        <tr>
                            <td style="padding: 0 40px 24px;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                    <tr><td style="background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 12px; padding: 24px; text-align: center;">
                                        <p style="color: #92400e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 12px;">New Password</p>
                                        <p style="font-family: 'Courier New', monospace; font-size: 22px; font-weight: 800; letter-spacing: 2px; color: #1e1b4b; margin: 0;">{new_password}</p>
                                    </td></tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Security Warning -->
                        <tr>
                            <td style="padding: 0 40px 24px;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 0 8px 8px 0; padding: 14px 18px;">
                                    <tr><td>
                                        <p style="color: #991b1b; font-size: 12px; line-height: 1.6; margin: 0;">
                                            &#8226; Change this password immediately after logging in.<br>
                                            &#8226; If you did not request this change, contact IT support immediately.
                                        </p>
                                    </td></tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 12px 40px;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="border-top: 1px solid #e5e7eb;"></td></tr></table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 40px 32px; text-align: center;">
                                <p style="font-size: 12px; color: #9ca3af; margin: 0 0 4px;">&copy; NeuroSent AI Platform. All rights reserved.</p>
                                <p style="font-size: 11px; color: #d1d5db; margin: 0;">Automated security notification</p>
                            </td>
                        </tr>
                        
                    </table>
                </td></tr>
            </table>
        </body>
        </html>
        """
        Thread(target=send_async_email, args=(current_app._get_current_object(), user.email, subject, html_body, text_body)).start()
        
        # Audit log
        entry = AuditLog(user_id=current_user.id, action='admin_reset_password', target=user.email, ip_address=request.remote_addr)
        db.session.add(entry)
        db.session.commit()
        
        flash(msg, 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error resetting password. Please try again.', 'danger')
        
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@login_required
@requires_roles('Admin')
def delete_user(user_id):
    from datetime import datetime
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot deactivate your own admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))
        
    try:
        # Soft delete: set deleted_at instead of removing from DB
        user.deleted_at = datetime.utcnow()
        entry = AuditLog(user_id=current_user.id, action='user_deactivated', target=user.email, ip_address=request.remote_addr)
        db.session.add(entry)
        db.session.commit()
        flash(f'User {user.email} has been deactivated. Their data is preserved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deactivating user. Please try again.', 'danger')
        
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/import-users', methods=['GET', 'POST'])
@login_required
@requires_roles('Admin')
def import_users():
    """Bulk import users from CSV file."""
    
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file selected. Please choose a CSV file.', 'warning')
            return redirect(url_for('admin.import_users'))
        
        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected. Please choose a CSV file.', 'warning')
            return redirect(url_for('admin.import_users'))
        
        if not file.filename.lower().endswith('.csv'):
            flash('Invalid file format. Only .csv files are accepted.', 'danger')
            return redirect(url_for('admin.import_users'))
        
        # Read CSV content
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            
            # Validate required columns
            if not reader.fieldnames:
                flash('CSV file is empty or has no headers.', 'danger')
                return redirect(url_for('admin.import_users'))
                
            # Define aliases for flexible column mapping
            COLUMN_ALIASES = {
                'name': ['name', 'full name', 'fullname', 'username', 'user name', 'student name', 'employee name', 'first name'],
                'email': ['email', 'email address', 'e-mail', 'user email', 'mail', 'email id'],
                'role': ['role', 'user role', 'account type', 'type', 'position', 'user type'],
                'department': ['department', 'dept', 'branch', 'course', 'program', 'department name']
            }
            
            # Map actual CSV headers to standard column names
            col_map = {}
            if not reader.fieldnames:
                flash('Invalid CSV: No headers found.', 'danger')
                return redirect(url_for('admin.import_users'))
                
            for col in reader.fieldnames:
                clean_col = col.strip().lower()
                matched = False
                
                # 1. Try exact alias match
                for standard_name, aliases in COLUMN_ALIASES.items():
                    if clean_col in aliases:
                        col_map[col] = standard_name
                        matched = True
                        break
                        
                # 2. Try partial match as fallback
                if not matched:
                    standard_names = list(COLUMN_ALIASES.keys())
                    for standard_name in standard_names:
                        if standard_name in clean_col:
                            col_map[col] = standard_name
                            matched = True
                            break
                            
                # 3. If no match, keep original
                if not matched:
                    col_map[col] = clean_col
            
            csv_mapped_cols = set(col_map.values())
            required_cols = {'name', 'email', 'role', 'department'}
            
            missing = required_cols - csv_mapped_cols
            if missing:
                flash(f'Missing required columns (or could not auto-map): {", ".join(missing)}. Please check your CSV headers.', 'danger')
                return redirect(url_for('admin.import_users'))
            
            valid_roles = {'Admin', 'HOD', 'Staff', 'Student'}
            imported: int = 0
            skipped_dup: int = 0
            skipped_invalid: int = 0
            errors: list = []
            app_ref = current_app._get_current_object()
            
            for row_num, row in enumerate(reader, start=2):
                # Normalize keys
                normalized = {col_map.get(k, k): (v.strip() if v else '') for k, v in row.items()}
                
                name = normalized.get('name', '')
                email_addr = normalized.get('email', '')
                role = normalized.get('role', '')
                department = normalized.get('department', '')
                
                # Validate non-null
                if not all([name, email_addr, role, department]):
                    skipped_invalid += 1
                    errors.append(f"Row {row_num}: missing required data")
                    continue
                
                # Validate role (case-insensitive match)
                role_matched = None
                for valid_role in valid_roles:
                    if role.lower() == valid_role.lower():
                        role_matched = valid_role
                        break
                
                if not role_matched:
                    skipped_invalid += 1
                    errors.append(f"Row {row_num}: invalid role '{role}'")
                    continue
                
                # Check for duplicate email
                if User.query.filter_by(email=email_addr).first():
                    skipped_dup += 1
                    continue
                
                # Generate password and create user
                password = _generate_strong_password()
                try:
                    new_user = User(name=name, email=email_addr, role=role_matched, department=department)
                    new_user.set_password(password)
                    db.session.add(new_user)
                    db.session.commit()
                    
                    # Send welcome email asynchronously
                    subj, html, text = _build_welcome_email(name, email_addr, password, role_matched)
                    Thread(target=send_async_email, args=(app_ref, email_addr, subj, html, text)).start()
                    
                    imported += 1
                except Exception as e:
                    db.session.rollback()
                    skipped_invalid += 1
                    errors.append(f"Row {row_num}: database error")
            
            # Build summary message
            parts = []
            if imported:
                parts.append(f"✅ {imported} user(s) imported successfully")
            if skipped_dup:
                parts.append(f"⏭ {skipped_dup} skipped (duplicate emails)")
            if skipped_invalid:
                parts.append(f"❌ {skipped_invalid} failed (validation errors)")
            
            summary = " · ".join(parts) if parts else "No users were processed."
            
            if imported > 0:
                flash(summary, 'success')
            elif skipped_dup > 0 and skipped_invalid == 0:
                flash(summary, 'info')
            else:
                flash(summary, 'warning')
            
            if errors:
                error_list: list = errors
                flash("Details: " + "; ".join(error_list[:5]) + (f" ... and {len(error_list)-5} more" if len(error_list) > 5 else ""), 'info')
                
        except UnicodeDecodeError:
            flash('Could not read file. Please ensure the CSV is UTF-8 encoded.', 'danger')
        except Exception as e:
            flash('An unexpected error occurred while processing the CSV file.', 'danger')
        
        return redirect(url_for('admin.import_users'))
    
    return render_template('admin/import_users.html')

@admin_bp.route('/import-users/sample-csv')
@login_required
def sample_csv():
    """Download a sample CSV template for bulk user import."""
    if current_user.role != 'Admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'email', 'role', 'department'])
    writer.writerow(['Jane Doe', 'jane@example.com', 'Student', 'Computer Science'])
    writer.writerow(['John Smith', 'john@example.com', 'Staff', 'Mathematics'])
    writer.writerow(['Dr. Alice', 'alice@example.com', 'HOD', 'Physics'])
    
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=neurosent_import_template.csv'}
    )
    return response

@admin_bp.route('/audit-log')
@login_required
@requires_roles('Admin')
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/audit_log.html', logs=logs)


@admin_bp.route('/feedback/<int:feedback_id>/status', methods=['POST'])
@login_required
@requires_roles('Admin')
def update_feedback_status(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    new_status = request.form.get('status', '').strip()
    
    valid_statuses = {'New', 'Under Review', 'Resolved', 'Dismissed'}
    if new_status not in valid_statuses:
        flash('Invalid status value.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    feedback.status = new_status
    entry = AuditLog(user_id=current_user.id, action='feedback_status_changed', target=f'Feedback #{feedback_id} → {new_status}', ip_address=request.remote_addr)
    db.session.add(entry)
    db.session.commit()
    
    flash(f'Feedback #{feedback_id} status updated to {new_status}.', 'success')
    return redirect(url_for('dashboard.index'))


@admin_bp.route('/feedback/<int:feedback_id>/reply', methods=['POST'])
@login_required
@requires_roles('Admin')
def reply_to_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    message = request.form.get('message', '').strip()
    
    if not message:
        flash('Reply message cannot be empty.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if len(message) > 2000:
        flash('Reply must be under 2000 characters.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    reply = FeedbackReply(feedback_id=feedback_id, admin_id=current_user.id, message=message)
    db.session.add(reply)
    
    entry = AuditLog(user_id=current_user.id, action='feedback_reply', target=f'Feedback #{feedback_id}', ip_address=request.remote_addr)
    db.session.add(entry)
    db.session.commit()
    
    flash('Reply sent successfully.', 'success')
    return redirect(url_for('dashboard.index'))
