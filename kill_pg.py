import psycopg
with psycopg.connect('postgresql://campus_user:campus_secure_2026@localhost/campus_ai', autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND datname = 'campus_ai';")
        print("Terminated backend processes")
