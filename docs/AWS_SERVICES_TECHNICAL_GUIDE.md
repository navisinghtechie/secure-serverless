# AWS Serverless Technical Deep Dive — Wild Rydes Project

A standalone technical reference for every major AWS service in this project, from definitions through advanced behavior, with **exact configurations from the templates** and **pros/cons**.

For a shorter introduction, see [WORKSHOP_GUIDE.md](WORKSHOP_GUIDE.md). For deploy commands, see [README.md](../README.md).

---

## Table of contents

1. [How the pieces connect](#0-how-the-pieces-connect-mental-model)
2. [AWS Lambda](#1-aws-lambda)
3. [Amazon API Gateway](#2-amazon-api-gateway-rest-api)
4. [Amazon VPC & networking](#3-amazon-vpc--networking)
5. [Amazon Aurora (RDS) PostgreSQL](#4-amazon-aurora-rds-postgresql)
6. [Amazon DynamoDB](#5-amazon-dynamodb)
7. [Amazon Cognito](#6-amazon-cognito)
8. [AWS IAM](#7-aws-iam-identity-and-access-management)
9. [AWS SAM & CloudFormation](#8-aws-sam--cloudformation)
10. [Amazon S3](#9-amazon-s3)
11. [Amazon EventBridge Scheduler](#10-amazon-eventbridge-scheduler)
12. [Amazon CloudWatch Logs](#11-amazon-cloudwatch-logs)
13. [Supporting services](#12-supporting-services-workshop--ide-templates)
14. [End-to-end: GET /socks](#13-end-to-end-get-socks-at-every-layer)
15. [Production vs workshop](#14-production-vs-this-workshop-honest-assessment)
16. [Lambda function reference](#15-quick-reference--all-lambda-functions)

---

## 0. How the pieces connect (mental model)

```
Internet
   │
   ▼
API Gateway (REST, stage=dev)  ──invoke──▶  Lambda functions (Python 3.9, in VPC)
   │                                              │
   │                                              ├──▶ Aurora PostgreSQL (port 5432, IAM auth)
   │                                              ├──▶ DynamoDB (partner lookup, analytics)
   │                                              └──▶ Cognito (create OAuth clients)
   │
   └── (optional) Custom Authorizer Lambda ──▶ validates JWT, reads DynamoDB

Foundation (deployed first):
VPC → subnets → NAT → security groups → S3 deploy bucket
EventBridge Scheduler ──invoke──▶ Analytics Lambda (every 2 min)
```

**Two CloudFormation stacks (typical):**

1. **`Secure-Serverless`** — network + shared infra (`secure-serverless-template.yaml` or `init-template.yml`)
2. **`CustomizeUnicorns`** — API app (`src/template.yaml` via SAM)

They connect via **CloudFormation exports/imports** (e.g. `Secure-Serverless-LambdaSecurityGroup`).

---

## 1. AWS Lambda

### Definition

**Lambda** is AWS's event-driven compute service. You upload a function (handler + runtime + dependencies). AWS runs it when triggered (API call, schedule, S3 event, etc.). You pay per **invocation**, **duration (GB-seconds)**, and optional provisioned concurrency.

You do **not** manage EC2 instances, OS patches, or scaling — AWS creates ephemeral execution environments (sandboxes) on demand.

### Key concepts

| Concept | Meaning |
|---------|---------|
| **Handler** | Entry point: `file.function` → `unicorn_parts.lambda_handler` |
| **Runtime** | Language version: `python3.9` |
| **Execution role** | IAM role Lambda assumes to call AWS APIs (RDS, DynamoDB, etc.) |
| **Environment variables** | Config injected at runtime (`DB_HOST`, etc.) |
| **Timeout** | Max run time (30s globally in your SAM template) |
| **Memory** | Default 128 MB unless set (affects CPU proportionally) |
| **Cold start** | First invocation or after idle → container init + import libs |
| **VPC-attached Lambda** | Gets ENIs in your subnets to reach private resources (adds cold-start latency) |

### What is configured in this project

**Global defaults** (`src/template.yaml`):

```yaml
Globals:
  Function:
    Timeout: 30
    Environment:
      Variables:
        DB_HOST: !Ref DbHost
        DB_USER: !Ref DbUser
        DB_NAME: !Ref DbName
        DB_USE_IAM_AUTH: "true"
```

Every function inherits `Timeout: 30` and DB env vars unless overridden.

#### Function 1: `UnicornPartsFunction`

```yaml
UnicornPartsFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: app/
    Handler: unicorn_parts.lambda_handler
    Runtime: python3.9
    Policies:
      - VPCAccessPolicy: {}          # AWSLambdaVPCAccessExecutionRole
      - rds-db:connect on dbuser:*/*
    VpcConfig:
      SecurityGroupIds:
        - Fn::ImportValue: Secure-Serverless-LambdaSecurityGroup
      SubnetIds:
        - PrivateSubnet1
        - PrivateSubnet2
    Events:
      ListSocks:
        Type: Api
        Properties:
          Path: /socks
          Method: get
```

**What this means technically:**

- **CodeUri `app/`** — SAM packages entire `app/` folder (all `.py` files + `requirements.txt` deps).
- **Handler** — Lambda calls `lambda_handler(event, context)` in `unicorn_parts.py`.
- **VPCAccessPolicy** — Grants `ec2:CreateNetworkInterface`, `ec2:DescribeNetworkInterfaces`, `ec2:DeleteNetworkInterface` so Lambda can attach ENIs in VPC.
- **rds-db:connect** — IAM permission for **IAM database authentication** (not traditional `rds:Connect`).
- **VpcConfig** — Function runs inside private subnets; outbound traffic to internet goes through NAT gateway.
- **Events Type: Api** — SAM creates API Gateway integration + Lambda invoke permission.

**Runtime example** (`unicorn_parts.py`):

```python
def lambda_handler(event, context):
    # event from API Gateway proxy integration:
    # { "httpMethod": "GET", "resource": "/socks", "headers": {...}, ... }
    horns = db_utils.list_body_part_options("Socks")
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps(horns),
    }
```

Lambda must return this **API Gateway proxy format** when using `aws_proxy` integration.

#### Function 2: `CustomizeUnicornFunction`

Same VPC + RDS IAM setup. API routes:

- `GET/POST /customizations`
- `GET/DELETE /customizations/{id}`

Extra commented policies for **Amazon Verified Permissions** (workshop module, not active).

Reads `CompanyID` from authorizer context when enabled:

```python
authorizer = event["requestContext"]["authorizer"]
company = authorizer["CompanyID"]  # injected by custom authorizer
```

#### Function 3: `ManagePartnerFunction`

Additional policies:

```yaml
Policies:
  - cognito-idp:* on *
  - dynamodb:* on *
  - rds-db:connect
Environment:
  USER_POOL_ID: !Ref CognitoUserPool
  PARTNER_DDB_TABLE: !Ref PartnerDDBTable
```

**Side effects on `POST /partners`:**

1. `INSERT` into PostgreSQL `Companies`
2. `cognito-idp:CreateUserPoolClient` — OAuth client with secret
3. `dynamodb:PutItem` — map `ClientID → CompanyID`

#### Function 4: `CustomUnicornAnalyticsFunction`

```yaml
FunctionName: "CustomUnicornAnalyticsFunction"  # fixed name (not auto-generated)
Policies:
  - AdministratorAccess   # intentionally bad for workshop demo
Tags:
  application: customizeUnicorn
Environment:
  DEMAND_FORECAST_DDB_TABLE: !Ref DemandForecastDDBTable
```

**Not API-triggered.** Invoked by EventBridge Scheduler every 2 minutes. Counts rows in Horns/Socks/Glasses/Capes tables, writes to DynamoDB.

#### Authorizer Lambda (`src/authorizer/index.py`)

Separate deployment unit (authorizer folder). When enabled in API Gateway:

```python
def handler(event, context):
    # event["authorizationToken"] = "Bearer eyJ..."
    # event["methodArn"] = "arn:aws:execute-api:region:account:apiId/stage/GET/customizations"
    pems = _load_pems()  # fetch Cognito JWKS
    return _validate_token(pems, event)  # returns IAM policy document
```

Returns an **IAM policy** allowing/denying API methods + optional **context** (`CompanyID`).

### Lambda + VPC: advanced behavior

When Lambda is in a VPC:

1. AWS creates **Elastic Network Interfaces (ENIs)** in your subnets.
2. Lambda gets a private IP from subnet CIDR.
3. To reach Aurora at private endpoint → route within VPC (security groups must allow 5432).
4. To reach AWS APIs (Cognito, DynamoDB, STS for IAM token) → typically via **NAT Gateway** (private subnet route `0.0.0.0/0 → NAT`) or **VPC endpoints** (not used in this project).

**Cold start impact:** VPC Lambda cold starts are often **1–10+ seconds** (ENI setup). Warm invocations reuse the sandbox.

**Your timeout:** 30s global. DB `connect_timeout: 10` in `db_utils.py`. A SG misconfiguration → ~10–13s then `OperationalError: timeout expired`.

### Pros & cons of Lambda (in this architecture)

| Pros | Cons |
|------|------|
| No server management | Cold starts (worse in VPC) |
| Auto-scales per request | 15-minute max execution time |
| Pay per use | Debugging distributed flows is harder |
| Fine-grained IAM per function | VPC config adds complexity |
| Native integration with API Gateway | Connection pooling to DB is tricky (open/close per invoke) |

---

## 2. Amazon API Gateway (REST API)

### Definition

**API Gateway** is a managed **HTTP API front door**. It handles TLS termination, routing, throttling, CORS, authentication hooks, and integration with backends (here: Lambda).

This project uses **REST API** (not HTTP API v2), defined via **Swagger 2.0** embedded in CloudFormation.

### What is configured

```yaml
UnicornApi:
  Type: AWS::Serverless::Api
  Properties:
    StageName: dev
    DefinitionBody:
      swagger: "2.0"
      paths:
        "/socks":
          get:
            x-amazon-apigateway-integration:
              httpMethod: POST        # always POST to Lambda invoke API
              type: aws_proxy         # Lambda proxy integration
              uri: arn:.../UnicornPartsFunction/invocations
          options:
            type: mock                # CORS preflight
```

### Key integration type: `aws_proxy`

**Most important technical detail:** With `aws_proxy`, API Gateway forwards the **entire HTTP request** as a JSON event to Lambda and expects Lambda to return **statusCode, headers, body**. API Gateway does **not** map response fields for you.

**Why `httpMethod: POST` on integration?**  
Invoking Lambda through API Gateway's AWS integration always uses POST to the Lambda Invoke API internally — even when the client sent GET `/socks`.

### CORS configuration

Each path has an `OPTIONS` method with **mock integration** returning:

- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: OPTIONS,POST,GET` (etc.)
- `Access-Control-Allow-Headers: Content-Type, Authorization, ...`

Plus gateway-level 4XX/5XX CORS headers in `x-amazon-apigateway-gateway-responses`.

### Authorizer (commented out in template)

```yaml
# security:
#   - CustomAuthorizer: []
```

When enabled:

1. Client sends `Authorization: Bearer <JWT>`
2. API Gateway invokes **authorizer Lambda synchronously** before backend Lambda
3. Authorizer returns IAM policy → allow/deny
4. On allow, `context` keys become `event.requestContext.authorizer.*`

**Authorizer types:**

- **TOKEN** — this project's authorizer (`authorizationToken` header)
- **REQUEST** — can inspect headers/query/body (not used here)

### API URL structure

```
https://{api-id}.execute-api.{region}.amazonaws.com/dev/socks
                              stage ──┘      └── resource path
```

Output from template:

```yaml
ApiURL: !Sub "https://${UnicornApi}.execute-api.${AWS::Region}.amazonaws.com/dev/"
```

### Pros & cons

| Pros | Cons |
|------|------|
| Managed TLS, DDoS protection (with AWS Shield standard) | REST API pricing per request |
| Built-in throttling & usage plans | Swagger 2.0 is older; HTTP API is cheaper/simpler |
| Lambda proxy = full control in code | `aws_proxy` = you must format responses correctly |
| Custom authorizers for fine auth | Authorizer adds latency (~100–500ms+) |

---

## 3. Amazon VPC & networking

### Definition

**VPC (Virtual Private Cloud)** is your isolated private network in AWS. You define IP ranges (CIDR), subnets, routing, and firewalls. Resources in the same VPC can communicate privately.

### VPC layout

```yaml
PubPrivateVPC:
  CidrBlock: 10.0.0.0/16          # 65,536 IPs
  EnableDnsHostnames: true        # required for RDS endpoint DNS resolution
```

| Subnet | CIDR | AZ | Public IP | Route to internet |
|--------|------|-----|-----------|-------------------|
| PublicSubnet1 | 10.0.1.0/24 | AZ-a | Yes | Internet Gateway |
| PublicSubnet2 | 10.0.2.0/24 | AZ-b | Yes | Internet Gateway |
| PrivateSubnet1 | 10.0.3.0/24 | AZ-a | No | NAT Gateway |
| PrivateSubnet2 | 10.0.4.0/24 | AZ-b | No | NAT Gateway |

### Internet Gateway (IGW)

Attached to VPC. Allows **public subnets** bidirectional internet access.

```yaml
PublicRoute:
  DestinationCidrBlock: 0.0.0.0/0
  GatewayId: !Ref InternetGateway
```

### NAT Gateway

Sits in **public subnet**. Private subnets route `0.0.0.0/0` to NAT so **outbound-only** internet works (Lambda → AWS APIs, public RDS if needed).

```yaml
NatGateway:
  SubnetId: PublicSubnet1
PrivateRoute:
  DestinationCidrBlock: 0.0.0.0/0
  NatGatewayId: !Ref NatGateway
```

**Cost note:** NAT Gateway is ~$0.045/hr + data processing — often the biggest fixed cost in small VPC setups.

### Security Groups (stateful firewalls)

**Aurora SG** — inbound only:

```yaml
SecurityGroupIngress:
  - IpProtocol: tcp
    FromPort: 5432
    ToPort: 5432
    CidrIp: 10.0.0.0/16    # any IP in VPC can connect to PostgreSQL
```

**Lambda SG** — egress only (default deny inbound):

```yaml
SecurityGroupEgress:
  - CidrIp: 10.0.0.0/16, port 5432    # PostgreSQL in VPC
  - CidrIp: 0.0.0.0/0, port 5432      # public RDS via NAT
  - CidrIp: 0.0.0.0/0, ports 80/443/53  # HTTPS/DNS for AWS APIs
```

**Stateful behavior:** If Lambda SG allows outbound to Aurora:5432, Aurora's **response** is allowed back automatically (if Aurora SG allows inbound from Lambda's IP/SG).

**Connection timeout bug (resolved):** Old config had Lambda egress only to `DestinationSecurityGroupId: AuroraSecurityGroup`. External RDS clusters using a **different SG** → outbound blocked → TCP timeout.

### CloudFormation exports (cross-stack wiring)

```yaml
Outputs:
  LambdaSecurityGroup:
    Export:
      Name: Secure-Serverless-LambdaSecurityGroup
```

SAM imports:

```yaml
Fn::ImportValue: !Sub "${InitResourceStack}-LambdaSecurityGroup"
```

This decouples network stack from app stack.

### Pros & cons of VPC-attached serverless

| Pros | Cons |
|------|------|
| Database never public | Lambda cold starts slower |
| Network-layer isolation | NAT Gateway cost |
| Security groups as defense in depth | More moving parts to debug |
| Matches enterprise patterns | Need VPC endpoints for best performance/cost |

---

## 4. Amazon Aurora (RDS) PostgreSQL

### Definition

**Amazon Aurora** is AWS's cloud-native relational database. **Aurora PostgreSQL** is wire-compatible with PostgreSQL. AWS manages storage replication, backups, patching, and failover.

**RDS** is the umbrella service; Aurora is one engine option (others: PostgreSQL non-Aurora, MySQL, etc.).

### What is configured (`init-template.yml`)

```yaml
AuroraDBCluster:
  Engine: aurora-postgresql
  EngineVersion: "17.4"
  DatabaseName: unicorn_customization
  MasterUsername: admin
  MasterUserPassword: !Ref DbPassword
  DBSubnetGroupName: !Ref AuroraSubnetGroup   # private subnets only
  VpcSecurityGroupIds:
    - !Ref AuroraSecurityGroup

AuroraDBInstance:
  DBInstanceClass: db.t3.medium
  DBClusterIdentifier: !Ref AuroraDBCluster
```

**Aurora architecture:**

- **Cluster** — shared storage volume (6 copies across AZs), cluster endpoint DNS name
- **Instance(s)** — compute nodes attached to cluster (`db.t3.medium` here)

**Endpoint types:**

- **Cluster endpoint** — read/write, used as `DB_HOST`
- **Reader endpoint** — read replicas (none configured here)

### Schema (application tables)

From `queries.sql`:

- `"Socks"`, `"Horns"`, `"Glasses"`, `"Capes"` — catalog
- `"Companies"` — partners
- `"Custom_Unicorns"` — designs with FK references

PostgreSQL uses **quoted identifiers** for case-sensitive table names.

### IAM database authentication

**Traditional auth:** static username/password in Secrets Manager.

**This project uses IAM auth:**

1. Lambda execution role has:

   ```yaml
   Action: rds-db:connect
   Resource: arn:aws:rds-db:region:account:dbuser:*/*
   ```

2. At runtime (`db_utils.py`):

   ```python
   boto3.client("rds").generate_db_auth_token(
       DBHostname=host, Port=5432, DBUsername="postgres", Region=region
   )
   ```

   Returns a string used as the **password** in `psycopg2.connect()`.

3. Token properties:
   - Valid ~15 minutes
   - Tied to IAM identity (Lambda role)
   - Requires `GRANT rds_iam TO postgres;` on DB side

4. Connection config:

   ```python
   {
       "host": DB_HOST,
       "user": "postgres",
       "password": <iam_token>,
       "dbname": "unicorn_customization",
       "port": 5432,
       "sslmode": "require",      # encryption in transit
       "connect_timeout": 10,
   }
   ```

**Why SSL:** Aurora requires TLS for IAM auth connections.

### Pros & cons of Aurora PostgreSQL + IAM auth

| Pros | Cons |
|------|------|
| No long-lived DB passwords in Lambda | IAM auth setup is more complex |
| Automatic credential rotation (tokens expire) | `postgres` user must have `rds_iam` role |
| Aurora failover / storage auto-growth | Aurora costs more than plain RDS PostgreSQL |
| PostgreSQL ecosystem (psycopg2) | Lambda opens new connection each invoke (latency) |

**Advanced note:** For high traffic, use **RDS Proxy** between Lambda and Aurora to pool connections. Not in this project.

---

## 5. Amazon DynamoDB

### Definition

**DynamoDB** is a fully managed **NoSQL** key-value/document database. Single-digit millisecond latency at any scale. No servers, no SQL (unless using PartiQL).

### What is configured

**Table 1: Partner mapping**

```yaml
PartnerDDBTable:
  Type: AWS::Serverless::SimpleTable
  Properties:
    PrimaryKey:
      Name: ClientID
      Type: String
    TableName: CustomizeUnicorns-WildRydePartners
```

`AWS::Serverless::SimpleTable` = SAM shorthand for on-demand DynamoDB table with one partition key.

**Usage** (`manage_partners.py`):

```python
ddb_client.put_item(
    TableName=PARTNER_DDB_TABLE,
    Item={
        "ClientID": {"S": client_id},
        "CompanyID": {"S": str(company_id)},
    }
)
```

**Usage** (`authorizer/index.py`):

```python
ddb_client.get_item(
    TableName=COMPANY_DDB_TABLE,
    Key={"ClientID": {"S": payload["client_id"]}}
)
# → CompanyID passed to API handler via authorizer context
```

**Table 2: Analytics**

```yaml
DemandForecastDDBTable:
  PrimaryKey:
    Name: RecordTimeStamp
    Type: String
```

Stores periodic counts from analytics Lambda.

### DynamoDB data model basics

| Concept | In this project |
|---------|-----------------|
| **Partition key** | `ClientID` or `RecordTimeStamp` |
| **Sort key** | None (simple table) |
| **Item** | JSON-like document with typed attributes (`{"S": "..."}`) |
| **Billing** | On-demand (default for SimpleTable) |

### Pros & cons

| Pros | Cons |
|------|------|
| Extremely fast key lookups | No joins — denormalize data |
| Scales automatically | Query patterns must be designed upfront |
| No connection management (HTTP API) | Less suitable for complex relational queries |
| Perfect for token→company mapping | Eventually consistent reads (unless strongly consistent) |

**Why DynamoDB + PostgreSQL?** Relational data (unicorns, parts, FKs) stays in Aurora. Fast auth lookups (client_id → company_id) use DynamoDB so authorizer doesn't hit PostgreSQL on every request.

---

## 6. Amazon Cognito

### Definition

**Amazon Cognito** provides **user directories (User Pools)** and **federated identity**. This project uses a **User Pool** primarily as an **OAuth 2.0 authorization server** for machine-to-machine (client credentials) flows — not end-user sign-up UI.

### What is configured

```yaml
CognitoUserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: !Sub '${AWS::StackName}-users'
```

Minimal pool — workshop adds app clients programmatically.

**Partner onboarding** (`manage_partners.py`):

```python
cognito_client.create_user_pool_client(
    ClientName=company,
    UserPoolId=USER_POOL_ID,
    GenerateSecret=True,
    AllowedOAuthFlows=["client_credentials"],
    AllowedOAuthScopes=["WildRydes/CustomizeUnicorn"],
    AllowedOAuthFlowsUserPoolClient=True,
)
```

### OAuth 2.0 client credentials flow

```
Partner                          Cognito                         API
   │                                │                              │
   │ POST /oauth2/token             │                              │
   │ client_id + client_secret    │                              │
   │─────────────────────────────▶│                              │
   │◀─────────────────────────────│ access_token (JWT)           │
   │                                │                              │
   │ GET /customizations            │                              │
   │ Authorization: Bearer JWT      │                              │
   │───────────────────────────────────────────────────────────────▶│
   │                                │         Authorizer validates │
```

**JWT contents (access token):**

- `iss` — issuer (Cognito user pool URL)
- `sub` — subject (app client UUID)
- `client_id` — OAuth client
- `scope` — `WildRydes/CustomizeUnicorn`
- `token_use` — must be `access`

**Authorizer validates:**

1. Signature against Cognito JWKS (`/.well-known/jwks.json`)
2. Issuer, token type
3. Scope matches required permission
4. DynamoDB lookup for `CompanyID`

### Pros & cons

| Pros | Cons |
|------|------|
| Managed OAuth/OIDC | User Pool config can be confusing |
| JWT standard — works with API Gateway authorizers | Client secrets must be stored by partners securely |
| No custom auth server to build | Limited compared to full IdP (Okta, Auth0) for complex scenarios |
| Integrates with IAM-style authorizer policies | Token validation adds latency |

---

## 7. AWS IAM (Identity and Access Management)

### Definition

**IAM** defines **who** can do **what** on **which resources**. Core entities: users, roles, policies, permission boundaries.

In serverless, the most important IAM concept is the **Lambda execution role**.

### Lambda execution roles in this project

Each Lambda gets an IAM role with trust policy:

```json
{
  "Principal": { "Service": "lambda.amazonaws.com" },
  "Action": "sts:AssumeRole"
}
```

**UnicornPartsFunction policies (effective):**

1. `AWSLambdaBasicExecutionRole` — CloudWatch Logs
2. `AWSLambdaVPCAccessExecutionRole` — ENI management
3. Custom: `rds-db:connect` on `arn:aws:rds-db:region:account:dbuser:*/*`

**ManagePartnerFunction adds:**

- `cognito-idp:*` (broad — workshop simplification)
- `dynamodb:*` (broad)

**CustomUnicornAnalyticsFunction:**

- `AdministratorAccess` — **full AWS account access** (intentionally dangerous for IAM workshop module)

### IAM database auth vs IAM API permissions

| Permission | Purpose |
|------------|---------|
| `rds-db:connect` | Generate IAM auth token + connect as DB user |
| `rds:Connect` | Different — legacy EC2-style |

Resource format for IAM DB auth:

```
arn:aws:rds-db:us-east-1:123456789012:dbuser:cluster-resource-id/postgres
```

This template uses wildcard: `dbuser:*/*` (allows any DB user on any cluster in account — broad).

### EventBridge Scheduler role

```yaml
DemandForecastAnalyticsSchedulerRole:
  Principal: scheduler.amazonaws.com
  Action: lambda:InvokeFunction
  Resource: CustomUnicornAnalyticsFunction.Arn
```

Scheduler **assumes this role** to invoke Lambda — separate from Lambda's own execution role.

### Workshop IAM demo resources (`secure-serverless-template.yaml`)

- **ABACTestUser** — IAM user that can assume `ServerlessABACDemoRole`
- **Permission boundaries** — cap maximum permissions for roles developers create
- **CloudTrail** — logs API calls for audit

### Pros & cons of IAM-centric security

| Pros | Cons |
|------|------|
| Fine-grained, auditable | Policy syntax learning curve |
| No credentials in code | Easy to over-permission (`*` actions) |
| Integrates with all AWS services | Debugging "access denied" requires CloudTrail |
| IAM DB auth eliminates static DB passwords | Wildcard `rds-db:connect` is too broad for production |

---

## 8. AWS SAM & CloudFormation

### Definition

**CloudFormation** — Infrastructure as Code. You declare resources in YAML/JSON; CloudFormation creates/updates/deletes them as a **stack**.

**SAM** — CloudFormation transform (`AWS::Serverless-2016-10-31`) with shortcuts:

- `AWS::Serverless::Function` → Lambda + IAM role + log group
- `AWS::Serverless::Api` → API Gateway REST API
- `AWS::Serverless::SimpleTable` → DynamoDB table

### SAM build/deploy pipeline

```bash
sam build
# 1. Reads template.yaml
# 2. For each CodeUri, installs requirements.txt into .aws-sam/build/
# 3. Uses Docker for python3.9 if available (matches Lambda runtime)

sam deploy --s3-bucket ...
# 1. Packages build artifacts to S3
# 2. Creates/updates CloudFormation stack CustomizeUnicorns
# 3. Creates Lambda versions, API Gateway deployment, permissions
```

### Parameters vs environment variables

```yaml
Parameters:
  DbHost:
    Type: String    # required at deploy — no default

Globals:
  Function:
    Environment:
      Variables:
        DB_HOST: !Ref DbHost   # CloudFormation resolves at deploy time
```

At runtime Lambda sees `DB_HOST=your-cluster.cluster-xxx.amazonaws.com` as a plain env var.

### Pros & cons

| Pros | Cons |
|------|------|
| Reproducible infrastructure | CloudFormation update failures can be painful |
| SAM simplifies Lambda/API boilerplate | Two templates (network + app) = cross-stack dependencies |
| Version controlled | SAM local ≠ exact production VPC behavior |
| Drift detection (CloudFormation) | Learning curve for intrinsic functions (`!Ref`, `!Sub`, `Fn::ImportValue`) |

---

## 9. Amazon S3

### Definition

**S3** is object storage (buckets / keys / objects). Used here for:

1. **SAM deployment artifacts** — Lambda zip packages
2. **CloudTrail logs** (workshop template)
3. **VS Code bootstrap logs** (vscode template)
4. **Workshop asset zip** (optional)

```yaml
DeploymentsS3Bucket:
  Type: AWS::S3::Bucket
```

Output: `DeploymentS3Bucket` → passed to `sam deploy --s3-bucket`.

### Pros & cons

| Pros | Cons |
|------|------|
| Durable (11 9s), cheap storage | Not a filesystem — objects are immutable versions |
| Required for large Lambda packages | Public bucket misconfig = data leaks (workshop uses private buckets) |
| Integrates with CloudFormation/SAM | |

---

## 10. Amazon EventBridge Scheduler

### Definition

**EventBridge Scheduler** is a managed cron/rate scheduler. It invokes targets (Lambda, SQS, etc.) on a schedule with optional flexible time windows.

### Configuration

```yaml
DemandForecastScheduler:
  Type: AWS::Scheduler::Schedule
  Properties:
    ScheduleExpression: "rate(2 minutes)"
    FlexibleTimeWindow:
      Mode: "OFF"
    Target:
      Arn: !GetAtt CustomUnicornAnalyticsFunction.Arn
      RoleArn: !GetAtt DemandForecastAnalyticsSchedulerRole.Arn
```

**Every 2 minutes:**

1. Scheduler assumes `DemandForecastAnalyticsSchedulerRole`
2. Calls `lambda:InvokeFunction` on analytics Lambda
3. Lambda queries PostgreSQL counts → writes DynamoDB item with ISO timestamp key

### vs CloudWatch Events / EventBridge Rules

Scheduler is newer, supports more precise scheduling and retry policies. For simple rate triggers, both work.

### Pros & cons

| Pros | Cons |
|------|------|
| Serverless cron — no EC2 crontab | Cost at high frequency × many schedules |
| IAM-controlled invocation | 2-minute rate is aggressive for demo (cost/noise) |
| Decouples schedule from Lambda code | |

---

## 11. Amazon CloudWatch Logs

### Definition

Every Lambda automatically writes **`stdout`/`stderr`** to CloudWatch Logs log groups `/aws/lambda/{FunctionName}`.

Code uses `print()` extensively:

```python
print("body part to query: " + str(body_part_to_query))
print(traceback.format_exc())
```

**This is how you debug** timeout and configuration errors.

### Pros & cons

| Pros | Cons |
|------|------|
| Automatic with Lambda | Log volume costs money |
| Centralized search | No built-in distributed tracing (use X-Ray optionally) |
| Retention configurable | Sensitive data in logs if you print secrets |

---

## 12. Supporting services (workshop / IDE templates)

### EC2 + SSM (`vscode-server-template.yaml`)

- **EC2** — virtual machine running code-server (browser VS Code)
- **SSM Document** — runs bootstrap shell scripts on instance (install SAM, Docker, psql)
- **CloudFront** — CDN in front of EC2, TLS, restricts origin access via managed prefix list
- **IAM Instance Profile** — `AdministratorAccess` on VS Code instance (workshop convenience — not production pattern)

### CloudTrail (`secure-serverless-template.yaml`)

Logs AWS API calls to S3 bucket for audit/compliance workshops.

### GuardDuty

Threat detection (malicious DNS, compromised instances). Enabled conditionally when `IsWorkshopStudio=yes`.

---

## 13. End-to-end: GET /socks at every layer

| Step | Service | Technical action |
|------|---------|------------------|
| 1 | Client | TLS GET to `execute-api.../dev/socks` |
| 2 | API Gateway | Match Swagger path, stage `dev`, no authorizer (commented) |
| 3 | API Gateway | `aws_proxy` POST invoke to `UnicornPartsFunction` |
| 4 | Lambda | Cold/warm start in VPC ENI |
| 5 | Lambda | `unicorn_parts.lambda_handler(event, context)` |
| 6 | IAM | Lambda role calls `sts` implicitly via boto3 credentials |
| 7 | IAM/RDS | `generate_db_auth_token()` using `rds-db:connect` |
| 8 | VPC/SG | TCP 5432 from Lambda ENI to Aurora ENI |
| 9 | Aurora | PostgreSQL auth via IAM, SSL, `SELECT * FROM "Socks"` |
| 10 | Lambda | Build `{statusCode:200, body: JSON}` |
| 11 | API Gateway | Return HTTP 200 to client |

**Typical timing:** warm ~200–800ms; cold VPC ~3–15s; timeout error ~10–13s (connect_timeout).

---

## 14. Production vs this workshop (honest assessment)

| Area | This project | Production best practice |
|------|--------------|-------------------------|
| IAM policies | `cognito-idp:*`, `dynamodb:*`, `AdministratorAccess` | Least privilege per action/resource |
| Network | Broad SG CIDR rules | SG-to-SG only, VPC endpoints for AWS APIs |
| Auth | Authorizer commented out initially | Always on for protected routes |
| DB connections | Open/close per Lambda invoke | RDS Proxy connection pooling |
| Secrets | IAM auth (good) | + Secrets Manager for any remaining secrets |
| API | REST API Swagger 2.0 | Consider HTTP API v2 for cost/simplicity |
| Monitoring | print statements | Structured logging, X-Ray tracing, alarms |

---

## 15. Quick reference — all Lambda functions

| Function | Trigger | VPC | Key permissions | Data stores |
|----------|---------|-----|-----------------|-------------|
| `UnicornPartsFunction` | API GET /socks,/horns,/glasses,/capes | Yes | rds-db:connect | Aurora |
| `CustomizeUnicornFunction` | API /customizations* | Yes | rds-db:connect | Aurora |
| `ManagePartnerFunction` | API POST /partners | Yes | rds-db, cognito, dynamodb | Aurora, Cognito, DDB |
| `CustomUnicornAnalyticsFunction` | Schedule 2 min | Yes | **AdministratorAccess**, rds-db | Aurora, DDB |
| Authorizer (separate) | API Gateway TOKEN | Typically no VPC | dynamodb read | DDB, Cognito JWKS |

---

## Further reading

| Topic | Where to go next |
|-------|------------------|
| Lambda VPC networking | [AWS Lambda VPC documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html) |
| IAM DB authentication | [RDS IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html) |
| API Gateway authorizers | [API Gateway custom authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-use-lambda-authorizer.html) |
| SAM transform | [AWS SAM resource types](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html) |
