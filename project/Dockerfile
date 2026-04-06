# Use the official lightweight Python image
# https://hub.docker.com/_/python
FROM python:3.10-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
# We install GCC because some python packages might need it
RUN apt-get update && apt-get install -y gcc
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the local code to the container
COPY . ./

# Set the environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV APP_CONFIG=production

# Run the database setup script (creates admin, schemas, etc.)
RUN python reset_db.py

# Expose the port Hugging Face expects (7860)
EXPOSE 7860

# Run the web service on container startup using gunicorn with ProductionConfig
CMD exec gunicorn --bind :7860 --workers 1 --threads 8 --timeout 0 "app:create_app()"
