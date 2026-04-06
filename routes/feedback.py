from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from markupsafe import escape
from models import db, Feedback, User
from utils.nlp_utils import preprocess_text, analyze_sentiment, is_college_context, detect_risk_content
from app import limiter
from utils.email_utils import send_smtp_email
from datetime import datetime

feedback_bp = Blueprint('feedback', __name__)

def _build_risk_alert_email(original_text, sentiment, score, risk_categories, department, source_type, submitter_name=None, submitter_id=None):
    """Build the enterprise-grade risk alert email with full metadata."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    risk_badges = ', '.join(risk_categories)
    safe_text = escape(original_text)
    safe_dept = escape(department) if department else 'N/A'
    safe_name = escape(submitter_name) if submitter_name else 'Unknown'
    
    subject = f'🚨 URGENT: High-Risk Feedback Detected [{risk_badges}] - NeuroSent'
    
    text_content = (
        f"NEUROSENT HIGH-RISK ALERT\n"
        f"=========================\n\n"
        f"Timestamp: {timestamp}\n"
        f"Risk Categories: {risk_badges}\n"
        f"Sentiment: {sentiment} (Score: {score:.2f})\n"
        f"Source: {source_type}\n"
        f"Submitted By: {safe_name} (ID: {submitter_id})\n"
        f"Department: {safe_dept}\n\n"
        f"Original Feedback:\n\"{original_text}\"\n\n"
        f"IMMEDIATE ACTION REQUIRED. Please review in the admin dashboard.\n\n"
        f"-- NeuroSent Risk Detection System"
    )
    
    # Build risk category badges HTML
    badge_html = ''
    category_colors = {
        'Bullying & Ragging': ('#fef2f2', '#dc2626', '#991b1b'),
        'Harassment & Abuse': ('#fdf2f8', '#db2777', '#9d174d'),
        'Violence & Assault': ('#fef2f2', '#ef4444', '#7f1d1d'),
        'Safety & Threats': ('#fffbeb', '#f59e0b', '#92400e'),
        'Mental Health & Self-Harm': ('#f5f3ff', '#8b5cf6', '#5b21b6'),
        'Discrimination': ('#fff7ed', '#f97316', '#9a3412'),
        'Corruption & Misconduct': ('#f0fdf4', '#22c55e', '#166534'),
    }
    
    for cat in risk_categories:
        bg, border, text_col = category_colors.get(cat, ('#f3f4f6', '#6b7280', '#374151'))
        badge_html += f'<span style="display: inline-block; padding: 4px 12px; margin: 2px 4px; background-color: {bg}; border: 1px solid {border}; border-radius: 20px; font-size: 11px; font-weight: 700; color: {text_col}; text-transform: uppercase; letter-spacing: 1px;">{cat}</span>'
    
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
                        <td style="background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 50%, #dc2626 100%); padding: 40px 40px 30px; text-align: center;">
                            <div style="width: 64px; height: 64px; background-color: rgba(255,255,255,0.15); border-radius: 50%; margin: 0 auto 16px; line-height: 64px; font-size: 28px;">&#128680;</div>
                            <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0 0 8px;">High-Risk Feedback Detected</h1>
                            <p style="color: #fecaca; font-size: 14px; margin: 0;">Immediate Review Required</p>
                        </td>
                    </tr>
                    
                    <!-- Risk Categories -->
                    <tr>
                        <td style="padding: 24px 40px 12px;">
                            <p style="color: #6b7280; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 10px;">Detected Risk Categories</p>
                            {badge_html}
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding: 20px 40px 20px;">
                            <p style="color: #4b5563; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                                The NeuroSent AI engine has flagged feedback containing <strong style="color: #dc2626;">high-risk content</strong>. Please review this immediately.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Metadata -->
                    <tr>
                        <td style="padding: 0 40px 20px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px;">
                                <tr><td>
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px; width: 140px;">Timestamp</td>
                                            <td style="padding: 6px 0; color: #111827; font-size: 14px; font-weight: 600;">{timestamp}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px;">Sentiment</td>
                                            <td style="padding: 6px 0; font-size: 14px; font-weight: 700; color: #dc2626;">{sentiment} ({score:.2f})</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px;">Source</td>
                                            <td style="padding: 6px 0; color: #111827; font-size: 14px;">{source_type}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px;">Submitted By</td>
                                            <td style="padding: 6px 0; color: #111827; font-size: 14px; font-weight: 600;">{safe_name} (ID: {submitter_id})</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; color: #6b7280; font-size: 13px;">Department</td>
                                            <td style="padding: 6px 0; color: #111827; font-size: 14px;">{safe_dept}</td>
                                        </tr>
                                    </table>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Quoted Text -->
                    <tr>
                        <td style="padding: 0 40px 24px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 0 8px 8px 0;">
                                <tr><td style="padding: 16px 20px;">
                                    <p style="color: #991b1b; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 10px;">Original Feedback</p>
                                    <p style="color: #374151; font-size: 14px; line-height: 1.7; margin: 0; font-style: italic;">"{safe_text}"</p>
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
                            <p style="font-size: 11px; color: #d1d5db; margin: 0;">Automated risk detection alert</p>
                        </td>
                    </tr>
                    
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """
    
    return subject, html_content, text_content


