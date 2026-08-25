# import streamlit as st
import psycopg2
from dotenv import load_dotenv
import os
import boto3

load_dotenv()

# st.title('This is the Title')
# print('This is the Title')

db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_database = os.getenv('DB_DATABASE')


password = db_password

conn = None
try:
    conn = psycopg2.connect(
        host='database1.cjyqee6gqwgb.eu-north-1.rds.amazonaws.com',
        port=5432,
        database='postgres',
        user='postgres',
        password=password,
        sslmode='verify-full',
    sslrootcert='./global-bundle.pem'
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