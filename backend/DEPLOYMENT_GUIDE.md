# SeaWind Task Management System (TMS) - Backend Deployment Guide

This package contains the complete production-ready backend for the SeaWind Task Management System, including application source code, static assets, database schema & data dump, runtime configuration (`.env`), and dependency manifests.

---

## 1. System Requirements

* **Operating System:** Linux (Ubuntu 20.04/22.04/24.04, Debian 11/12, CentOS/RHEL/AlmaLinux), Windows Server, or cPanel with Python Selector.
* **Python:** Python **3.12** or **3.13** (64-bit recommended).
* **Database:** **MySQL 8.0+** (or MariaDB 10.6+). MySQL 8 is the primary supported database engine.
* **Network Ports:** Port 8000 (or whichever custom port or reverse proxy port you assign, e.g. Nginx proxy to port 8000).

---

## 2. Directory Structure Overview

```text
backend/
├── app/                      # Application core, modules, API routes, jobs, models
│   ├── static/seawind-logo.png  # Embedded email logo
│   └── main.py               # FastAPI application entrypoint
├── alembic/                  # Database migration scripts
├── .env                      # Active environment configuration
├── .env.example              # Example environment configuration reference
├── alembic.ini               # Alembic configuration
├── passenger_wsgi.py         # cPanel Phusion Passenger WSGI entrypoint
├── pyproject.toml            # Project metadata and dependencies
├── requirements.txt          # Universal production pip requirements
├── requirements-cpanel.txt   # Lightweight cPanel requirements
├── tms_db_dump.sql           # MySQL 8 database schema + data dump
└── DEPLOYMENT_GUIDE.md       # This guide
```

---

## 3. Step-by-Step Deployment Instructions

### Step 1: Extract Files
Extract the archive on your target server:
```bash
# On Linux
unzip tms-backend-deploy.zip -d /var/www/tms-backend
cd /var/www/tms-backend
```

### Step 2: Database Setup (MySQL 8)
1. Log in to MySQL as root or administrator:
```sql
CREATE DATABASE tms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tms_user'@'localhost' IDENTIFIED BY 'YourStrongPasswordHere';
GRANT ALL PRIVILEGES ON tms.* TO 'tms_user'@'localhost';
FLUSH PRIVILEGES;
```

2. Import the included database dump:
```bash
mysql -u tms_user -p tms < tms_db_dump.sql
```

### Step 3: Python Virtual Environment & Dependencies
1. Create a Python 3.12 virtual environment:
```bash
python3.12 -m venv venv
```

2. Activate the virtual environment:
* On Linux/macOS:
  ```bash
  source venv/bin/activate
  ```
* On Windows (PowerShell):
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```

3. Upgrade pip and install all dependencies:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Environment Configuration (`.env`)

Inspect and adjust the `.env` file for your deployment domain and credentials:

| Key | Description | Example / Default |
| :--- | :--- | :--- |
| `TMS_ENV` | Environment mode | `prod` (or `dev`) |
| `TMS_DATABASE_URL` | SQLAlchemy MySQL connection URL | `mysql+pymysql://tms_user:Password@localhost:3306/tms?charset=utf8mb4` |
| `TMS_SECRET_KEY` | JWT and crypto signing key (>= 32 chars) | Random 48+ char token |
| `TMS_APP_BASE_URL` | Public frontend URL (used in email links) | `https://your-domain.com` |
| `TMS_CORS_ORIGINS` | Allowed web origins | `https://your-domain.com,http://localhost:5173` |
| `TMS_COMPANY_TIMEZONE` | Business timezone | `Asia/Kolkata` |
| `TMS_EOD_TIME` | End of day time for deadline reminders | `18:30` |
| `TMS_EMAIL_BACKEND` | Email backend (`smtp` or `log`) | `smtp` |
| `TMS_SMTP_HOST` | Outbound SMTP host | `smtp.gmail.com` or corporate SMTP |
| `TMS_SMTP_PORT` | Outbound SMTP port | `587` (STARTTLS) or `465` (SSL) |
| `TMS_SMTP_SECURITY` | `starttls` or `ssl` | `starttls` |
| `TMS_SMTP_USER` | SMTP username | `your-email@domain.com` |
| `TMS_SMTP_PASSWORD` | SMTP password / App Password | `app-password-here` |
| `TMS_EMAIL_FROM` | Sender address | `"SeaWind TMS" <noreply@domain.com>` |
| `TMS_MAIL_AFTER_REQUEST`| Process emails/reminders immediately after mutations | `true` |
| `TMS_INLINE_JOBS` | Run scheduler inside app | `true` |
| `TMS_GEMINI_API_KEY` | Google Gemini API key for AI task recommendations | Optional / configured |
| `TMS_OPENROUTER_API_KEY`| OpenRouter fallback API key | Optional / configured |

---

## 5. Running the Application

### Option A: Linux VPS with Systemd (Recommended for Linux)
1. Test running directly with Uvicorn:
```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

2. Create a systemd service file `/etc/systemd/system/tms-backend.service`:
```ini
[Unit]
Description=SeaWind Task Management System Backend
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/tms-backend
Environment="PATH=/var/www/tms-backend/venv/bin"
ExecStart=/var/www/tms-backend/venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tms-backend
sudo systemctl start tms-backend
sudo systemctl status tms-backend
```

4. Nginx Reverse Proxy snippet:
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### Option B: cPanel / Shared Hosting (Phusion Passenger)
1. In cPanel, navigate to **Setup Python App**.
2. Click **Create Application**:
   * **Python version:** Select **3.12**
   * **Application root:** `tms-backend` (path where backend folder is located)
   * **Application URL:** domain/subdomain or sub-path
   * **Application startup file:** `passenger_wsgi.py`
   * **Application Entry point:** `application`
3. Click **Create**.
4. Install dependencies via cPanel UI or SSH:
   ```bash
   source /home/username/virtualenv/tms-backend/3.12/bin/activate
   pip install -r requirements-cpanel.txt
   ```
5. Restart the Python application from the cPanel interface.

---

## 6. Background Cron Job Setup (Reminders & Email Dispatch)

The backend handles inline job kicking upon requests, but for reliable unattended reminders (including 3-hour before EOD notices when no users are active), add a cron job:

```bash
# Run every minute
* * * * * cd /var/www/tms-backend && /var/www/tms-backend/venv/bin/python app/jobs/run_once.py >> logs/cron.log 2>&1
```

---

## 7. Health Check Verification

Once running, verify the backend health status:
```bash
curl http://127.0.0.1:8000/healthz
```
Expected Response:
```json
{"status": "ok", "database": "ok"}
```

API Documentation (Swagger UI):
`http://your-domain.com/docs` or `http://127.0.0.1:8000/docs`
