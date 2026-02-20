import os
import time
from sqlalchemy import create_engine, text
from app import create_app

def wait_for_db():
    db_url = os.environ["DATABASE_URL"]
    engine = create_engine(db_url, pool_pre_ping=True)
    for _ in range(30):  # ~30 intentos (aprox 30s)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("DB no disponible después de esperar.")

wait_for_db()
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
