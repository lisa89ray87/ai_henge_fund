"""Optional shared reservation check for new PAPER entries only.

Enable with SHARED_SYMBOL_RESERVATIONS=true and SHARED_SYMBOL_DATABASE_URL.
Both repositories must point to the same Neon database. Disabled by default.
"""
import os

def reserve_henge_symbol(symbol: str) -> bool:
    if os.getenv("SHARED_SYMBOL_RESERVATIONS", "false").lower() != "true":
        return True
    url = os.getenv("SHARED_SYMBOL_DATABASE_URL")
    if not url:
        raise RuntimeError("SHARED_SYMBOL_DATABASE_URL missing: blocking paper entry")
    import psycopg
    with psycopg.connect(url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO intraday_trader.symbol_reservations
                    (symbol, owner, reserved_until)
                VALUES (%s, 'AI_HENGE_FUND', now() + interval '30 minutes')
                ON CONFLICT (symbol) DO UPDATE
                SET owner = EXCLUDED.owner, reserved_until = EXCLUDED.reserved_until,
                    updated_at = now()
                WHERE intraday_trader.symbol_reservations.reserved_until <= now()
                   OR intraday_trader.symbol_reservations.owner = EXCLUDED.owner
                RETURNING symbol
            """, (symbol,))
            return cur.fetchone() is not None
