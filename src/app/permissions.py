import json
import os

import boto3

POLICY_STORE_ID = os.environ.get("AVP_POLICY_STORE_ID")
POLICY_TEMPLATE_ID = os.environ.get("AVP_POLICY_TEMPLATE_ID")

avp_client = boto3.client("verifiedpermissions")

ACTIONS = {
    "GET:/customizations/{id}": "GetUnicorn",
    "DELETE:/customizations/{id}": "DeleteUnicorn",
}


class Permissions:
    def is_authorized(self, principal, action, http_method, resource, entities=None):
        action = ACTIONS.get(http_method + ":" + action, "unknown_action")
        params = {
            "policyStoreId": POLICY_STORE_ID,
            "principal": {
                "entityId": principal,
                "entityType": "WildRydes::User",
            },
            "action": {
                "actionId": action,
                "actionType": "WildRydes::Action",
            },
            "resource": {
                "entityId": resource,
                "entityType": "WildRydes::Unicorn",
            },
        }
        print("AVP params:" + json.dumps(params))

        response = avp_client.is_authorized(**params)

        print("AVP response:" + json.dumps(response))

        if response.get("decision") == "ALLOW":
            return True
        return False

    def create_template_linked_policy(self, principal, resource):
        params = {
            "definition": {
                "templateLinked": {
                    "policyTemplateId": POLICY_TEMPLATE_ID,
                    "principal": {
                        "entityId": principal,
                        "entityType": "WildRydes::User",
                    },
                    "resource": {
                        "entityId": str(resource),
                        "entityType": "WildRydes::Unicorn",
                    },
                }
            },
            "policyStoreId": POLICY_STORE_ID,
        }

        print("AVP params:" + json.dumps(params))
        response = avp_client.create_policy(**params)
        print("AVP response:" + json.dumps(response))
        return response

    def list_policies(self, principal, resource=None):
        params = {
            "policyStoreId": POLICY_STORE_ID,
            "filter": {
                "policyTemplateId": POLICY_TEMPLATE_ID,
                "policyType": "TEMPLATE_LINKED",
                "principal": {
                    "identifier": {
                        "entityId": principal,
                        "entityType": "WildRydes::User",
                    }
                },
            },
        }

        if resource:
            params["filter"]["resource"] = {
                "identifier": {
                    "entityId": str(resource),
                    "entityType": "WildRydes::Unicorn",
                }
            }

        print("AVP params:" + json.dumps(params))
        response = avp_client.list_policies(**params)
        print("AVP response:" + json.dumps(response))
        return response

    def delete_policy(self, principal, resource):
        policies = self.list_policies(principal, resource)
        response_delete_policy = {}

        if "policies" in policies and len(policies["policies"]) > 0:
            policy_id = policies["policies"][0]["policyId"]

            params = {
                "policyStoreId": POLICY_STORE_ID,
                "policyId": policy_id,
            }

            print("AVP params:" + json.dumps(params))
            response_delete_policy = avp_client.delete_policy(**params)
            print("AVP response:" + json.dumps(response_delete_policy))
        else:
            print("No AVP policies found")

        return response_delete_policy


permissions = Permissions()
