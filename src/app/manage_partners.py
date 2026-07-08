import json
import os

import boto3
import psycopg2.errors

import db_utils
import http_util

SCOPES = ["WildRydes/CustomizeUnicorn"]
COMPANY_DDB_TABLE = os.environ["PARTNER_DDB_TABLE"]

ddb_client = boto3.client("dynamodb", region_name=os.environ.get("AWS_REGION"))
cognito_client = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION"))


def lambda_handler(event, context):
    print("received input event: \n" + json.dumps(event, indent=2))

    _id = (event.get("pathParameters") or {}).get("id") or False

    if "authorizer" not in event.get("requestContext", {}):
        print("Error: unsupported HTTP method (" + event["httpMethod"] + ")")
        return http_util.return_access_denied(
            "You must implement the custom authorizers before you can call this API."
        )

    if event["httpMethod"] == "POST":
        try:
            request = json.loads(event["body"])
            company = request["name"]

            results = db_utils.add_partner_company(company)
            print("successfully added partner company.")
            company_id = results["companyId"]

            create_user_pool_client_response = cognito_client.create_user_pool_client(
                ClientName=company,
                UserPoolId=os.environ["USER_POOL_ID"],
                GenerateSecret=True,
                RefreshTokenValidity=1,
                AllowedOAuthFlows=["client_credentials"],
                AllowedOAuthScopes=SCOPES,
                AllowedOAuthFlowsUserPoolClient=True,
            )
            client_id = create_user_pool_client_response["UserPoolClient"]["ClientId"]
            client_secret = create_user_pool_client_response["UserPoolClient"]["ClientSecret"]
            print("successfully created cognito client: " + client_id)

            put_item_param = {
                "TableName": COMPANY_DDB_TABLE,
                "Item": {
                    "ClientID": {"S": client_id},
                    "CompanyID": {"S": str(company_id)},
                },
            }
            print("DDB params: " + json.dumps(put_item_param))
            ddb_client.put_item(**put_item_param)
            print("success writing to ddb ID mapping")

            return_message = {"ClientID": client_id, "ClientSecret": client_secret}
            return http_util.return_ok(return_message)
        except psycopg2.errors.UniqueViolation as e:
            print(e)
            return http_util.return_bad_input("Company already registered")
        except Exception as e:
            print(e)
            return http_util.return_fail("Error Encountered")
    else:
        print("Error: unsupported HTTP method (" + event["httpMethod"] + ")")
        return {"statusCode": 501}
