from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Feedback, AuditLog
import re

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/', methods=['GET'])
@login_required
def index():
    total_feedbacks = Feedback.query.filter_by(user_id=current_user.id).count()
    
    avg_score = 0
    if total_feedbacks > 0:
        feedbacks = Feedback.query.filter_by(user_id=current_user.id).all()
        total_score = sum(f.sentiment_score for f in feedbacks)
        avg_score = round(total_score / total_feedbacks, 2)
        
    return render_template(
        'dashboard/profile.html',
        total_feedbacks=total_feedbacks,
        avg_score=avg_score
    )

@profile_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        flash('All password fields are required.', 'danger')
        return redirect(url_for('profile.index'))
    
    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('profile.index'))
    
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('profile.index'))
    
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'danger')
        return redirect(url_for('profile.index'))
    if not any(c.isdigit() for c in new_password) or not any(c.isalpha() for c in new_password):
        flash('New password must contain both letters and numbers.', 'danger')
        return redirect(url_for('profile.index'))
    
    current_user.set_password(new_password)
    
    # Audit log
    entry = AuditLog(user_id=current_user.id, action='password_changed', ip_address=request.remote_addr)
    db.session.add(entry)
    db.session.commit()
    
    flash('Password changed successfully.', 'success')
    return redirect(url_for('profile.index'))
