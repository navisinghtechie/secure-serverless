# Secure Serverless (Python)

Python port of the [AWS Serverless Security Workshop](https://github.com/aws-samples/aws-serverless-security-workshop) Wild Rydes API.

## Project layout

```
src/
  app/              Lambda handlers (API)
  authorizer/       Cognito JWT custom authorizer
  init/             VPC / Aurora PostgreSQL 17 bootstrap CloudFormation
  template.yaml     SAM template
apiclient/          Static API test UI (use IDE preview on index.html)
```

## API client (preview)

Open `apiclient/index.html` with your editor's **Simple Browser / Live Preview**:

1. Enter your API Gateway base URL (e.g. `https://xxxx.execute-api.us-east-1.amazonaws.com/dev/`)
2. Use **Module 0** to test `GET /socks` without auth

## Deploy

```bash
cd src
sam build
sam deploy --guided
```

Set the Aurora PostgreSQL endpoint in `src/app/db_utils.py` (`HOST`) before deploying. Initialize schema with `src/init/db/queries.sql` via `psql`.
