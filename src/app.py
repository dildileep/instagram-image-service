import os
import json
import uuid
import time
import boto3
from urllib.parse import unquote_plus

IMAGE_BUCKET = os.environ.get("IMAGE_BUCKET")
TABLE_NAME = os.environ.get("TABLE_NAME")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body), "headers": {"Content-Type": "application/json"}}


def lambda_handler(event, context):
    # API Gateway proxy event
    http_method = event.get("httpMethod")
    path = event.get("path", "")
    raw_qs = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}
    body = event.get("body")
    try:
        if body and event.get("isBase64Encoded"):
            # if base64, API expects presigned approach so usually not used
            pass
    except Exception:
        pass

    # Routing
    if http_method == "POST" and path.endswith("/images"):
        return create_image(event)
    if http_method == "GET" and path.endswith("/images") and not path_params.get("image_id"):
        return list_images(event)
    # GET /images/{image_id}
    if http_method == "GET" and "/images/" in path:
        image_id = path.split("/images/")[-1]
        image_id = unquote_plus(image_id)
        return get_image(event, image_id)
    # DELETE /images/{image_id}
    if http_method == "DELETE" and "/images/" in path:
        image_id = path.split("/images/")[-1]
        image_id = unquote_plus(image_id)
        return delete_image(event, image_id)

    return response(404, {"message": "Not Found"})


def create_image(event):
    """
    Create an image metadata record and return a presigned PUT URL for the client to upload.

    Expected JSON body:
    {
      "user_id": "user123",
      "filename": "photo.jpg",
      "content_type": "image/jpeg",       # optional, default application/octet-stream
      "tags": ["vacation", "beach"],
      "description": "..."
    }
    """
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"message": "Invalid JSON"})

    user_id = payload.get("user_id")
    filename = payload.get("filename")
    content_type = payload.get("content_type", "application/octet-stream")
    tags = payload.get("tags", [])
    description = payload.get("description", "")

    if not user_id or not filename:
        return response(400, {"message": "user_id and filename are required"})

    image_id = str(uuid.uuid4())
    key = f"{user_id}/{image_id}/{filename}"

    # store metadata in DynamoDB (object may be uploaded shortly after)
    item = {
        "image_id": image_id,
        "user_id": user_id,
        "s3_key": key,
        "filename": filename,
        "content_type": content_type,
        "tags": tags,
        "description": description,
        "created_at": int(time.time())
    }
    table.put_item(Item=item)

    # generate presigned PUT URL
    put_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": IMAGE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=900  # 15 minutes
    )

    return response(201, {"image_id": image_id, "upload_url": put_url, "s3_key": key})


def list_images(event):
    """
    List images. Support filters via query params:
      - user_id
      - tag  (single tag; for multiple tags, call multiple times or extend)
      - from_ts, to_ts (unix timestamps)
      - limit
    """
    qs = event.get("queryStringParameters") or {}
    user_id = qs.get("user_id")
    tag = qs.get("tag")
    from_ts = qs.get("from_ts")
    to_ts = qs.get("to_ts")
    limit = int(qs.get("limit", "50"))

    # If user_id provided, use GSI to query
    items = []
    if user_id:
        resp = table.query(IndexName="UserIndex", KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id), Limit=limit)
        items = resp.get("Items", [])
    else:
        # scan (for demo; in prod use better patterns)
        resp = table.scan(Limit=limit)
        items = resp.get("Items", [])

    # apply tag and timestamp filters in memory
    if tag:
        items = [i for i in items if tag in (i.get("tags") or [])]
    if from_ts or to_ts:
        try:
            fts = int(from_ts) if from_ts else None
            tts = int(to_ts) if to_ts else None
            def in_range(i):
                ca = int(i.get("created_at", 0))
                if fts and ca < fts:
                    return False
                if tts and ca > tts:
                    return False
                return True
            items = [i for i in items if in_range(i)]
        except ValueError:
            return response(400, {"message": "from_ts and to_ts must be integers"})

    # For each item, add a 'download_url' (short-lived)
    for i in items:
        try:
            i["download_url"] = s3.generate_presigned_url("get_object", Params={"Bucket": IMAGE_BUCKET, "Key": i["s3_key"]}, ExpiresIn=300)
        except Exception:
            i["download_url"] = None

    return response(200, {"items": items})


def get_image(event, image_id):
    # fetch metadata, return presigned GET URL
    resp = table.get_item(Key={"image_id": image_id})
    item = resp.get("Item")
    if not item:
        return response(404, {"message": "Image not found"})
    try:
        url = s3.generate_presigned_url("get_object", Params={"Bucket": IMAGE_BUCKET, "Key": item["s3_key"]}, ExpiresIn=300)
    except Exception as e:
        return response(500, {"message": "Could not generate URL", "error": str(e)})

    item["download_url"] = url
    return response(200, item)


def delete_image(event, image_id):
    # Get item
    resp = table.get_item(Key={"image_id": image_id})
    item = resp.get("Item")
    if not item:
        return response(404, {"message": "Image not found"})

    # Delete object from S3
    try:
        s3.delete_object(Bucket=IMAGE_BUCKET, Key=item["s3_key"])
    except Exception as e:
        # continue to remove metadata, but report
        pass

    # Delete from DynamoDB
    table.delete_item(Key={"image_id": image_id})
    return response(200, {"message": "Deleted", "image_id": image_id})
