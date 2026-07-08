import json

import boto3

import db_utils
import http_util

# from permissions import permissions

CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
}


def lambda_handler(event, context):
    print("received input event: \n" + json.dumps(event, indent=2))

    id = (event.get("pathParameters") or {}).get("id") or False

    resource = None
    if id:
        id = decode_uri(id)
        resource = id

    company = None

    # use the company id from auth context
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    if "authorizer" in request_context and "CompanyID" in authorizer:
        company = authorizer["CompanyID"]

    principal_id = authorizer["principalId"]
    action = request_context["resourcePath"]
    http_method = request_context["httpMethod"]

    if event["httpMethod"] == "GET":
        if id:
            try:
                # is_allowed = permissions.is_authorized(principal_id, action, http_method, resource)
                # if is_allowed:
                unicorn_data = db_utils.get_custom_unicorn(id, company)

                print("successfully retrieved: " + json.dumps(unicorn_data, indent=2))

                if len(unicorn_data) == 0:
                    return http_util.return_not_found(
                        "Unicorn customization " + str(id) + " does not exist."
                    )

                result_row = unicorn_data[0]
                if company is not None:
                    result_row.pop("COMPANY", None)
                    return http_util.return_ok(result_row)
                return http_util.return_ok(result_row)
                # else:
                #     return http_util.return_fail("Unauthorized")
            except Exception as e:
                print(e)
                return http_util.return_fail("Error retrieving unicorn customization")
        else:
            try:
                # policies = permissions.list_policies(principal_id)
                # unicorn_ids = []
                # if "policies" in policies and len(policies["policies"]) > 0:
                #     for policy in policies["policies"]:
                #         unicorn_ids.append(policy["resource"]["entityId"])
                # results = db_utils.list_custom_unicorn(company, unicorn_ids)
                results = db_utils.list_custom_unicorn(company)

                print("successfully retrieved " + str(len(results)) + " custom unicorns.")

                for item in results:
                    item.pop("COMPANY", None)
                return http_util.return_ok(results)
            except Exception as e:
                print(e)
                return http_util.return_fail("Error retrieving unicorn customizations")

    elif event["httpMethod"] == "POST":
        request = json.loads(event["body"])

        if "company" in request:
            company = request["company"]

        name = request["name"]

        if company is None:
            print("no company specified")
            return http_util.return_bad_input("Company not valid")

        image_url = request["imageUrl"]
        sock = request["sock"]
        horn = request["horn"]
        glasses = request["glasses"]
        cape = request["cape"]
        try:
            db_results = db_utils.create_custom_unicorn(
                name, company, image_url, sock, horn, glasses, cape
            )
            print("successfully inserted custom unicorn.")

            # print("creating AVP policy for the unicorn.")
            # permissions.create_template_linked_policy(principal_id, db_results["customUnicornId"])

            return http_util.return_ok(db_results)
        except Exception as e:
            print(e)
            return http_util.return_fail("Error creating unicorn")

    elif event["httpMethod"] == "DELETE":
        try:
            # is_allowed = permissions.is_authorized(principal_id, action, http_method, resource)
            # if is_allowed:
            results = db_utils.delete_custom_unicorn(id, company)

            print("successfully deleted custom unicorn " + str(results))
            # permissions.delete_policy(principal_id, resource)
            return http_util.return_ok(results)
            # else:
            #     return http_util.return_fail("Unauthorized")
        except Exception as e:
            print(e)
            return http_util.return_fail("Error deleting unicorn customization")
    else:
        print("Error: unsupported HTTP method (" + event["httpMethod"] + ")")
        return {"statusCode": 501}


def decode_uri(value):
    from urllib.parse import unquote

    return unquote(value)
