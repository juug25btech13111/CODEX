import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Upload, Feedback
from utils.file_processor import allowed_file, process_uploaded_file
from utils.decorators import requires_roles
import mimetypes

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/', methods=['GET', 'POST'])
@login_required
@requires_roles('Admin', 'HOD', 'Staff')
def index():
    if request.method == 'POST':
        if 'dataset' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url)
            
        file = request.files['dataset']
        if file.filename == '':
            flash('No selected file.', 'danger')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            # File MIME type validation
            allowed_mimes = {
                'text/csv', 'application/csv',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
            mime_type = mimetypes.guess_type(file.filename)[0]
            if mime_type and mime_type not in allowed_mimes:
                flash('File content type is not allowed. Only CSV and Excel files are accepted.', 'danger')
                return redirect(request.url)
            
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Validate file size after save (defense in depth)
            file_size = os.path.getsize(filepath)
            if file_size > current_app.config['MAX_CONTENT_LENGTH']:
                os.remove(filepath)
                flash('File exceeds maximum allowed size (16 MB).', 'danger')
                return redirect(request.url)
            
            # Create an upload record
            new_upload = Upload(user_id=current_user.id, filename=filename, status='Processing')
            db.session.add(new_upload)
            db.session.commit()
            
            # Process the file (Synchronous for now, ideally background task like Celery)
            selected_column = request.form.get('text_column')
            success, message = process_uploaded_file(filepath, new_upload.id, current_user.id, selected_column)
            
            if success:
                flash(message, 'success')
            else:
                flash(f"Error processing file: {message}", 'danger')
                
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid file type. Allowed: .csv, .xls, .xlsx', 'danger')
            
    # GET: View all past uploads
    uploads = Upload.query.order_by(Upload.upload_date.desc()).all()
    return render_template('upload/index.html', uploads=uploads)

@upload_bp.route('/delete/<int:upload_id>', methods=['POST'])
@login_required
@requires_roles('Admin')
def delete_upload(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    # The Feedbacks associated will be cascade deleted based on DB schema model
    db.session.delete(upload)
    db.session.commit()
    flash('Upload and associated feedbacks deleted successfully.', 'success')
    return redirect(url_for('upload.index'))
