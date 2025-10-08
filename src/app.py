import os
import json
import uuid
import time
from decimal import Decimal
import boto3
from urllib.parse import unquote_plus

IMAGE_BUCKET = os.environ.get("IMAGE_BUCKET")
TABLE_NAME = os.environ.get("TABLE_NAME")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def decimal_default(obj):
    """Convert DynamoDB Decimal to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "body": json.dumps(body, default=decimal_default),
        "headers": {"Content-Type": "application/json"},
    }


def lambda_handler(event, context):
    http_method = event.get("httpMethod")
    path = event.get("path", "")
    path_params = event.get("pathParameters") or {}

    # Routing
    if http_method == "POST" and path.endswith("/images"):
        return create_image(event)
    if http_method == "GET" and path.endswith("/images") and not path_params.get("image_id"):
        return list_images(event)
    if http_method == "GET" and "/images/" in path:
        image_id = path.split("/images/")[-1]
        image_id = unquote_plus(image_id)
        return get_image(event, image_id)
    if http_method == "DELETE" and "/images/" in path:
        image_id = path.split("/images/")[-1]
        image_id = unquote_plus(image_id)
        return delete_image(event, image_id)

    return response(404, {"message": "Not Found"})


def create_image(event):
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

    item = {
        "image_id": image_id,
        "user_id": user_id,
        "s3_key": key,
        "filename": filename,
        "content_type": content_type,
        "tags": tags,
        "description": description,
        "created_at": int(time.time()),
    }

    table.put_item(Item=item)

    put_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": IMAGE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=900,
    )

    return response(201, {"image_id": image_id, "upload_url": put_url, "s3_key": key})


def list_images(event):
    qs = event.get("queryStringParameters") or {}
    user_id = qs.get("user_id")
    tag = qs.get("tag")
    from_ts = qs.get("from_ts")
    to_ts = qs.get("to_ts")
    limit = int(qs.get("limit", "50"))

    items = []
    if user_id:
        try:
            resp = table.query(
                IndexName="UserIndex",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
                Limit=limit,
            )
            items = resp.get("Items", [])
        except Exception as e:
            return response(500, {"message": "DynamoDB query failed", "error": str(e)})
    else:
        resp = table.scan(Limit=limit)
        items = resp.get("Items", [])

    # Filter by tag
    if tag:
        items = [i for i in items if tag in (i.get("tags") or [])]

    # Filter by timestamp
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

    # Add download URLs
    for i in items:
        try:
            i["download_url"] = s3.generate_presigned_url(
                "get_object", Params={"Bucket": IMAGE_BUCKET, "Key": i["s3_key"]}, ExpiresIn=300
            )
        except Exception:
            i["download_url"] = None

    return response(200, {"items": items})


def get_image(event, image_id):
    try:
        resp = table.get_item(Key={"image_id": image_id})
        item = resp.get("Item")
        if not item:
            return response(404, {"message": "Image not found"})
        item["download_url"] = s3.generate_presigned_url(
            "get_object", Params={"Bucket": IMAGE_BUCKET, "Key": item["s3_key"]}, ExpiresIn=300
        )
        return response(200, item)
    except Exception as e:
        return response(500, {"message": "Failed to fetch image", "error": str(e)})


def delete_image(event, image_id):
    try:
        resp = table.get_item(Key={"image_id": image_id})
        item = resp.get("Item")
        if not item:
            return response(404, {"message": "Image not found"})

        try:
            s3.delete_object(Bucket=IMAGE_BUCKET, Key=item["s3_key"])
        except Exception:
            pass

        table.delete_item(Key={"image_id": image_id})
        return response(200, {"message": "Deleted", "image_id": image_id})
    except Exception as e:
        return response(500, {"message": "Failed to delete image", "error": str(e)})
