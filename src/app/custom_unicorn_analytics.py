import json
import os
from datetime import datetime, timezone

import boto3

import db_utils

DEMAND_FORECAST_DDB_TABLE = os.environ["DEMAND_FORECAST_DDB_TABLE"]

ddb_client = boto3.client("dynamodb", region_name=os.environ.get("AWS_REGION"))


def lambda_handler(event, context):
    try:
        horn_count = db_utils.count_body_part_options("Horns")
        sock_count = db_utils.count_body_part_options("Socks")
        glass_count = db_utils.count_body_part_options("Glasses")
        cape_count = db_utils.count_body_part_options("Capes")
        record_time_stamp = datetime.now(timezone.utc).isoformat()

        print(
            " hornCount:[" + json.dumps(horn_count) + "] Socks:[" + str(sock_count) + "] "
            "Glasses:[" + str(glass_count) + "] Capes:[" + str(cape_count) + "] "
            "recordTimeStamp:[" + record_time_stamp + "]"
        )

        put_item_param = {
            "TableName": DEMAND_FORECAST_DDB_TABLE,
            "Item": {
                "HornCount": {"S": str(horn_count[1])},
                "SockCount": {"S": str(sock_count[1])},
                "GlassCount": {"S": str(glass_count[1])},
                "CapeCount": {"S": str(cape_count[1])},
                "RecordTimeStamp": {"S": str(record_time_stamp)},
            },
        }

        return ddb_client.put_item(**put_item_param)
    except Exception as e:
        print(e)
        return 500
