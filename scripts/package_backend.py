import zipfile
import os
from pathlib import Path

backend_dir = Path("backend").resolve()
zip_path = Path("tms-backend-deploy.zip").resolve()

exclude_dirs = {".venv", "__pycache__", ".pytest_cache", ".hypothesis", ".ruff_cache", "task_management_backend.egg-info"}
exclude_extensions = {".pyc", ".pyo"}

included = []
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(backend_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if any(f.endswith(ext) for ext in exclude_extensions):
                continue
            full_path = Path(root) / f
            arc_name = full_path.relative_to(backend_dir)
            zf.write(full_path, arc_name)
            included.append(str(arc_name).replace("\\", "/"))

print(f"Total files packaged: {len(included)}")
key_checks = [
    ".env",
    "DEPLOYMENT_GUIDE.md",
    "requirements.txt",
    "tms_db_dump.sql",
    "app/main.py",
    "app/static/seawind-logo.png",
    "passenger_wsgi.py",
    "alembic/versions/0019_role_invites_department.py",
]
for check in key_checks:
    found = check in included
    status = "FOUND" if found else "MISSING!"
    print(f" - {check}: {status}")
