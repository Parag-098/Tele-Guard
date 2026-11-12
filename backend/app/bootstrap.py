import os
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password


def main():
    Base.metadata.create_all(engine)
    username, password = os.getenv("TG_ADMIN_USERNAME"), os.getenv("TG_ADMIN_PASSWORD")
    if not username or not password or len(password) < 12:
        raise SystemExit(
            "Set TG_ADMIN_USERNAME and TG_ADMIN_PASSWORD (12+ chars) to bootstrap the first admin"
        )
    with SessionLocal() as db:
        if db.query(User).filter_by(username=username).first():
            raise SystemExit("Admin already exists")
        db.add(User(username=username, password_hash=hash_password(password), role="Administrator"))
        db.commit()
    print(f"Administrator {username} created")


if __name__ == "__main__":
    main()
