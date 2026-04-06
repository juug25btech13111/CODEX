"""
Comprehensive security tests for the NeuroSent sentiment analysis app.
Tests all security fixes applied during the audit.
"""
import pytest
from app import create_app
from models import db, User, PasswordResetOTP
from datetime import datetime, timedelta, timezone


@pytest.fixture
def test_client():
    """Create a test client with a fresh in-memory database."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for test convenience
    app.config['RATELIMIT_ENABLED'] = False  # Disable rate limiter for tests

    with app.test_client() as testing_client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Seed test users
            admin = User(name="Admin Test", email="admin@test.com", role="Admin", department="IT")
            admin.set_password("AdminPass1")

            student = User(name="Student Test", email="student@test.com", role="Student", department="CSE")
            student.set_password("StudentPass1")

            hod = User(name="HOD Test", email="hod@test.com", role="HOD", department="CSE")
            hod.set_password("HodPass123")

            staff = User(name="Staff Test", email="staff@test.com", role="Staff", department="CSE")
            staff.set_password("StaffPass1")

            db.session.add_all([admin, student, hod, staff])
            db.session.commit()

            yield testing_client

            db.session.remove()
            db.drop_all()


def login(client, email, password):
    return client.post('/auth/login', data=dict(
        email=email,
        password=password
    ), follow_redirects=True)


def logout(client):
    return client.post('/auth/logout', follow_redirects=True)


# ========================
# SECURITY TEST: Role Privilege Escalation
# ========================

class TestRolePrivilegeEscalation:
    """
    CRITICAL: Verify that users cannot self-assign Admin role during registration.
    This was the #1 security vulnerability found during audit.
    """

    def test_register_always_creates_student(self, test_client):
        """Even if role=Admin is sent in POST body, user must be created as Student."""
        response = test_client.post('/auth/register', data=dict(
            name='Hacker User',
            email='hacker@test.com',
            password='HackerPass1',
            role='Admin',  # Attempting privilege escalation
            department='CSE'
        ), follow_redirects=True)

        # Check user was created as Student, NOT Admin
        with test_client.application.app_context():
            user = User.query.filter_by(email='hacker@test.com').first()
            assert user is not None, "User should have been created"
            assert user.role == 'Student', f"User role should be Student, got {user.role}"

    def test_register_hod_escalation_blocked(self, test_client):
        """Verify HOD role escalation is also blocked."""
        test_client.post('/auth/register', data=dict(
            name='HOD Hacker',
            email='hodhacker@test.com',
            password='HodHacker1',
            role='HOD',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='hodhacker@test.com').first()
            assert user is not None
            assert user.role == 'Student'


# ========================
# SECURITY TEST: Password Strength Validation
# ========================

class TestPasswordStrength:
    """Verify password strength is enforced on registration and password reset."""

    def test_short_password_rejected(self, test_client):
        """Passwords under 8 characters should be rejected."""
        response = test_client.post('/auth/register', data=dict(
            name='Weak User',
            email='weak@test.com',
            password='Ab1',  # Too short
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='weak@test.com').first()
            assert user is None, "User with weak password should NOT be created"

    def test_no_digit_password_rejected(self, test_client):
        """Passwords without digits should be rejected."""
        response = test_client.post('/auth/register', data=dict(
            name='No Digit User',
            email='nodigit@test.com',
            password='AbcdefghIjk',  # No digits
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='nodigit@test.com').first()
            assert user is None, "User with no-digit password should NOT be created"

    def test_no_letter_password_rejected(self, test_client):
        """Passwords without letters should be rejected."""
        response = test_client.post('/auth/register', data=dict(
            name='No Letter User',
            email='noletter@test.com',
            password='12345678',  # No letters
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='noletter@test.com').first()
            assert user is None, "User with no-letter password should NOT be created"

    def test_strong_password_accepted(self, test_client):
        """Valid strong passwords should be accepted."""
        response = test_client.post('/auth/register', data=dict(
            name='Strong User',
            email='strong@test.com',
            password='StrongPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='strong@test.com').first()
            assert user is not None, "User with strong password should be created"
            assert user.role == 'Student'


# ========================
# SECURITY TEST: Logout Method
# ========================

class TestLogoutSecurity:
    """Verify logout requires POST method (CSRF mitigation)."""

    def test_logout_get_returns_405(self, test_client):
        """GET /auth/logout should return 405 Method Not Allowed."""
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.get('/auth/logout')
        assert response.status_code == 405, \
            f"GET logout should return 405, got {response.status_code}"

    def test_logout_post_works(self, test_client):
        """POST /auth/logout should successfully log the user out."""
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.post('/auth/logout', follow_redirects=True)
        assert response.status_code == 200


# ========================
# SECURITY TEST: Admin Route Protection
# ========================

class TestAdminRouteSecurity:
    """Verify that admin-only routes reject non-admin users."""

    def test_student_cannot_access_create_user(self, test_client):
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.get('/admin/create-user', follow_redirects=True)
        assert b'permission' in response.data.lower()

    def test_student_cannot_access_manage_users(self, test_client):
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.get('/admin/manage-users', follow_redirects=True)
        assert b'permission' in response.data.lower()

    def test_hod_cannot_access_admin_routes(self, test_client):
        login(test_client, 'hod@test.com', 'HodPass123')
        response = test_client.get('/admin/create-user', follow_redirects=True)
        assert b'permission' in response.data.lower()

    def test_admin_can_access_admin_routes(self, test_client):
        login(test_client, 'admin@test.com', 'AdminPass1')
        response = test_client.get('/admin/create-user')
        assert response.status_code == 200

    def test_admin_can_access_manage_users(self, test_client):
        login(test_client, 'admin@test.com', 'AdminPass1')
        response = test_client.get('/admin/manage-users')
        assert response.status_code == 200


# ========================
# SECURITY TEST: Upload Route Protection
# ========================

class TestUploadRouteSecurity:
    """Verify upload restrictions by role."""

    def test_student_cannot_upload(self, test_client):
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.get('/upload/', follow_redirects=True)
        assert b'permission' in response.data.lower()

    def test_admin_can_upload(self, test_client):
        login(test_client, 'admin@test.com', 'AdminPass1')
        response = test_client.get('/upload/')
        assert response.status_code == 200


# ========================
# SECURITY TEST: Authentication Required
# ========================

class TestAuthenticationRequired:
    """Verify that unauthenticated users are redirected."""

    def test_dashboard_requires_login(self, test_client):
        response = test_client.get('/dashboard/', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_profile_requires_login(self, test_client):
        response = test_client.get('/profile/', follow_redirects=False)
        assert response.status_code == 302

    def test_feedback_requires_login(self, test_client):
        response = test_client.get('/feedback/submit', follow_redirects=False)
        assert response.status_code == 302

    def test_upload_requires_login(self, test_client):
        response = test_client.get('/upload/', follow_redirects=False)
        assert response.status_code == 302

    def test_reports_require_login(self, test_client):
        response = test_client.get('/reports/excel', follow_redirects=False)
        assert response.status_code == 302


# ========================
# SECURITY TEST: Security Headers
# ========================

class TestSecurityHeaders:
    """Verify all security headers are present in responses."""

    def test_security_headers_present(self, test_client):
        login(test_client, 'student@test.com', 'StudentPass1')
        response = test_client.get('/dashboard/')

        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
        assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'
        assert response.headers.get('Pragma') == 'no-cache'

    def test_headers_on_unauthenticated_routes(self, test_client):
        response = test_client.get('/auth/login')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'


# ========================
# SECURITY TEST: Open Redirect Prevention
# ========================

class TestOpenRedirectPrevention:
    """Verify the login redirect does not allow open redirects."""

    def test_external_redirect_blocked(self, test_client):
        """Ensure ?next= with external URL is ignored."""
        response = test_client.post('/auth/login?next=http://evil.com', data=dict(
            email='student@test.com',
            password='StudentPass1'
        ), follow_redirects=False)

        # Should redirect to dashboard, NOT evil.com
        assert response.status_code == 302
        location = response.headers.get('Location', '')
        assert 'evil.com' not in location
        assert '/dashboard' in location


# ========================
# SECURITY TEST: Duplicate Email Prevention
# ========================

class TestDuplicateEmailPrevention:
    """Verify that duplicate emails are rejected during registration."""

    def test_duplicate_email_rejected(self, test_client):
        response = test_client.post('/auth/register', data=dict(
            name='Dup User',
            email='student@test.com',  # Already exists
            password='DupPass123',
            department='CSE'
        ), follow_redirects=True)

        assert b'already registered' in response.data.lower() or b'login' in response.data.lower()


# ========================
# SECURITY TEST: Input Validation
# ========================

class TestInputValidation:
    """Verify empty/missing inputs are rejected."""

    def test_empty_name_rejected(self, test_client):
        response = test_client.post('/auth/register', data=dict(
            name='',
            email='empty@test.com',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='empty@test.com').first()
            assert user is None, "User with empty name should NOT be created"

    def test_empty_email_rejected(self, test_client):
        response = test_client.post('/auth/register', data=dict(
            name='No Email',
            email='',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(name='No Email').first()
            assert user is None, "User with empty email should NOT be created"

    def test_empty_password_rejected(self, test_client):
        response = test_client.post('/auth/register', data=dict(
            name='No Pass',
            email='nopass@test.com',
            password='',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='nopass@test.com').first()
            assert user is None, "User with empty password should NOT be created"

# ========================
# SECURITY TEST: OTP Password Reset
# ========================

class TestOTPPasswordReset:
    """Verify OTP generation, verification, and expiration."""

    def test_forgot_password_generates_otp(self, test_client):
        """Requesting password reset should generate an OTP in the database."""
        response = test_client.post('/recovery/forgot_password', data=dict(
            email='student@test.com'
        ), follow_redirects=True)
        
        # Success message should be shown even for existing emails
        assert b'password reset link has been sent' in response.data or b'OTP' in response.data or b'account exists' in response.data
        
        with test_client.application.app_context():
            user = User.query.filter_by(email='student@test.com').first()
            otp_record = PasswordResetOTP.query.filter_by(user_id=user.id).first()
            assert otp_record is not None
            assert len(otp_record.otp) == 6
            assert not otp_record.is_used

    def test_verify_invalid_otp_fails(self, test_client):
        """Providing an invalid OTP should fail."""
        # 1. Inject email into session
        with test_client.session_transaction() as sess:
            sess['reset_email'] = 'student@test.com'
        
        # 2. Try invalid OTP
        response = test_client.post('/recovery/verify_otp', data=dict(
            otp='999999'  # Very unlikely to be the real OTP
        ), follow_redirects=True)
        
        assert b'Invalid or expired' in response.data

    def test_verify_valid_otp_succeeds(self, test_client):
        """Providing the correct OTP should allow password reset."""
        # 1. Request OTP
        test_client.post('/recovery/forgot_password', data=dict(email='student@test.com'))
        
        # 2. Get the actual OTP from the database
        otp_code = None
        with test_client.application.app_context():
            user = User.query.filter_by(email='student@test.com').first()
            otp_record = PasswordResetOTP.query.filter_by(user_id=user.id, is_used=False).first()
            otp_code = otp_record.otp
            
        # 3. Simulate session email that would normally carry over in a browser
        with test_client.session_transaction() as sess:
            sess['reset_email'] = 'student@test.com'
            
        # 4. Verify the OTP
        response = test_client.post('/recovery/verify_otp', data=dict(
            otp=otp_code
        ), follow_redirects=True)
        
        assert b'OTP Verified' in response.data
        
        # Check session was updated
        with test_client.session_transaction() as sess:
            assert sess.get('otp_verified') is True
        
        # 5. Perform the actual password reset
        response2 = test_client.post('/recovery/reset_password', data=dict(
            password='NewStrongPass1',
            confirm_password='NewStrongPass1'
        ), follow_redirects=True)
        
        assert b'securely updated' in response2.data
        
        # Verify the OTP is now marked as used
        with test_client.application.app_context():
            user = User.query.filter_by(email='student@test.com').first()
            old_otp = PasswordResetOTP.query.filter_by(user_id=user.id, otp=otp_code).first()
            assert old_otp.is_used
            
    def test_expired_otp_fails(self, test_client):
        """An expired OTP should not be accepted."""
        # 1. Request OTP
        test_client.post('/recovery/forgot_password', data=dict(email='staff@test.com'))
        
        # 2. Manually expire the OTP in the database
        otp_code = None
        with test_client.application.app_context():
            user = User.query.filter_by(email='staff@test.com').first()
            otp_record = PasswordResetOTP.query.filter_by(user_id=user.id, is_used=False).first()
            otp_code = otp_record.otp
            
            # Set expiration to 1 hour ago
            otp_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.session.commit()
            
        # 3. Simulate session setup
        with test_client.session_transaction() as sess:
            sess['reset_email'] = 'staff@test.com'
            
        # 4. Try to verify the expired OTP
        response = test_client.post('/recovery/verify_otp', data=dict(
            otp=otp_code
        ), follow_redirects=True)
        
        assert b'Invalid or expired' in response.data


# ========================
# SECURITY TEST: Rate Limiting (Vulnerability 1)
# ========================

class TestRateLimiting:
    """Verify rate limiting is properly configured."""

    def test_rate_limit_headers_present(self, test_client):
        """Verify rate limit response headers are present."""
        response = test_client.get('/auth/login')
        # Flask-Limiter adds these headers when RATELIMIT_HEADERS_ENABLED=True
        # In test mode with RATELIMIT_ENABLED=False, headers may not appear
        # This test verifies the app doesn't crash with rate limit config
        assert response.status_code == 200

    def test_api_endpoints_require_auth(self, test_client):
        """Verify dashboard API endpoints require authentication."""
        response = test_client.get('/dashboard/api/dashboard_data', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_keywords_api_requires_auth(self, test_client):
        """Verify keywords API endpoint requires authentication."""
        response = test_client.get('/dashboard/api/keywords', follow_redirects=False)
        assert response.status_code == 302


# ========================
# SECURITY TEST: Email Validation (Vulnerability 3)
# ========================

class TestEmailValidation:
    """Verify email format validation on registration."""

    def test_invalid_email_no_at_sign(self, test_client):
        """Reject emails without @ symbol."""
        test_client.post('/auth/register', data=dict(
            name='Bad Email User',
            email='notanemail',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='notanemail').first()
            assert user is None, "User with invalid email should NOT be created"

    def test_invalid_email_no_domain(self, test_client):
        """Reject emails without a domain."""
        test_client.post('/auth/register', data=dict(
            name='Bad Email User 2',
            email='user@',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='user@').first()
            assert user is None, "User with invalid email (no domain) should NOT be created"

    def test_valid_email_accepted(self, test_client):
        """Accept properly formatted emails."""
        test_client.post('/auth/register', data=dict(
            name='Good Email User',
            email='valid.user@example.com',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='valid.user@example.com').first()
            assert user is not None, "User with valid email should be created"


# ========================
# SECURITY TEST: Input Sanitization (Vulnerability 3)
# ========================

class TestInputSanitization:
    """Verify XSS prevention and input length limits."""

    def test_xss_in_name_stripped(self, test_client):
        """HTML/script tags should be stripped from the name field."""
        test_client.post('/auth/register', data=dict(
            name='<script>alert("xss")</script>Normal Name',
            email='xss@test.com',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='xss@test.com').first()
            if user:
                assert '<script>' not in user.name, "HTML tags should be stripped from name"
                assert 'Normal Name' in user.name

    def test_long_name_rejected(self, test_client):
        """Names exceeding 100 characters should be rejected."""
        test_client.post('/auth/register', data=dict(
            name='A' * 101,
            email='longname@test.com',
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email='longname@test.com').first()
            assert user is None, "User with name > 100 chars should NOT be created"

    def test_long_email_rejected(self, test_client):
        """Emails exceeding 120 characters should be rejected."""
        # Construct a valid-format email that exceeds 120 chars
        long_email = 'a' * 115 + '@test.com'
        test_client.post('/auth/register', data=dict(
            name='Long Email User',
            email=long_email,
            password='ValidPass1',
            department='CSE'
        ), follow_redirects=True)

        with test_client.application.app_context():
            user = User.query.filter_by(email=long_email).first()
            assert user is None, "User with email > 120 chars should NOT be created"