@feedback_bp.route('/submit', methods=['GET', 'POST'])
@login_required
@limiter.limit("5 per minute") # Prevent users/bots from spamming the RoBERTa pipeline
def submit():
    if request.method == 'POST':
        original_text = request.form.get('text')
        department = request.form.get('department') or current_user.department
        is_anonymous = request.form.get('anonymous') == 'on' and current_user.role != 'Admin'
        
        if not original_text:
            flash('Comment cannot be empty.', 'danger')
            return redirect(url_for('feedback.submit'))
        
        # Input validation: prevent DoS with very long text payloads
        if len(original_text) > 10000:
            flash('Feedback text exceeds maximum allowed length (10,000 characters).', 'danger')
            return redirect(url_for('feedback.submit'))
            
        if not is_college_context(original_text):
            flash('Please provide feedback relevant to the college, staff, or coursework.', 'danger')
            return redirect(url_for('feedback.submit'))
        
        # Preprocess for storage / keyword extraction
        cleaned_text = preprocess_text(original_text)
        
        # CRITICAL FIX: Analyze sentiment on the ORIGINAL text, not the
        # preprocessed version. Preprocessing strips negation words like
        # "not", "no", "never" which are essential for accurate sentiment.
        sentiment, score = analyze_sentiment(original_text)
        
        new_feedback = Feedback(
            user_id=None if is_anonymous else current_user.id,
            original_text=original_text,
            cleaned_text=cleaned_text,
            sentiment=sentiment,
            sentiment_score=score,
            department_category=department,
            is_anonymous=is_anonymous
        )
        
        db.session.add(new_feedback)
        db.session.commit()
        
        # NEW: Risk content detection — independent of sentiment label
        risk_categories = detect_risk_content(original_text)
        if risk_categories:
            try:
                admin = User.query.filter_by(role='Admin').first()
                if admin and admin.email:
                    subject, html_content, text_content = _build_risk_alert_email(
                        original_text=original_text,
                        sentiment=sentiment,
                        score=score,
                        risk_categories=risk_categories,
                        department=department,
                        source_type='Manual Input',
                        submitter_name=current_user.name,
                        submitter_id=current_user.id
                    )
                    send_smtp_email(admin.email, subject, html_content, text_content, priority="high")
            except Exception as e:
                print(f"Failed to send risk alert email: {e}")
                pass
        
        flash('Feedback submitted successfully. Thank you!', 'success')
        return redirect(url_for('dashboard.index'))
        
    return render_template('feedback/submit.html')
