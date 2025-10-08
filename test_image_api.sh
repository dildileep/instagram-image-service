#!/bin/bash
API_URL="https://78lf4caa92.execute-api.us-east-1.amazonaws.com/Prod"
USER_ID="u1"
FILENAME="pic.jpg"
CONTENT_TYPE="image/jpeg"

echo "=== 1️⃣ Creating image ==="
CREATE_RESPONSE=$(curl -s -X POST "$API_URL/images" \
-H "Content-Type: application/json" \
-d '{
  "user_id": "'"$USER_ID"'",
  "filename": "'"$FILENAME"'",
  "content_type": "'"$CONTENT_TYPE"'",
  "tags": ["vacation","test"],
  "description": "Testing upload"
}')
echo "$CREATE_RESPONSE"

IMAGE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.image_id')
UPLOAD_URL=$(echo "$CREATE_RESPONSE" | jq -r '.upload_url')
S3_KEY=$(echo "$CREATE_RESPONSE" | jq -r '.s3_key')

echo "Image ID: $IMAGE_ID"
echo "Upload URL: $UPLOAD_URL"
echo "S3 Key: $S3_KEY"

echo
echo "=== 2️⃣ Listing images ==="
curl -s "$API_URL/images?user_id=$USER_ID&limit=10" | jq

echo
echo "=== 3️⃣ Getting single image ==="
curl -s "$API_URL/images/$IMAGE_ID" | jq

echo
echo "=== 4️⃣ Deleting image ==="
curl -s -X DELETE "$API_URL/images/$IMAGE_ID" | jq

echo
echo "✅ Done!"
