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
cd project
pip install -r requirements.txt
python app.py
```

## Team
Built during the college hackathon, April 2026.
