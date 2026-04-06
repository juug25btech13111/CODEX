import pytest
from app import create_app
from models import db, User

@pytest.fixture
def test_client():
    # Configure app for testing
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory SQLite for tests
    app.config['WTF_CSRF_ENABLED'] = False

    with app.test_client() as testing_client:
        with app.app_context():
            db.create_all()
            
            # Seed test users
            admin = User(name="Admin test", email="admin@test.com", role="Admin")
            admin.set_password("pass123")
            
            student = User(name="Student test", email="student@test.com", role="Student")
            student.set_password("pass123")
            
            db.session.add_all([admin, student])
            db.session.commit()
            
            yield testing_client
            
            db.session.remove()
            db.drop_all()

def test_login_page_loads(test_client):
    response = test_client.get('/auth/login')
    assert response.status_code == 200

def test_register_page_loads(test_client):
    response = test_client.get('/auth/register')
    assert response.status_code == 200

def login(client, email, password):
    return client.post('/auth/login', data=dict(
        email=email,
        password=password
    ), follow_redirects=True)

def logout(client):
    return client.post('/auth/logout', follow_redirects=True)

def test_dashboard_access(test_client):
    # Unauthenticated should redirect
    response = test_client.get('/dashboard/', follow_redirects=False)
    assert response.status_code == 302
    assert '/auth/login' in response.headers.get('Location')
    
    # Authenticated should succeed
    login(test_client, 'student@test.com', 'pass123')
    response2 = test_client.get('/dashboard/')
    assert response2.status_code == 200

def test_admin_routes_security(test_client):
    # Login as student
    login(test_client, 'student@test.com', 'pass123')
    
    # Try access admin route
    response = test_client.get('/admin/create-user', follow_redirects=True)
    # Should be redirected to dashboard
    assert b'permission' in response.data
    
    logout(test_client)
    
    # Login as admin
    login(test_client, 'admin@test.com', 'pass123')
    response2 = test_client.get('/admin/create-user')
    assert response2.status_code == 200
    
    response3 = test_client.get('/admin/manage-users')
    assert response3.status_code == 200

def test_profile_route(test_client):
    login(test_client, 'student@test.com', 'pass123')
    response = test_client.get('/profile/')
    assert response.status_code == 200

def test_submit_feedback_page(test_client):
    login(test_client, 'student@test.com', 'pass123')
    response = test_client.get('/feedback/submit')
    assert response.status_code == 200

def test_upload_route_security(test_client):
    # Student cannot upload
    login(test_client, 'student@test.com', 'pass123')
    response = test_client.get('/upload/', follow_redirects=True)
    assert b'permission to access' in b''.join(response.data.split()) or b'permission' in response.data
    logout(test_client)
    
    # Admin can upload
    login(test_client, 'admin@test.com', 'pass123')
    response2 = test_client.get('/upload/')
    assert response2.status_code == 200
