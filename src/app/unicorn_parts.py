import json

import db_utils

CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
}


def lambda_handler(event, context):
    if event.get("httpMethod") == "GET":
        body_part_to_query = None

        resource = event.get("resource")
        if resource == "/horns":
            body_part_to_query = "Horns"
        elif resource == "/socks":
            body_part_to_query = "Socks"
        elif resource == "/glasses":
            body_part_to_query = "Glasses"
        elif resource == "/capes":
            body_part_to_query = "Capes"

        print("body part to query: " + str(body_part_to_query))

        if body_part_to_query is None:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": "Unsupported body part",
            }

        horns = db_utils.list_body_part_options(body_part_to_query)
        print("successfully retrieved " + str(len(horns)) + " records.")

        response = {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(horns),
        }
        print(response)
        return response

    return {
        "statusCode": 400,
        "headers": CORS_HEADERS,
        "body": "Unsupported method",
    }
