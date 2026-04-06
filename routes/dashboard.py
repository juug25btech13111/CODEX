from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import db, Feedback, FeedbackReply
from sqlalchemy import func
from sklearn.feature_extraction.text import TfidfVectorizer
import pandas as pd
from app import limiter

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    # Base query
    query = Feedback.query
    
    # Filter based on role
    if current_user.role == 'Student' or current_user.role == 'Staff':
        query = query.filter_by(user_id=current_user.id)
    elif current_user.role == 'HOD':
        query = query.filter_by(department_category=current_user.department)
    # Admin sees all (no filter needed)

    total_count = query.count()
    
    # Sentiment distribution
    positive = query.filter_by(sentiment='Positive').count()
    negative = query.filter_by(sentiment='Negative').count()
    neutral = query.filter_by(sentiment='Neutral').count()
    
    # Get percentages
    pct_pos = round((positive / total_count * 100) if total_count > 0 else 0, 1)
    pct_neg = round((negative / total_count * 100) if total_count > 0 else 0, 1)
    pct_neu = round((neutral / total_count * 100) if total_count > 0 else 0, 1)

    # Department distribution
    dept_distribution = dict(query.with_entities(
        Feedback.department_category, 
        func.count(Feedback.id)
    ).group_by(Feedback.department_category).all())

    # Get recent feedbacks (admin sees all with eager-loaded author; others see last 10)
    if current_user.role == 'Admin':
        recent_feedback = query.options(
            db.joinedload(Feedback.author)
        ).order_by(Feedback.created_at.desc()).all()
    else:
        recent_feedback = query.order_by(Feedback.created_at.desc()).limit(10).all()

    # Pass the appropriate template based on role
    template_name = 'dashboard/student.html'
    if current_user.role == 'Admin':
        template_name = 'dashboard/admin.html'
    elif current_user.role in ['HOD', 'Staff']:
        template_name = 'dashboard/hod_staff.html'

    return render_template(
        template_name,
        total_count=total_count,
        positive=positive,
        negative=negative,
        neutral=neutral,
        pct_pos=pct_pos,
        pct_neg=pct_neg,
        pct_neu=pct_neu,
        dept_distribution=dept_distribution,
        recent_feedback=recent_feedback
    )

from cachetools import cached, TTLCache

# Cache dashboard stats, keying off role/department and any date filters
dashboard_cache = TTLCache(maxsize=50, ttl=60)

def dashboard_cache_key():
    from flask import request
    role_key = current_user.role if current_user.role in ['Admin', 'Student'] else current_user.department
    return f"{role_key}_{request.args.get('start_date', '')}_{request.args.get('end_date', '')}"

@dashboard_bp.route('/api/dashboard_data')
@login_required
@limiter.limit("30 per minute")
@cached(cache=dashboard_cache, key=dashboard_cache_key)
def get_dashboard_data():
    """
    AJAX endpoint to fetch filtered dashboard statistics based on date ranges
    without reloading the entire page or restarting Vanta.js
    """
    from flask import request
    from datetime import datetime
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = Feedback.query
    if current_user.role == 'Student' or current_user.role == 'Staff':
        query = query.filter_by(user_id=current_user.id)
    elif current_user.role == 'HOD':
        query = query.filter_by(department_category=current_user.department)
        
    try:
        # Apply date filters if provided
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Feedback.created_at >= start_date)
        if end_date_str:
            # Add time to include the whole end date
            end_date = datetime.strptime(f"{end_date_str} 23:59:59", '%Y-%m-%d %H:%M:%S')
            query = query.filter(Feedback.created_at <= end_date)
            
        total_count = query.count()
        positive = query.filter_by(sentiment='Positive').count()
        negative = query.filter_by(sentiment='Negative').count()
        neutral = query.filter_by(sentiment='Neutral').count()
        
        pct_pos = round((positive / total_count * 100) if total_count > 0 else 0, 1)
        pct_neg = round((negative / total_count * 100) if total_count > 0 else 0, 1)
        pct_neu = round((neutral / total_count * 100) if total_count > 0 else 0, 1)
        
        dept_raw = query.with_entities(
            Feedback.department_category, 
            func.count(Feedback.id)
        ).group_by(Feedback.department_category).all()
        
        dept_labels = []
        dept_counts = []
        for name, count in dept_raw:
            dept_labels.append(name if name else "Uncategorized")
            dept_counts.append(count)
            
        return jsonify({
            'success': True,
            'total_count': total_count,
            'positive': positive, 'negative': negative, 'neutral': neutral,
            'pct_pos': pct_pos, 'pct_neg': pct_neg, 'pct_neu': pct_neu,
            'dept_labels': dept_labels,
            'dept_counts': dept_counts
        })
    except Exception as e:
        print(f"AJAX Data Error: {e}")
        return jsonify({'success': False, 'error': 'An internal error occurred. Please try again later.'})



# Cache exactly 10 different keyword results (e.g. for different roles) for up to 60 seconds
keyword_cache = TTLCache(maxsize=10, ttl=60)

@dashboard_bp.route('/api/keywords')
@login_required
@limiter.limit("20 per minute")
@cached(cache=keyword_cache, key=lambda: current_user.role if current_user.role in ['Admin', 'Student'] else current_user.department)
def get_keywords():
    """
    Asynchronous endpoint to extract trending keywords from negative feedback
    using Term Frequency-Inverse Document Frequency (TF-IDF).
    This doesn't block the initial page load.
    The results are cached for 60 seconds to support 500+ concurrent requests.
    """
    # Only analyze negative feedback to find "pain points", or all feedback if preferred.
    # We will analyze all, but you can filter by sentiment='Negative'
    query = Feedback.query
    if current_user.role == 'Student' or current_user.role == 'Staff':
        query = query.filter_by(user_id=current_user.id)
    elif current_user.role == 'HOD':
        query = query.filter_by(department_category=current_user.department)
        
    feedbacks = query.all()
    
    if len(feedbacks) < 5:
        return jsonify({"keywords": []}) # Not enough data
        
    documents = [f.cleaned_text for f in feedbacks if f.cleaned_text]
    
    if not documents:
         return jsonify({"keywords": []})
         
    try:
        # Extract top 30 meaningful words, ignoring standard english stop words
        vectorizer = TfidfVectorizer(stop_words='english', max_features=30)
        tfidf_matrix = vectorizer.fit_transform(documents)
        
        # Sum the TF-IDF scores for each word across all documents
        word_scores = tfidf_matrix.sum(axis=0).A1
        words = vectorizer.get_feature_names_out()
        
        # wordcloud2.js expects an array of [word, size] arrays.
        # We multiply the TF-IDF score by a factor (e.g., 20) to make the font size visually impactful
        keywords = []
        for word, score in zip(words, word_scores):
            # Scale score for visual size mapping, ensure minimum size
            size = max(float(score) * 20, 10) 
            keywords.append([str(word), size])
            
        # Sort by size descending
        keywords.sort(key=lambda x: x[1], reverse=True)
        
        return jsonify({"keywords": keywords})
    except Exception as e:
        print(f"Keyword UI error: {e}")
        return jsonify({"keywords": []})
