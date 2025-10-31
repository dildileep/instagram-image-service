# 📸 Instagram Image Service (Lambda + API Gateway + S3 + DynamoDB)

A fully serverless image management backend built on AWS. This service allows you to upload images using **S3 presigned URLs**, and manage image metadata (like tags, descriptions, and user IDs) via a REST API.

---

## ✅ Prerequisites

Before deploying, ensure you have the following installed and configured:

- ✅ [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) with valid credentials  
- ✅ [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)  
- ✅ Python 3.7+  
- ✅ [jq](https://stedolan.github.io/jq/) (for parsing JSON in bash scripts):  

```bash
# Install jq
sudo apt install jq       # Ubuntu/Debian
brew install jq           # macOS


git clone https://github.com/dildileep/instagram-image-service.git
cd instagram-image-service


sam build


sam deploy --guided