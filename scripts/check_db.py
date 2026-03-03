from app.core.database import init_db, engine
from sqlalchemy import inspect

init_db()
tables = inspect(engine).get_table_names()
print("Tables created:", tables)
assert "balances" in tables, "balances table missing!"
assert "transactions" in tables, "transactions table missing!"
assert "products" in tables, "products table missing!"
print("All required tables present - DB init OK")

