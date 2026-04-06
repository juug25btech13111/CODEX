import os
import sys
import json
import subprocess
from flask import Blueprint, render_template, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.decorators import requires_roles
from app import limiter

training_bp = Blueprint('training', __name__)

STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "training_status.json")
TRAIN_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "train_model.py")
CUSTOM_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_model")

@training_bp.route('/training')
@login_required
@requires_roles('Admin')
def index():
    
    # Check if a custom model already exists
    has_custom = os.path.exists(CUSTOM_MODEL_DIR)
    
    return render_template('admin/training.html', has_custom=has_custom)

@training_bp.route('/training/start', methods=['POST'])
@login_required
@requires_roles('Admin')
@limiter.limit("3 per hour")
def start_training():
        
    # Reset the status file
    with open(STATUS_FILE, "w") as f:
        json.dump({"status": "Initializing", "progress": 0, "message": "Starting background trainer..."}, f)
        
    # Launch training script as an asynchronous subprocess
    try:
        # Use python executable from sys or environment
        subprocess.Popen([sys.executable, TRAIN_SCRIPT], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@training_bp.route('/training/status')
@login_required
@requires_roles('Admin')
def check_status():
        
    if not os.path.exists(STATUS_FILE):
        return jsonify({"status": "Idle", "progress": 0, "message": "Waiting to start..."})
        
    try:
        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception:
        return jsonify({"status": "Error", "progress": 0, "message": "Could not read status file."})
