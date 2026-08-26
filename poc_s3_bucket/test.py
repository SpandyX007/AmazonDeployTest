import psycopg2
import boto3
from dotenv import load_dotenv
import os

load_dotenv()

db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_database = os.getenv('DB_DATABASE')


conn = None
try:
    conn = psycopg2.connect(
        host=db_host,
        port=5432,
        database='postgres',
        user=db_user,
        password=db_password,
        sslmode='verify-full',
    sslrootcert='global-bundle.pem'
    )
    cur = conn.cursor()
    cur.execute('SELECT version();')
    print(cur.fetchone()[0])
    cur.close()
except Exception as e:
    print(f"Database error: {e}")
    raise
finally:
    if conn:
        conn.close()