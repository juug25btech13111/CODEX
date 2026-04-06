"""
Data Retention Purge Script
Deletes feedback records older than a configurable number of days.
Usage: python scripts/purge_old_data.py --days 1095  (default: 3 years)
"""
import sys
import os
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import db, Feedback

def purge_old_feedback(days):
    app = create_app()
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=days)
        old_count = Feedback.query.filter(Feedback.created_at < cutoff).count()
        
        if old_count == 0:
            print(f"No feedback records older than {days} days found. Nothing to purge.")
            return
        
        confirm = input(f"Found {old_count} feedback records older than {days} days ({cutoff.strftime('%Y-%m-%d')}). Delete? [y/N]: ")
        if confirm.lower() != 'y':
            print("Purge cancelled.")
            return
        
        Feedback.query.filter(Feedback.created_at < cutoff).delete()
        db.session.commit()
        print(f"Successfully purged {old_count} feedback records.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Purge old feedback data')
    parser.add_argument('--days', type=int, default=1095, help='Delete records older than N days (default: 1095 = ~3 years)')
    args = parser.parse_args()
    purge_old_feedback(args.days)
