print("Loading function")

import json
import os

import boto3
import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from auth_policy import AuthPolicy, HttpVerb

USER_POOL_ID = os.environ["USER_POOL_ID"]
REGION = os.environ["AWS_REGION"]
ISS = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

ddb_client = boto3.client("dynamodb")

COMPANY_DDB_TABLE = os.environ["PARTNER_DDB_TABLE"]
CUSTOMIZE_SCOPE = "WildRydes/CustomizeUnicorn"
PARTNER_ADMIN_SCOPE = "WildRydes/ManagePartners"

_pems = None


def _load_pems():
    global _pems
    if _pems is None:
        response = requests.get(f"{ISS}/.well-known/jwks.json", timeout=10)
        if response.status_code != 200:
            raise Exception("error")

        _pems = {}
        for key in response.json()["keys"]:
            key_id = key["kid"]
            jwk = {"kty": key["kty"], "n": key["n"], "e": key["e"]}
            _pems[key_id] = RSAAlgorithm.from_jwk(json.dumps(jwk))
    return _pems


def _validate_token(pems, event):
    token = event["authorizationToken"]

    parts = token.split(" ")
    if len(parts) == 2:
        schema = parts[0].lower()
        token = " ".join(parts[1:])
        if schema != "bearer":
            print("Schema " + schema + " not supported")
            raise Exception("Unauthorized")

    decoded_jwt = jwt.decode(token, options={"verify_signature": False})
    header = jwt.get_unverified_header(token)
    if not decoded_jwt:
        print("Not a valid JWT token")
        raise Exception("Unauthorized")

    if decoded_jwt.get("iss") != ISS:
        print("invalid issuer")
        raise Exception("Unauthorized")

    if decoded_jwt.get("token_use") != "access":
        print("Not an access token")
        raise Exception("Unauthorized")

    kid = header.get("kid")
    pem = pems.get(kid)
    if not pem:
        print("Invalid access token")
        raise Exception("Unauthorized")

    try:
        payload = jwt.decode(token, pem, algorithms=["RS256"], issuer=ISS)
    except jwt.PyJWTError as err:
        print("error verifying token: " + json.dumps(str(err), indent=2))
        raise Exception("Unauthorized") from err

    print("Token payload: " + json.dumps(payload))

    principal_id = payload["iss"].split("/")[-1] + "|" + payload["sub"]

    tmp = event["methodArn"].split(":")
    api_gateway_arn_tmp = tmp[5].split("/")
    aws_account_id = tmp[4]
    api_options = {
        "region": tmp[3],
        "restApiId": api_gateway_arn_tmp[0],
        "stage": api_gateway_arn_tmp[1],
    }

    policy = AuthPolicy(principal_id, aws_account_id, api_options)

    policy.allow_method(HttpVerb.GET, "/horns")
    policy.allow_method(HttpVerb.GET, "/socks")
    policy.allow_method(HttpVerb.GET, "/glasses")
    policy.allow_method(HttpVerb.GET, "/capes")

    scope = payload.get("scope", "")

    if PARTNER_ADMIN_SCOPE in scope:
        policy.allow_method(HttpVerb.GET, "/partner*")
        policy.allow_method(HttpVerb.POST, "/partner*")
        policy.allow_method(HttpVerb.DELETE, "/partner*")

        auth_response = policy.build()
        print("authResponse:" + json.dumps(auth_response, indent=2))
        return auth_response

    if CUSTOMIZE_SCOPE in scope:
        policy.allow_method(HttpVerb.GET, "/customizations*")
        policy.allow_method(HttpVerb.POST, "/customizations*")
        policy.allow_method(HttpVerb.DELETE, "/customizations*")
        auth_response = policy.build()

        params = {
            "TableName": COMPANY_DDB_TABLE,
            "Key": {"ClientID": {"S": payload["client_id"]}},
        }

        try:
            response = ddb_client.get_item(**params)
            print("DDB response:\n" + json.dumps(response))
            item = response.get("Item")
            if item and "CompanyID" in item:
                auth_response["context"] = {"CompanyID": item["CompanyID"]["S"]}

                # Uncomment here to pass on the client ID as the api key in the auth response
                # auth_response["usageIdentifierKey"] = payload["client_id"]

                print("authResponse:" + json.dumps(auth_response, indent=2))
                return auth_response

            print("did not find matching clientID")
            raise Exception("Unauthorized")
        except Exception as e:
            if str(e) == "Unauthorized":
                raise
            print("TESTING TESTING: " + str(e))
            raise Exception("Error: Internal Error") from e

    print("did not find matching clientID")
    raise Exception("Unauthorized")


def handler(event, context):
    print("received event:\n" + json.dumps(event, indent=2))

    pems = _load_pems()
    return _validate_token(pems, event)
