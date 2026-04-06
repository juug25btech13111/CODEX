from functools import wraps
from flask import redirect, url_for, flash, abort, request
from flask_login import current_user

def requires_roles(*roles):
    """
    Decorator to restrict access to endpoints based on user roles.
    Returns HTTP 403 for API requests, redirects with flash for browser requests.
    """
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                # For AJAX/API requests, return proper 403 status
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                   request.accept_mimetypes.best == 'application/json':
                    abort(403)
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return wrapped
    return wrapper
