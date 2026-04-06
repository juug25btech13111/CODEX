import os
from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    print("Dropping all existing tables...")
    db.drop_all()
    print("Creating all tables based on new models...")
    db.create_all()
    
    print("Seeding default Admin user...")
    admin = User(
        name="System Admin",
        email="mathasenquiry@gmail.com",
        role="Admin",
        department="System Operations",
        is_verified=True
    )
    admin.set_password("Admin@2026")
    db.session.add(admin)
    db.session.commit()
    print("Database reset successfully! Default admin created (mathasenquiry@gmail.com / Admin@2026).")
