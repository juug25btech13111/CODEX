# CODEX - College Feedback Sentiment Analysis Platform

## Overview
CODEX is an AI-powered sentiment analysis platform designed for educational institutions. It automatically analyzes student feedback using NLP techniques to extract sentiment trends, generate actionable reports, and provide real-time dashboards for administrators, HODs, and students.

## Features
- **Sentiment Analysis Engine**: NLP-based text analysis using TextBlob and custom models
- **Multi-role Dashboard**: Separate views for Admin, HOD/Staff, and Students
- **File Upload Processing**: Bulk feedback analysis via CSV/Excel uploads
- **Authentication System**: Secure login with MFA, OTP verification, and password recovery
- **Admin Panel**: User management, audit logs, and training management
- **Chart Visualizations**: Interactive sentiment trend charts and reports
- **Docker Support**: Containerized deployment ready

## Tech Stack
- **Backend**: Python, Flask
- **Frontend**: HTML5, CSS3, JavaScript
- **NLP**: TextBlob, NLTK
- **Database**: Firebase Firestore
- **Auth**: Flask sessions with MFA support
- **Deployment**: Docker, Gunicorn

## Project Structure
```
CODEX/
├── README.md              ← This file
├── presentation.pptx      ← Hackathon presentation
└── project/               ← Source code
    ├── app.py             ← Flask application entry point
    ├── config.py          ← Configuration settings
    ├── models.py          ← Database models
    ├── routes/            ← API route handlers
    ├── templates/         ← HTML templates
    ├── static/            ← CSS, JS, assets
    ├── utils/             ← NLP and utility modules
    ├── scripts/           ← DB maintenance scripts
    └── Dockerfile         ← Container config
```

## Quick Start

```bash
# 1. Navigate to the project directory
cd project

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env
# Edit .env with your actual values:
#   - SECRET_KEY (generate a random key)
#   - MAIL_USERNAME / MAIL_PASSWORD (Gmail App Password)
#   - OPENROUTER_API_KEY (from https://openrouter.ai/keys)

# 5. Run the application
python app.py
```

The app will be available at **http://localhost:8080**

## Default Admin Credentials

After running the app, create the admin account by running:
```bash
python create_admin.py
```

| Field    | Value                        |
|----------|------------------------------|
| Email    | `mathasenquiry@gmail.com`    |
| Password | `Admin@2026`                 |
| Role     | Admin                        |

> **Note:** You can create additional users (HOD, Staff, Student) from the Admin dashboard after logging in.

## Team
Built during the college hackathon, April 2026.
