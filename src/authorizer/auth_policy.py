import re

VALID_HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "HEAD", "DELETE", "OPTIONS", "*"}


class HttpVerb:
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    HEAD = "HEAD"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    ALL = "*"


class AuthPolicy:
    """
    AuthPolicy receives a set of allowed and denied methods and generates a valid
    AWS policy for the API Gateway authorizer.
    """

    path_regex = re.compile(r"^[/.a-zA-Z0-9-\*]+$")

    def __init__(self, principal, aws_account_id, api_options=None):
        self.aws_account_id = aws_account_id
        self.principal_id = principal
        self.version = "2012-10-17"
        self.allow_methods = []
        self.deny_methods = []

        api_options = api_options or {}
        self.rest_api_id = api_options.get("restApiId") or "*"
        self.region = api_options.get("region") or "*"
        self.stage = api_options.get("stage") or "*"

    def _add_method(self, effect, verb, resource, conditions):
        if verb != "*" and verb not in VALID_HTTP_VERBS:
            raise ValueError(f"Invalid HTTP verb {verb}. Allowed verbs in AuthPolicy.HttpVerb")

        if not self.path_regex.match(resource):
            raise ValueError(
                f"Invalid resource path: {resource}. Path should match {self.path_regex.pattern}"
            )

        cleaned_resource = resource[1:] if resource.startswith("/") else resource
        resource_arn = (
            f"arn:aws:execute-api:{self.region}:{self.aws_account_id}:"
            f"{self.rest_api_id}/{self.stage}/{verb}/{cleaned_resource}"
        )

        entry = {"resourceArn": resource_arn, "conditions": conditions}
        if effect.lower() == "allow":
            self.allow_methods.append(entry)
        elif effect.lower() == "deny":
            self.deny_methods.append(entry)

    @staticmethod
    def _get_empty_statement(effect):
        effect = effect[0].upper() + effect[1:].lower()
        return {
            "Action": "execute-api:Invoke",
            "Effect": effect,
            "Resource": [],
        }

    def _get_statements_for_effect(self, effect, methods):
        statements = []

        if len(methods) > 0:
            statement = self._get_empty_statement(effect)

            for method in methods:
                if method["conditions"] is None or len(method["conditions"]) == 0:
                    statement["Resource"].append(method["resourceArn"])
                else:
                    conditional_statement = self._get_empty_statement(effect)
                    conditional_statement["Resource"].append(method["resourceArn"])
                    conditional_statement["Condition"] = method["conditions"]
                    statements.append(conditional_statement)

            if len(statement["Resource"]) > 0:
                statements.append(statement)

        return statements

    def allow_all_methods(self):
        self._add_method("allow", "*", "*", None)

    def deny_all_methods(self):
        self._add_method("deny", "*", "*", None)

    def allow_method(self, verb, resource):
        self._add_method("allow", verb, resource, None)

    def deny_method(self, verb, resource):
        self._add_method("deny", verb, resource, None)

    def allow_method_with_conditions(self, verb, resource, conditions):
        self._add_method("allow", verb, resource, conditions)

    def deny_method_with_conditions(self, verb, resource, conditions):
        self._add_method("deny", verb, resource, conditions)

    def build(self):
        if len(self.allow_methods) == 0 and len(self.deny_methods) == 0:
            raise ValueError("No statements defined for the policy")

        policy = {"principalId": self.principal_id}
        doc = {
            "Version": self.version,
            "Statement": self._get_statements_for_effect("Allow", self.allow_methods)
            + self._get_statements_for_effect("Deny", self.deny_methods),
        }
        policy["policyDocument"] = doc
        return policy
