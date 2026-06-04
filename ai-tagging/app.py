from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/suggest-tags", methods=["POST"])
def suggest_tags():
    return jsonify({"tags": ["electronics", "hardware", "PC"]})
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
