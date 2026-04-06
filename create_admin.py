from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    # Check if admin exists
    admin_user = User.query.filter_by(role='Admin').first()
    
    if not admin_user:
        print("Creating default admin account...")
        admin = User(name="System Administrator", email="mathasenquiry@gmail.com", role="Admin", department="IT", is_verified=True)
        admin.set_password("Admin@2026")
        db.session.add(admin)
        db.session.commit()
        print("Admin account created! Email: mathasenquiry@gmail.com | Pass: Admin@2026")
    else:
        # Update existing admin password to be sure
        print(f"Admin already exists: {admin_user.email}")
        admin_user.set_password("Admin@2026")
        admin_user.is_verified = True
        db.session.commit()
        print("Admin password reset to: Admin@2026")
