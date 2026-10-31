```python
import os
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "message": "Brick Ball Chat backend is online"
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/oauth2callback")
def oauth_callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return jsonify({
            "status": "error",
            "message": error
        }), 400

    if not code:
        return jsonify({
            "status": "error",
            "message": "Authorization code is missing"
        }), 400

    # Token exchange will be implemented next.
    return jsonify({
        "status": "callback_received",
        "message": "Google authorization code received"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
```
