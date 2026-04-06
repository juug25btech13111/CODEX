import os
import pandas as pd
import threading
from werkzeug.utils import secure_filename
from utils.nlp_utils import preprocess_text, analyze_sentiment, analyze_sentiment_batch, is_college_context, detect_risk_content
from models import db, Feedback, Upload
from flask import current_app

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def identify_text_column(df):
    """
    Heuristic to find the column most likely containing the feedback text.
    Looks for keywords or selects the column with the longest average string length.
    """
    # Lowercase column names for easier checking
    col_names = [str(c).lower().strip() for c in df.columns]
    
    # Expanded heuristic matching for academic, social media, and product reviews
    keywords = [
        'review_text', 'feedback_text', 'text', 'feedback', 'review', 
        'comment', 'description', 'message', 'body', 'content', 'tweet', 'post'
    ]
    for kw in keywords:
        for i, col in enumerate(col_names):
            if kw == col or kw in col:
                return df.columns[i]
    
    # Fallback: Find column with string type and highest max length
    text_cols = df.select_dtypes(include=['object', 'string']).columns
    if len(text_cols) == 0:
        return None
        
    max_len_col = text_cols[0]
    max_len = 0
    
    for col in text_cols:
        # Get mean length of strings in this column (sample first 50 rows for speed)
        avg_len = df[col].astype(str).head(50).apply(len).mean()
        if avg_len > max_len:
            max_len = avg_len
            max_len_col = col
            
    return max_len_col


