from sqlalchemy import text
from ai_henge_fund.database.engine import get_engine

engine = get_engine()
with engine.connect() as connection:
    for table in ("orders", "agent_runs", "signals"):
        sql = (
            "SELECT conname, contype, pg_get_constraintdef(oid) AS definition "
            f"FROM pg_constraint WHERE conrelid = '{table}'::regclass ORDER BY conname"
        )
        result = connection.execute(text(sql)).fetchall()
        print(f"TABLE {table}")
        for row in result:
            print(row)
