# Image Service (Lambda + API Gateway + S3 + DynamoDB)

## Prerequisites
- AWS CLI configured with credentials
- AWS SAM CLI installed
- Python 3.7+
- Docker (optional for sam build)

## Build & Deploy (SAM)

1. Clone repo and cd into folder:
   ```bash
   cd instagram-image-service
Build:


sam build
Deploy (guided):

sam deploy --guided
During --guided set:

Stack Name: image-service

AWS Region: e.g. us-east-1

Confirm changesets: yes

Allow SAM to create roles: yes

Save arguments to samconfig: yes (optional)

After deploy, SAM prints the ApiUrl output, e.g. https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod