# Wild Rydes Secure Serverless — Beginner's Guide

This document explains **what this project is**, **how AWS Serverless works in this context**, and **what was built step by step**. It assumes you are new to AWS and serverless.

---

## Table of contents

1. [The business story](#1-the-business-story)
2. [What is AWS Serverless?](#2-what-is-aws-serverless)
3. [Big picture architecture](#3-big-picture-architecture)
4. [What this repo contains](#4-what-this-repo-contains)
5. [Infrastructure layer (the foundation)](#5-infrastructure-layer-the-foundation)
6. [The SAM application (the API)](#6-the-sam-application-the-api)
7. [Walkthrough: what happens when you call GET /socks](#7-walkthrough-what-happens-when-you-call-get-socks)
8. [The database](#8-the-database)
9. [Security in this project](#9-security-in-this-project)
10. [Deployment order (step by step)](#10-deployment-order-step-by-step)
11. [What we changed from the original workshop](#11-what-we-changed-from-the-original-workshop)
12. [Workshop security modules (advanced)](#12-workshop-security-modules-advanced)
13. [Glossary](#13-glossary)

---

## 1. The business story

**Wild Rydes** is a fictional ride-sharing company (like Uber, but with unicorns). In this workshop, they offer **unicorn customization**: customers pick socks, horns, glasses, and capes for their unicorn.

This project is a **REST API** that:

- Lists available customization parts (`/socks`, `/horns`, `/glasses`, `/capes`)
- Creates and manages custom unicorn designs (`/customizations`)
- Onboards partner companies who can build integrations (`/partners`)

The original workshop taught **how to secure serverless applications on AWS**. This repo is a **Python port** of that workshop, using **Aurora PostgreSQL** instead of MySQL.

---

## 2. What is AWS Serverless?

Traditional apps run on servers you manage 24/7. **Serverless** means AWS runs the compute for you—you only pay when code executes.

| AWS service | Role in this project |
|-------------|----------------------|
| **Lambda** | Runs your Python code when an API is called. No servers to patch. |
| **API Gateway** | The public front door. Maps URLs like `/socks` to Lambda functions. |
| **Aurora (RDS)** | Managed PostgreSQL database for unicorn parts and customizations. |
| **DynamoDB** | Fast NoSQL database for partner metadata and analytics. |
| **Cognito** | User identity — issues OAuth tokens for API access. |
| **VPC** | Private network where Lambda and Aurora live (not on the public internet). |
| **IAM** | Permissions — who can connect to the database, invoke Lambdas, etc. |
| **CloudFormation / SAM** | Infrastructure as code — deploy everything from YAML templates. |

**SAM** (Serverless Application Model) is an extension of CloudFormation specifically for Lambda + API Gateway apps. You run `sam build` and `sam deploy` to publish the API.

---

## 3. Big picture architecture

```
┌─────────────┐     HTTPS      ┌──────────────────┐     invoke     ┌─────────────────┐
│   Browser   │ ──────────────▶│   API Gateway    │ ──────────────▶│  Lambda (VPC)   │
│  or curl    │                │  /dev/socks      │                │ unicorn_parts.py│
└─────────────┘                └──────────────────┘                └────────┬────────┘
                                                                            │
                                                                            │ IAM auth + SQL
                                                                            ▼
                                                                   ┌─────────────────┐
                                                                   │ Aurora PostgreSQL│
                                                                   │  table "Socks"   │
                                                                   └─────────────────┘
```

**Key idea:** The user never talks to Lambda or the database directly. API Gateway receives the HTTP request, starts a Lambda function, Lambda queries the database, and returns JSON.

Lambda functions run **inside a VPC** (Virtual Private Cloud) so they can reach Aurora on a private network. That requires **security groups** (firewall rules) allowing traffic on port **5432** (PostgreSQL).

---

## 4. What this repo contains

```
secure-serverless/
├── apiclient/              Web UI to test the API from your browser
├── bootstrap.sh            Optional script run on VS Code Server instances
├── docs/                   Documentation (this file)
├── secure-serverless-template.yaml   CloudFormation: VPC, subnets, security groups
├── vscode-server-template.yaml       CloudFormation: browser-based IDE for workshops
└── src/
    ├── app/                Lambda function code (Python)
    ├── authorizer/         JWT token validator for protected API routes
    ├── init/               Database schema + optional Aurora bootstrap template
    └── template.yaml       SAM template — defines the whole API
```

---

## 5. Infrastructure layer (the foundation)

Before the API works, AWS needs networking and permissions.

### 5.1 VPC (Virtual Private Cloud)

A **VPC** is your private slice of the AWS network (`10.0.0.0/16` in this project).

| Subnet | Purpose |
|--------|---------|
| **Public subnets** | Can reach the internet (NAT gateway, VS Code Server) |
| **Private subnets** | Lambda and Aurora live here — not directly exposed |

### 5.2 Security groups

Security groups are **firewalls** attached to resources.

- **Lambda security group** — allows outbound HTTPS (for AWS APIs) and PostgreSQL (port 5432) to the database
- **Aurora security group** — allows inbound PostgreSQL from the VPC (and from Lambda's security group)

Without matching rules on **both sides**, Lambda gets **connection timeout** when calling Aurora — a common issue we fixed in this project.

### 5.3 Templates

| File | What it deploys |
|------|-----------------|
| `secure-serverless-template.yaml` | VPC, NAT, Lambda SG, S3 deploy bucket, workshop IAM demos |
| `src/init/init-template.yml` | Same VPC setup **plus** Aurora PostgreSQL 17 cluster + Cloud9 |
| `vscode-server-template.yaml` | EC2 with code-server (browser VS Code) for workshop participants |

Stack name is typically **`Secure-Serverless`**. It **exports** values (subnet IDs, security group ID) that the SAM app imports.

---

## 6. The SAM application (the API)

File: `src/template.yaml`

This defines **four Lambda functions** and **one API Gateway**:

### 6.1 `UnicornPartsFunction` → `unicorn_parts.py`

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/socks` | GET | Open (Module 0) | List sock options |
| `/horns` | GET | Open | List horn options |
| `/glasses` | GET | Open | List glasses options |
| `/capes` | GET | Open | List cape options |

This is the **simplest** function — read-only, no login required in early workshop modules.

### 6.2 `CustomizeUnicornFunction` → `customize_unicorn.py`

| Route | Method | Purpose |
|-------|--------|---------|
| `/customizations` | GET | List all custom unicorns for a company |
| `/customizations` | POST | Create a new custom unicorn |
| `/customizations/{id}` | GET | Get one customization |
| `/customizations/{id}` | DELETE | Delete a customization |

Uses the **authorizer** to identify which partner company is calling (via JWT token).

### 6.3 `ManagePartnerFunction` → `manage_partners.py`

| Route | Method | Purpose |
|-------|--------|---------|
| `/partners` | POST | Register a new partner company |

Creates:
1. A row in PostgreSQL `Companies` table
2. A **Cognito app client** (Client ID + Secret) for OAuth
3. A row in **DynamoDB** linking Client ID → Company ID

### 6.4 `CustomUnicornAnalyticsFunction` → `custom_unicorn_analytics.py`

Not called via API directly. Triggered on a **schedule** (every 2 minutes) by EventBridge Scheduler.

Counts rows in each body-part table and writes metrics to DynamoDB. Used in later workshop modules about **over-permissioned Lambda roles** (it intentionally has `AdministratorAccess` for demo purposes).

### 6.5 Shared configuration (Globals)

Every Lambda gets these environment variables:

| Variable | Meaning |
|----------|---------|
| `DB_HOST` | Aurora cluster endpoint (required at deploy) |
| `DB_USER` | Database user (`postgres`) |
| `DB_NAME` | Database name (`unicorn_customization`) |
| `DB_USE_IAM_AUTH` | `true` — use IAM tokens instead of passwords |

---

## 7. Walkthrough: what happens when you call GET /socks

This traces the code in `unicorn_parts.py` end to end.

### Step 1 — You send a request

```bash
curl -s "https://YOUR-API.execute-api.us-east-1.amazonaws.com/dev/socks"
```

### Step 2 — API Gateway receives it

API Gateway matches `GET /socks` to `UnicornPartsFunction` (defined in `template.yaml`).

It builds an **event** object — a JSON document describing the HTTP request — and passes it to Lambda:

```json
{
  "httpMethod": "GET",
  "resource": "/socks",
  "path": "/socks",
  ...
}
```

### Step 3 — Lambda handler runs

```python
def lambda_handler(event, context):
```

1. Checks `event["httpMethod"] == "GET"`
2. Reads `event["resource"]` → `"/socks"`
3. Maps `/socks` → database table name `"Socks"`
4. Calls `db_utils.list_body_part_options("Socks")`

### Step 4 — Database query

`db_utils.py`:

1. Reads `DB_HOST`, `DB_USER`, etc. from environment
2. Generates an **IAM auth token** (temporary password, valid ~15 minutes)
3. Opens a PostgreSQL connection with `sslmode=require`
4. Runs: `SELECT * FROM "Socks"`
5. Returns rows as Python dictionaries

### Step 5 — Response back to you

Lambda returns:

```json
{
  "statusCode": 200,
  "headers": { "Access-Control-Allow-Origin": "*", ... },
  "body": "[{\"ID\": 1, \"NAME\": \"Basic\", \"PRICE\": 0.0}, ...]"
}
```

API Gateway forwards the body to your browser/curl.

### If something fails

The `try/except` block catches errors (timeout, auth failure, missing table) and returns a readable error message instead of a generic "Internal server error".

---

## 8. The database

### 8.1 Engine

**Aurora PostgreSQL 17** — Amazon's managed PostgreSQL-compatible database.

The original workshop used **MySQL on Aurora**. We migrated to PostgreSQL:
- Port **5432** (MySQL uses 3306)
- Different SQL syntax (`SERIAL` instead of `AUTO_INCREMENT`, quoted identifiers)

### 8.2 Schema (`src/init/db/queries.sql`)

| Table | Contents |
|-------|----------|
| `Socks`, `Horns`, `Glasses`, `Capes` | Catalog of parts with names and prices |
| `Companies` | Partner companies |
| `Custom_Unicorns` | Saved designs linking a company to chosen parts |

Seed data includes options like "Elvis Presley style" glasses and "Rainbow" capes.

### 8.3 IAM database authentication

Instead of storing a database password in code:

1. Lambda's IAM role has `rds-db:connect` permission
2. At runtime, `boto3` calls `generate_db_auth_token()`
3. That token is used as the PostgreSQL password
4. Aurora validates it against IAM

One-time setup on the database:

```sql
GRANT rds_iam TO postgres;
```

No passwords are hardcoded in the repository.

---

## 9. Security in this project

The workshop progressively adds security layers:

### 9.1 Network isolation (Module 1–2)

- Aurora in **private subnets** — not reachable from the public internet
- Lambda in VPC — can reach Aurora internally
- Security groups restrict who can talk on port 5432

### 9.2 API Gateway + Lambda (Module 3)

- HTTPS only at the edge
- Each route maps to a specific function (least exposure)

### 9.3 Cognito + Custom Authorizer (Module 4+)

File: `src/authorizer/index.py`

For protected routes:

1. Client sends `Authorization: Bearer <JWT token>`
2. **Authorizer Lambda** validates the JWT against Cognito's public keys
3. Checks OAuth **scopes** (e.g. `WildRydes/CustomizeUnicorn`)
4. Looks up **Company ID** in DynamoDB from the token's client ID
5. Returns an IAM policy allowing or denying the API call
6. Passes `CompanyID` to the handler so partners only see their data

### 9.4 IAM roles per function

Each Lambda has its own IAM role with only the permissions it needs (in theory — the analytics function is deliberately over-permissioned for the workshop demo).

### 9.5 Secrets

- Database: IAM tokens (no static password in code)
- Cognito client secrets: generated at runtime when creating partners
- Deploy-time passwords: CloudFormation parameters with `NoEcho: true`

---

## 10. Deployment order (step by step)

### Phase 1 — Foundation

```bash
# Deploy VPC, subnets, security groups, S3 bucket
aws cloudformation deploy \
  --template-file secure-serverless-template.yaml \
  --stack-name Secure-Serverless \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    DbPassword='YOUR-STRONG-PASSWORD' \
    WorkshopDemoUserPassword='YOUR-DEMO-USER-PASSWORD'
```

### Phase 2 — Database (if not using existing Aurora)

Either use `src/init/init-template.yml` to create Aurora, or point to your own cluster.

Apply schema:

```bash
export RDSHOST="your-cluster-endpoint"
export PGPASSWORD="$(aws rds generate-db-auth-token ...)"
psql "host=$RDSHOST ... dbname=unicorn_customization ..." -f src/init/db/queries.sql
```

Fix security groups if Lambda cannot reach Aurora (see README troubleshooting).

### Phase 3 — SAM application

```bash
cd src
sam build                    # Install Python deps, package Lambdas
sam deploy \
  --stack-name CustomizeUnicorns \
  --s3-bucket YOUR-DEPLOY-BUCKET \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides DbHost='your-cluster-endpoint'
```

### Phase 4 — Test

```bash
curl -s "https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/dev/socks" | jq .
```

Or open `apiclient/index.html` in Live Preview.

### Optional — VS Code Server (workshop IDE)

```bash
aws cloudformation deploy \
  --template-file vscode-server-template.yaml \
  --stack-name VSCodeServer \
  --capabilities CAPABILITY_NAMED_IAM
```

Opens a browser-based VS Code at a CloudFront URL with SAM, Docker, and `psql` pre-installed.

---

## 11. What we changed from the original workshop

| Area | Original | This project |
|------|----------|--------------|
| Language | Node.js 22 | **Python 3.9** |
| Database | Aurora MySQL | **Aurora PostgreSQL 17** |
| DB auth | Secrets Manager password | **IAM authentication** |
| DB port | 3306 | **5432** |
| IDE | Cloud9 only | Cloud9 + **VS Code Server template** |
| Credentials | Some defaults in code | **Removed** — required at deploy |
| Error handling | Generic failures | Readable errors in `unicorn_parts.py` |
| Lambda SG | Restrictive egress | VPC CIDR + NAT egress for PostgreSQL |

### Problems we solved

1. **`sam build` failed** — Cloud9 had Python 3.9, not 3.12 → set runtime to `python3.9`
2. **`DB_USER is not defined`** — refactored `db_utils.py` to read config safely at runtime
3. **Connection timeout** — Lambda security group could not reach Aurora → fixed SG rules
4. **Wrong auth** — switched from static password to IAM tokens

---

## 12. Workshop security modules (advanced)

The `secure-serverless-template.yaml` also deploys resources for later security lessons:

| Module | Resource | Lesson |
|--------|----------|--------|
| Access Analyzer | CloudTrail + S3 | Detect unintended public access |
| ABAC demo | IAM user `serverless-dev-user` | Attribute-based access control |
| Permission boundaries | IAM policies | Limit what developers can create |
| GuardDuty | Threat detector | Detect suspicious Lambda behavior |
| Analytics Lambda | `AdministratorAccess` | Find over-permissioned functions |

These are **not required** for `/socks` to work but are part of the full workshop curriculum.

---

## 13. Glossary

| Term | Definition |
|------|------------|
| **Lambda** | AWS function-as-a-service; runs code on demand |
| **API Gateway** | Managed HTTP API that triggers Lambda |
| **SAM** | Toolkit to define and deploy serverless apps |
| **VPC** | Isolated virtual network in AWS |
| **Aurora** | AWS managed relational database (PostgreSQL or MySQL) |
| **IAM** | AWS Identity and Access Management — permissions |
| **Cognito** | AWS user directory and OAuth/OIDC provider |
| **DynamoDB** | AWS NoSQL key-value database |
| **Security group** | Virtual firewall for EC2/Lambda/RDS |
| **JWT** | JSON Web Token — signed token proving identity |
| **OAuth scope** | Permission string embedded in a token |
| **CORS** | Cross-Origin Resource Sharing — lets browsers call the API |
| **CloudFormation** | AWS infrastructure as code (YAML/JSON) |
| **Stack** | A deployed CloudFormation template |
| **Handler** | Entry point function Lambda calls (e.g. `unicorn_parts.lambda_handler`) |

---

## Next steps

1. Deploy the infrastructure and SAM app following [README.md](../README.md)
2. Test `GET /socks` — confirm database connectivity
3. Use `apiclient/index.html` to walk through workshop modules
4. Enable the **authorizer** in `template.yaml` (uncomment security sections) for protected routes
5. Explore CloudWatch Logs for each Lambda to see what happens on every request

For operational commands and troubleshooting, see the main [README.md](../README.md).

For a detailed service-by-service technical reference (Lambda, API Gateway, VPC, Aurora, IAM, pros/cons, template configs), see [AWS_SERVICES_TECHNICAL_GUIDE.md](AWS_SERVICES_TECHNICAL_GUIDE.md).
