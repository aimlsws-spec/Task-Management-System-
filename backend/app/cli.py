"""Usage:
  (schema is created ONLY by Alembic: python -m alembic upgrade head)
  python -m app.cli seed-core
  python -m app.cli bootstrap-admin --email you@x.com --password '...'
  python -m app.cli send-test-email --to someone@yourcompany.com   (uses the configured email backend)
"""

import argparse
import getpass

import app.models_registry  # noqa: F401
from app.core.db import SessionLocal
from app.seed import bootstrap_admin, seed_core


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed-core")
    t = sub.add_parser("send-test-email")
    t.add_argument("--to", required=True)
    b = sub.add_parser("bootstrap-admin")
    b.add_argument("--email", required=True)
    b.add_argument("--password")
    b.add_argument("--name", default="Administrator")
    args = ap.parse_args()

    if args.cmd == "send-test-email":
        from types import SimpleNamespace

        from app.core.config import get_settings
        from app.modules.notifications import mailer, templates

        s = get_settings()
        title = "Test email from the SeaWind Task Management System"
        body = "If you can read this, outgoing email is working. Task notifications, reminders and escalations will arrive the same way."
        text, html = templates.email_bodies(title, body, s.app_base_url.rstrip("/") + "/", False)
        row = SimpleNamespace(to_email=args.to, subject=f"[SeaWind] {title}", body_text=text, body_html=html, urgent=False)
        print(f"sending via {s.email_backend} ({s.smtp_host}:{s.smtp_port}, {s.smtp_security}) from {s.email_from} to {args.to} ...")
        print("sent through backend:", mailer.send_message(mailer.build_message(row)))  # type: ignore[arg-type]
        return
    with SessionLocal() as db:
        if args.cmd == "seed-core":
            seed_core(db)
        elif args.cmd == "bootstrap-admin":
            bootstrap_admin(db, args.email, args.password or getpass.getpass("Admin password: "), args.name)
        db.commit()
    print("done")


if __name__ == "__main__":
    main()
