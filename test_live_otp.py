import re


def get_csrf_token(html):
    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', html)
    if not match:
        match = re.search(r'name="csrf_token".*?value="([^"]+)"', html)
    return match.group(1) if match else None


def test_otp_flow():
    from app import create_app
    from models import db, User, PasswordResetOTP

    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        db.create_all()

        # Seed test user
        if not User.query.filter_by(email="hogiicont@gmail.com").first():
            u = User(name="Test Student", email="hogiicont@gmail.com", role="Student", department="CSE")
            u.set_password("OldPassword123!")
            db.session.add(u)
            db.session.commit()

    print("1. Requesting password reset page...")
    with app.test_client() as client:
        r = client.get("/recovery/forgot_password")
        if r.status_code != 200:
            print(f"Failed to load forgot_password page: {r.status_code}")
            return False

        csrf_token = get_csrf_token(r.data.decode('utf-8'))

        print("2. Submitting forgot password form...")
        r = client.post("/recovery/forgot_password", data={
            "csrf_token": csrf_token,
            "email": "hogiicont@gmail.com"
        }, follow_redirects=True)

        print(f"Forgot password response: {r.status_code}")

        print("3. Querying database for generated OTP...")
        with app.app_context():
            user = User.query.filter_by(email="hogiicont@gmail.com").first()
            if not user:
                print("User not found in DB!")
                return False

            otp_record = PasswordResetOTP.query.filter_by(
                user_id=user.id, is_used=False
            ).order_by(PasswordResetOTP.id.desc()).first()
            if not otp_record:
                print("No OTP generated in DB!")
                return False

            otp_code = otp_record.otp
            print(f"Found OTP in DB: {otp_code}")

        print("4. Testing OTP verification page...")
        r = client.get("/recovery/verify_otp")
        csrf_token = get_csrf_token(r.data.decode('utf-8'))

        r = client.post("/recovery/verify_otp", data={
            "csrf_token": csrf_token,
            "otp": otp_code
        }, follow_redirects=True)
        response_text = r.data.decode('utf-8')

        if "Create your new password" not in response_text and "/reset_password" not in r.request.path:
            print("Failed to verify OTP!")
            print(response_text[:500])
            return False

        print("5. Submitting new password...")
        r = client.get("/recovery/reset_password")
        csrf_token = get_csrf_token(r.data.decode('utf-8'))

        r = client.post("/recovery/reset_password", data={
            "csrf_token": csrf_token,
            "password": "NewLiveDataPass123",
            "confirm_password": "NewLiveDataPass123"
        }, follow_redirects=True)
        response_text = r.data.decode('utf-8')

        if "Your password has been securely updated" in response_text or "/login" in r.request.path:
            print("SUCCESS! Password reset flow works end-to-end.")
            return True
        else:
            print("Failed to reset password.")
            print(response_text[:500])
            return False


if __name__ == "__main__":
    test_otp_flow()

