import json
import os
from datetime import date, datetime
from decimal import Decimal

from aws_xray_sdk.core import patch, xray_recorder

patch(["boto3"])

from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
import boto3
from botocore.exceptions import ClientError
import psycopg2
from psycopg2.extras import RealDictCursor

CUSTOM_UNICORN_TABLE = "Custom_Unicorns"
PARTNER_COMPANY_TABLE = "Companies"

_secrets_client = None
_rds_client = None
_secret_cache_client = None


def _get_region():
    return os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )


def _get_dbname():
    return os.environ.get("DB_NAME", "unicorn_customization")


def _use_iam_auth():
    return os.environ.get("DB_USE_IAM_AUTH", "true").lower() == "true"


def _get_rds_client():
    global _rds_client
    if _rds_client is None:
        _rds_client = boto3.client("rds", region_name=_get_region())
    return _rds_client


def _get_secret_name():
    secret_name = os.environ.get("SECRET_NAME")
    if not secret_name:
        raise ValueError("SECRET_NAME environment variable is required")
    return secret_name


def _get_secret_cache():
    global _secret_cache_client
    if _secret_cache_client is None:
        client = boto3.client("secretsmanager", region_name=_get_region())
        config = SecretCacheConfig(
            secret_refresh_interval=float(
                os.environ.get("SECRET_CACHE_TTL_SECONDS", "300")
            )
        )
        _secret_cache_client = SecretCache(config=config, client=client)
    return _secret_cache_client


@xray_recorder.capture("secrets_manager_get_secret")
def _load_db_secret():
    secret_string = _get_secret_cache().get_secret_string(_get_secret_name())

    if not secret_string:
        raise ValueError("Cannot parse DB credentials from Secrets Manager.")

    secret = json.loads(secret_string)
    for key in ("host", "username"):
        if not secret.get(key):
            raise ValueError(f"Secret is missing required field: {key}")

    return secret


@xray_recorder.capture("resolve_db_password")
def _resolve_password(host, user, port, secret):
    if _use_iam_auth():
        return _get_rds_client().generate_db_auth_token(
            DBHostname=host,
            Port=port,
            DBUsername=user,
            Region=_get_region(),
        )

    password = secret.get("password")
    if not password:
        raise ValueError(
            "Secret must contain 'password' when DB_USE_IAM_AUTH is not true"
        )
    return password


def _serialize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialize_row(row):
    return {key: _serialize_value(val) for key, val in row.items()}


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
        secret = _load_db_secret()

        host = secret["host"]
        user = secret["username"]
        port = int(secret.get("port", 5432))

        return {
            "host": host,
            "user": user,
            "password": _resolve_password(host, user, port, secret),
            "dbname": _get_dbname(),
            "port": port,
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
