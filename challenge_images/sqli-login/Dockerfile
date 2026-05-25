# CTFacile — SQLi Login Bypass Challenge Image
# Intentionally vulnerable Flask app for educational CTF use only.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# Default env vars (overridden by DockerManagerService at spawn time)
ENV FLAG="FLAG{sqli_master}"
ENV ADMIN_USERNAME="admin"
ENV ADMIN_PASSWORD="s3cr3t_p4ssw0rd_not_for_you"

# Port 80 matches the default challenge.internal_port value
EXPOSE 80

# gunicorn lets us bind to port 80 without host-level capabilities
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:80", "--workers", "2", "--timeout", "30", "--access-logfile", "-"]