def process_uploaded_file_async(app, filepath, upload_record_id, user_id, selected_column=None):
    """
    Background worker function that runs outside the active request thread.
    Processes CSV/Excel files through the full NLP pipeline.
    """
    with app.app_context():
        try:
            # Determine source type for alert metadata
            file_ext = os.path.splitext(filepath)[1].lower()
            if file_ext == '.csv':
                source_type = 'CSV Upload'
            elif file_ext in ('.xls', '.xlsx'):
                source_type = 'Excel Upload'
            else:
                source_type = 'File Upload'
            
            # Read file
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath)
            elif filepath.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(filepath)
            else:
                _mark_upload_status(upload_record_id, 'Failed', "Unsupported file format")
                return

            if df.empty:
                _mark_upload_status(upload_record_id, 'Failed', "The uploaded file is empty")
                return

            # Determine target text column
            text_col = selected_column if selected_column and selected_column in df.columns else identify_text_column(df)
            if not text_col:
                _mark_upload_status(upload_record_id, 'Failed', "Could not identify a text column")
                return

            # Look for a department/category column if it exists
            dept_col = None
            dept_keywords = [
                'department', 'category', 'product', 'dept', 'course', 
                'branch', 'faculty', 'subject', 'program', 'unit'
            ]
            for col in df.columns:
                if any(kw in str(col).lower().strip() for kw in dept_keywords):
                    dept_col = col
                    break

            # Drop NA from the text column to avoid processing empties
            df = df.dropna(subset=[text_col])
            
            # FIX: Accept ALL non-empty rows from uploads.
            # Previously, is_college_context() filtered out valid facility feedback.
            # For bulk uploads, we trust that the admin is uploading relevant data.
            valid_rows = []
            for index, row in df.iterrows():
                orig_text = str(row[text_col])
                if orig_text.strip() and orig_text.lower() != 'nan':
                    valid_rows.append(row)
                    
            df = pd.DataFrame(valid_rows, columns=df.columns) if valid_rows else pd.DataFrame(columns=df.columns)
            total_rows = len(df)
            
            # Update upload tally to track maximum valid rows early
            upload_record = Upload.query.get(upload_record_id)
            if upload_record:
                upload_record.total_rows = total_rows
                db.session.commit()

            feedbacks = []
            alerts_to_send = []
            
            # Get batch size from config (default 15)
            batch_size = current_app.config.get('OPENROUTER_BATCH_SIZE', 15)
            
            # Collect rows into batches for efficient API usage
            rows_list = list(df.iterrows())
            
            for batch_start in range(0, len(rows_list), batch_size):
                batch_rows = rows_list[batch_start:batch_start + batch_size]
                batch_texts = [str(row[text_col]) for _, row in batch_rows]
                
                # Batch sentiment analysis — uses API if available, falls back to local
                batch_results = analyze_sentiment_batch(batch_texts)
                
                for i, (_, row) in enumerate(batch_rows):
                    orig_text = batch_texts[i]
                    sentiment, score = batch_results[i]
                    
                    # Preprocess for storage / keyword extraction
                    cleaned_text = preprocess_text(orig_text)
                    
                    department = str(row[dept_col]) if dept_col and pd.notna(row[dept_col]) else None
                    
                    feedback = Feedback(
                        user_id=user_id,
                        upload_id=upload_record_id,
                        original_text=orig_text,
                        cleaned_text=cleaned_text,
                        sentiment=sentiment,
                        sentiment_score=score,
                        department_category=department
                    )
                    feedbacks.append(feedback)
                    
                    # Risk detection decoupled from sentiment (runs locally, no API)
                    risk_categories = detect_risk_content(orig_text)
                    if risk_categories:
                        alerts_to_send.append({
                            "text": orig_text,
                            "score": score,
                            "sentiment": sentiment,
                            "department": department,
                            "risk_categories": risk_categories,
                        })
                
                # Commit after each batch to show live progress and conserve memory
                if feedbacks:
                    db.session.bulk_save_objects(feedbacks)
                    upload_record = Upload.query.get(upload_record_id)
                    if upload_record:
                        upload_record.processed_rows += len(feedbacks)
                    db.session.commit()
                    feedbacks = []
                    
            # Fire all emergency alerts collected in this batch
            if alerts_to_send:
                from models import User
                from utils.email_utils import send_smtp_email
                from markupsafe import escape
                from datetime import datetime
                
                admin = User.query.filter_by(role='Admin').first()
                if admin and admin.email:
                    try:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        subject = f'🚨 URGENT: {len(alerts_to_send)} High-Risk Feedbacks in {source_type} - NeuroSent'
                        
                        body = (
                            f"NEUROSENT BULK RISK ALERT\n"
                            f"=========================\n\n"
                            f"Timestamp: {timestamp}\n"
                            f"Source: {source_type} (Upload ID: {upload_record_id})\n"
                            f"Total Risk Alerts: {len(alerts_to_send)}\n\n"
                        )
                        
                        html_body = f"""
                        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: auto;">
                            <div style="background: linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%); padding: 30px; border-radius: 16px 16px 0 0; text-align: center;">
                                <div style="width: 48px; height: 48px; background-color: rgba(255,255,255,0.15); border-radius: 50%; margin: 0 auto 12px; line-height: 48px; font-size: 22px;">&#128680;</div>
                                <h2 style="color: #ffffff; margin: 0 0 6px; font-size: 20px;">Bulk Risk Alert</h2>
                                <p style="color: #fecaca; margin: 0; font-size: 13px;">{len(alerts_to_send)} critical items from {source_type}</p>
                            </div>
                            <div style="background-color: #ffffff; padding: 24px; border: 1px solid #e5e7eb; border-radius: 0 0 16px 16px;">
                                <p style="color: #6b7280; font-size: 12px; margin: 0 0 6px;">Upload ID: {upload_record_id} &bull; {timestamp}</p>
                        """
                        
                        # Limit to first 10 to avoid email size limits
                        alert_list = list(alerts_to_send)
                        alert_subset = alert_list[:10]
                        for idx, alert in enumerate(alert_subset):
                            risk_badges = ', '.join(alert['risk_categories'])
                            safe_alert_text = escape(str(alert['text']))
                            
                            body += f"--- Alert {idx+1} ---\n"
                            body += f"Risk: {risk_badges}\n"
                            body += f"Sentiment: {alert['sentiment']} ({alert['score']:.2f})\n"
                            body += f"Text: '{alert['text']}'\n\n"
                            
                            html_body += f"""
                            <div style="background-color: #fef2f2; padding: 14px 16px; border-left: 4px solid #ef4444; margin: 12px 0; border-radius: 0 8px 8px 0;">
                                <p style="margin: 0 0 4px; font-size: 11px; color: #dc2626; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">⚠ {risk_badges}</p>
                                <p style="margin: 0 0 4px; font-size: 12px; color: #6b7280;">Sentiment: {alert['sentiment']} ({alert['score']:.2f})</p>
                                <p style="margin: 0; font-size: 14px; color: #374151; font-style: italic;">"{safe_alert_text}"</p>
                            </div>
                            """
                            
                        if len(alerts_to_send) > 10:
                            remaining = len(alerts_to_send) - 10
                            body += f"\n...and {remaining} more. Please review the dashboard immediately.\n"
                            html_body += f"<p style='color: #6b7280; font-size: 13px; margin: 16px 0 0;'>...and {remaining} more. Please review the dashboard immediately.</p>"
                            
                        html_body += """
                                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0 12px;">
                                <p style="font-size: 11px; color: #9ca3af; text-align: center; margin: 0;">&copy; NeuroSent AI Platform &bull; Automated risk detection alert</p>
                            </div>
                        </div>
                        """
                            
                        send_smtp_email(admin.email, subject, html_body, body, priority="high")
                    except Exception as e:
                        print(f"Failed to send bulk risk alert email: {e}")
                        pass

            # Save remaining
            if feedbacks:
                db.session.bulk_save_objects(feedbacks)
                upload_record = Upload.query.get(upload_record_id)
                if upload_record:
                    upload_record.processed_rows += len(feedbacks)
                db.session.commit()

            # Mark as totally completed
            upload_record = Upload.query.get(upload_record_id)
            if upload_record:
                upload_record.status = 'Completed'
                db.session.commit()

        except Exception as e:
            db.session.rollback()
            _mark_upload_status(upload_record_id, 'Failed', str(e))

def _mark_upload_status(upload_id, status, error_msg=None):
    upload_record = Upload.query.get(upload_id)
    if upload_record:
        upload_record.status = status
        db.session.commit()
        if error_msg:
            print(f"Upload {upload_id} failed: {error_msg}")

def process_uploaded_file(filepath, upload_record_id, user_id, selected_column=None):
    """
    Entry point for the web route. Instantly spawns a background thread and returns to not block the browser.
    """
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=process_uploaded_file_async,
        args=(app, filepath, upload_record_id, user_id, selected_column)
    )
    thread.daemon = True # Allows server to shut down freely
    thread.start()
    
    return True, "File uploaded successfully. Neural Network is processing rows in the background!"
