import os
import json
import time
import boto3
import pytest
from moto import mock_s3, mock_dynamodb2
from src import app as image_app

TEST_BUCKET = "test-bucket"
TEST_TABLE = "test-table"


@pytest.fixture(autouse=True)
def aws_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield


@pytest.fixture
def aws_resources():
    with mock_s3():
        with mock_dynamodb2():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=TEST_BUCKET)
            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            table = dynamodb.create_table(
                TableName=TEST_TABLE,
                KeySchema=[{"AttributeName": "image_id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "image_id", "AttributeType": "S"},
                                      {"AttributeName": "user_id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
                GlobalSecondaryIndexes=[{
                    "IndexName": "UserIndex",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }],
            )
            table.wait_until_exists()

            # patch environment for the handler
            os.environ["IMAGE_BUCKET"] = TEST_BUCKET
            os.environ["TABLE_NAME"] = TEST_TABLE

            yield


def test_create_and_get_and_delete(aws_resources):
    # Create image
    event = {
        "httpMethod": "POST",
        "path": "/images",
        "body": json.dumps({
            "user_id": "u1",
            "filename": "pic.jpg",
            "content_type": "image/jpeg",
            "tags": ["t1", "t2"],
            "description": "desc"
        }),
        "isBase64Encoded": False
    }
    resp = image_app.lambda_handler(event, None)
    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    image_id = body["image_id"]
    assert "upload_url" in body

    # now simulate upload by putting object to S3
    s3 = boto3.client("s3")
    s3.put_object(Bucket=TEST_BUCKET, Key=f"u1/{image_id}/pic.jpg", Body=b"data", ContentType="image/jpeg")

    # Get image (presigned)
    get_event = {"httpMethod": "GET", "path": f"/images/{image_id}", "queryStringParameters": None, "pathParameters": {"image_id": image_id}}
    get_resp = image_app.lambda_handler(get_event, None)
    assert get_resp["statusCode"] == 200
    gbody = json.loads(get_resp["body"])
    assert gbody["image_id"] == image_id
    assert "download_url" in gbody

    # Delete
    del_event = {"httpMethod": "DELETE", "path": f"/images/{image_id}", "pathParameters": {"image_id": image_id}}
    del_resp = image_app.lambda_handler(del_event, None)
    assert del_resp["statusCode"] == 200

    # subsequent get should be 404
    get_resp2 = image_app.lambda_handler(get_event, None)
    assert get_resp2["statusCode"] == 404


def test_list_and_filters(aws_resources):
    # create several images
    now = int(time.time())
    ids = []
    for u, fname, tags in [
        ("userA", "a.jpg", ["sun"]),
        ("userA", "b.jpg", ["sun", "sea"]),
        ("userB", "c.jpg", ["mountain"])
    ]:
        event = {
            "httpMethod": "POST",
            "path": "/images",
            "body": json.dumps({"user_id": u, "filename": fname, "tags": tags}),
            "isBase64Encoded": False
        }
        resp = image_app.lambda_handler(event, None)
        body = json.loads(resp["body"])
        ids.append(body["image_id"])
        # create placeholder object
        s3 = boto3.client("s3")
        s3.put_object(Bucket=TEST_BUCKET, Key=f"{u}/{body['image_id']}/{fname}", Body=b"data")

    # List userA
    list_event = {"httpMethod": "GET", "path": "/images", "queryStringParameters": {"user_id": "userA", "limit": "10"}}
    list_resp = image_app.lambda_handler(list_event, None)
    assert list_resp["statusCode"] == 200
    items = json.loads(list_resp["body"])["items"]
    assert len(items) == 2

    # Filter by tag
    list_event2 = {"httpMethod": "GET", "path": "/images", "queryStringParameters": {"tag": "mountain"}}
    list_resp2 = image_app.lambda_handler(list_event2, None)
    items2 = json.loads(list_resp2["body"])["items"]
    assert len(items2) == 1
    assert items2[0]["user_id"] == "userB"
