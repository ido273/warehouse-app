import base64
import json
import logging
import os

import boto3
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "eu-west-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# Credentials come from the pod's IRSA-bound service account, never hardcoded.
bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

MOCK_TAGS = ["electronics", "hardware", "PC"]

TAGGING_PROMPT = """You are a warehouse inventory tagging system.
Given an item named '{name}' and its image,
return exactly 5 short relevant tags in JSON format.
Example: ["cable", "usb", "charging", "electronics", "phone"]
Return ONLY the JSON array, nothing else."""

TEXT_ONLY_PROMPT = """You are a warehouse inventory tagging system.
Given an item named '{name}' (no image available),
return exactly 5 short relevant tags in JSON format.
Example: ["cable", "usb", "charging", "electronics", "phone"]
Return ONLY the JSON array, nothing else."""


def _fetch_image(image_url):
    resp = requests.get(image_url, timeout=10)
    resp.raise_for_status()
    media_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return base64.b64encode(resp.content).decode("utf-8"), media_type


def _invoke_bedrock(content):
    body = {
        "messages": [{"role": "user", "content": content}],
        "inferenceConfig": {"maxTokens": 200},
    }

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    payload = json.loads(response["body"].read())
    text = payload["output"]["message"]["content"][0]["text"].strip()
    tags = json.loads(text)

    if not isinstance(tags, list):
        raise ValueError(f"expected a JSON array of tags, got: {tags!r}")

    return tags


def generate_tags(name, image_url):
    try:
        if image_url:
            image_b64, media_type = _fetch_image(image_url)
            image_format = media_type.split("/")[-1]
            content = [
                {
                    "image": {
                        "format": image_format,
                        "source": {"bytes": image_b64},
                    }
                },
                {"text": TAGGING_PROMPT.format(name=name)},
            ]
        else:
            content = [{"text": TEXT_ONLY_PROMPT.format(name=name)}]

        return _invoke_bedrock(content)
    except Exception:
        logger.exception("Bedrock tagging failed for '%s', falling back to mock tags", name)
        return MOCK_TAGS


@app.route("/tag", methods=["POST"])
def tag_item():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    image_url = data.get("image_url")

    if not name:
        return jsonify({"error": "name is required"}), 400

    return jsonify({"item_id": data.get("item_id"), "tags": generate_tags(name, image_url)})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
