import json

CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
}


def _response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(message),
    }


def return_fail(message):
    return _response(500, message)


def return_bad_input(message):
    return _response(400, message)


def return_not_found(message):
    return _response(404, message)


def return_access_denied(message):
    return _response(403, message)


def return_ok(message):
    return _response(200, message)
