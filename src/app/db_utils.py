import os
from datetime import date, datetime
from decimal import Decimal

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

CUSTOM_UNICORN_TABLE = "Custom_Unicorns"
PARTNER_COMPANY_TABLE = "Companies"

HOST = os.environ.get(
    "DB_HOST",
    "database-2.cluster-ckn4goo6k8of.us-east-1.rds.amazonaws.com",
)
DB_USER = os.environ.get("DB_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "unicorn_customization")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USE_IAM_AUTH = os.environ.get("DB_USE_IAM_AUTH", "true").lower() == "true"
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


def _serialize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialize_row(row):
    return {key: _serialize_value(val) for key, val in row.items()}


def _get_auth_password():
    if DB_USE_IAM_AUTH:
        return boto3.client("rds", region_name=AWS_REGION).generate_db_auth_token(
            DBHostname=HOST,
            Port=DB_PORT,
            DBUsername=DB_USER,
            Region=AWS_REGION,
        )
    return DB_PASSWORD or "Corp123!"


class Database:
    def query(self, sql, connection):
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                if sql.strip().upper().startswith("SELECT"):
                    return [_serialize_row(dict(row)) for row in cursor.fetchall()]
                connection.commit()
                return {"insertId": None, "affectedRows": cursor.rowcount}
        finally:
            connection.close()

    def connect_to_db(self, db_config):
        return psycopg2.connect(**db_config)

    def get_db_config(self):
        print("getDbConfig()")
        return {
            "host": HOST,
            "user": DB_USER,
            "password": _get_auth_password(),
            "dbname": DB_NAME,
            "port": DB_PORT,
            "connect_timeout": 10,
            "sslmode": "require",
        }


def execute_db_query(query):
    db_conn = Database()
    config = db_conn.get_db_config()
    connection = db_conn.connect_to_db(config)
    return db_conn.query(query, connection)


def count_body_part_options(body_part):
    query = f'SELECT count(*) AS count FROM "{body_part}"'
    print("query for DB: " + query)
    results = execute_db_query(query)
    print(str(results))
    count = results[0]["count"]
    print(body_part + " count: " + str(count))
    return [body_part, count]


def list_body_part_options(body_part):
    query = f'SELECT * FROM "{body_part}"'
    print("query for DB: " + query)
    return execute_db_query(query)


def add_partner_company(company_name):
    insert_query = (
        f'INSERT INTO "{PARTNER_COMPANY_TABLE}" ("NAME") '
        f"VALUES ('{company_name}') RETURNING \"ID\""
    )
    print("query for insert:" + insert_query)
    db_conn = Database()
    config = db_conn.get_db_config()
    connection = db_conn.connect_to_db(config)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(insert_query)
            row = cursor.fetchone()
            connection.commit()
            insert_id = row["ID"]
    finally:
        connection.close()
    print("insert id: " + str(insert_id))
    return {"companyId": insert_id}


def create_custom_unicorn(name, company, image_url, sock, horn, glasses, cape):
    insert_query = (
        f'INSERT INTO "{CUSTOM_UNICORN_TABLE}" '
        f'("NAME", "COMPANY", "IMAGEURL", "SOCK", "HORN", "GLASSES", "CAPE") '
        f"VALUES ('{name}',{company},'{image_url}',{sock},{horn},{glasses},{cape}) "
        f'RETURNING "ID"'
    )
    print("query for insert:" + insert_query)
    db_conn = Database()
    config = db_conn.get_db_config()
    connection = db_conn.connect_to_db(config)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(insert_query)
            row = cursor.fetchone()
            connection.commit()
            insert_id = row["ID"]
    finally:
        connection.close()
    print("insert id: " + str(insert_id))
    return {"customUnicornId": insert_id}


def list_custom_unicorn(company, unicorn_ids=None):
    if unicorn_ids is None:
        unicorn_ids = []
    query = f'SELECT * FROM "{CUSTOM_UNICORN_TABLE}"'
    print("query for compa" + str(company))
    if company is not None and company != "":
        query += f' WHERE "COMPANY" = {company}'
    print("query for DB: " + query)
    return execute_db_query(query)


def get_custom_unicorn(id, company):
    query = f'SELECT * FROM "{CUSTOM_UNICORN_TABLE}" WHERE "ID" = {id}'
    if company is not None and company != "":
        query += f' AND "COMPANY" = {company}'
    print("query for DB: " + query)
    return execute_db_query(query)


def delete_custom_unicorn(id, company):
    query = f'DELETE FROM "{CUSTOM_UNICORN_TABLE}" WHERE "ID" = {id}'
    if company is not None and company != "":
        query += f' AND "COMPANY" = {company}'
    print("query for DB: " + query)
    results = execute_db_query(query)
    if results["affectedRows"] == 1:
        return {"id": id}
    return {}
