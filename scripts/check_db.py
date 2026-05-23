from sqlalchemy import inspect

from app.core.database import engine, init_db

init_db()
tables = inspect(engine).get_table_names()
print("Tables created:", tables)
assert "balances" in tables, "balances table missing!"
assert "transactions" in tables, "transactions table missing!"
assert "products" in tables, "products table missing!"
print("All required tables present - DB init OK")
