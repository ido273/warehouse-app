import base64
import json
import logging

import boto3
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)

BEDROCK_REGION = "eu-west-1"
BEDROCK_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

# Credentials come from the pod's IRSA-bound service account, never hardcoded.
bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

MOCK_TAGS = ["electronics", "hardware", "PC"]

TAGGING_PROMPT = """You are a warehouse inventory tagging system.
Given an item named '{name}' and its image,
return exactly 5 short relevant tags in JSON format.
Example: ["cable", "usb", "charging", "electronics", "phone"]
Return ONLY the JSON array, nothing else."""


def _fetch_image(image_url):
    resp = requests.get(image_url, timeout=10)
    resp.raise_for_status()
    media_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return base64.b64encode(resp.content).decode("utf-8"), media_type


def _invoke_bedrock(name, image_b64, media_type):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": TAGGING_PROMPT.format(name=name)},
                ],
            }
        ],
    }

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    payload = json.loads(response["body"].read())
    text = payload["content"][0]["text"].strip()
    tags = json.loads(text)

    if not isinstance(tags, list):
        raise ValueError(f"expected a JSON array of tags, got: {tags!r}")

    return tags


def generate_tags(name, image_url):
    try:
        image_b64, media_type = _fetch_image(image_url)
        return _invoke_bedrock(name, image_b64, media_type)
    except Exception:
        logger.exception("Bedrock tagging failed for '%s', falling back to mock tags", name)
        return MOCK_TAGS


@app.route("/suggest-tags", methods=["POST"])
def suggest_tags():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    image_url = data.get("image_url")

    if not name or not image_url:
        return jsonify({"error": "name and image_url are required"}), 400

    return jsonify({"tags": generate_tags(name, image_url)})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
