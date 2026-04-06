"""
SQLite Database Backup Script
Creates a timestamped copy of the database file in a backups/ directory.
Usage: python scripts/backup_db.py
"""
import os
import shutil
from datetime import datetime

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_path = os.path.join(basedir, 'sentiment.sqlite')
backup_dir = os.path.join(basedir, 'backups')

def backup():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False

    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'sentiment_backup_{timestamp}.sqlite')
    
    shutil.copy2(db_path, backup_path)
    
    # Keep only the 10 most recent backups
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.sqlite')],
        reverse=True
    )
    for old_backup in backups[10:]:
        os.remove(os.path.join(backup_dir, old_backup))
        print(f"Removed old backup: {old_backup}")
    
    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"Backup created: {backup_path} ({size_mb:.2f} MB)")
    return True

if __name__ == '__main__':
    backup()
