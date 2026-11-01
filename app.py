import os
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")

REDIRECT_URI = "https://brick-ball-chat.hostless.app/oauth2callback"

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"

# Temporary storage for testing.
# Later we will move the refresh token to persistent secure storage.
credentials = {
    "access_token": None,
    "refresh_token": None
}


@app.route("/")
def home():
    return jsonify({
        "message": "Brick Ball Chat backend is online",
        "status": "running"
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/login")
def login():
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({
            "status": "error",
            "message": "YouTube OAuth environment variables are missing"
        }), 500

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    }

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params)
    )

    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth_callback():
    error = request.args.get("error")

    if error:
        return jsonify({
            "status": "error",
            "message": error
        }), 400

    code = request.args.get("code")

    if not code:
        return jsonify({
            "status": "error",
            "message": "Authorization code is missing"
        }), 400

    token_data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        timeout=30
    )

    if response.status_code != 200:
        return jsonify({
            "status": "error",
            "message": "Google token exchange failed",
            "details": response.text
        }), 400

    tokens = response.json()

    credentials["access_token"] = tokens.get("access_token")
    credentials["refresh_token"] = tokens.get("refresh_token")

    return jsonify({
        "status": "authorized",
        "message": "YouTube authorization successful"
    })


@app.route("/youtube/broadcast")
def youtube_broadcast():
    access_token = credentials.get("access_token")

    if not access_token:
        return jsonify({
            "status": "error",
            "message": "YouTube is not authorized. Open /login first."
        }), 401

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    params = {
        "part": "id,snippet",
        "mine": "true",
        "broadcastStatus": "active",
        "broadcastType": "all"
    }

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/liveBroadcasts",
        headers=headers,
        params=params,
        timeout=30
    )

    if response.status_code != 200:
        return jsonify({
            "status": "error",
            "message": "YouTube API request failed",
            "details": response.text
        }), response.status_code

    data = response.json()

    broadcasts = []

    for item in data.get("items", []):
        snippet = item.get("snippet", {})

        broadcasts.append({
            "video_id": item.get("id"),
            "title": snippet.get("title"),
            "live_chat_id": snippet.get("liveChatId")
        })

    return jsonify({
        "status": "ok",
        "broadcasts": broadcasts
    })


@app.route("/youtube/chat")
def youtube_chat():
    access_token = credentials.get("access_token")

    if not access_token:
        return jsonify({
            "status": "error",
            "message": "YouTube is not authorized. Open /login first."
        }), 401

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # First find the active broadcast.
    broadcast_response = requests.get(
        "https://www.googleapis.com/youtube/v3/liveBroadcasts",
        headers=headers,
        params={
            "part": "id,snippet",
            "mine": "true",
            "broadcastStatus": "active",
            "broadcastType": "all"
        },
        timeout=30
    )

    if broadcast_response.status_code != 200:
        return jsonify({
            "status": "error",
            "message": "Could not find active broadcast",
            "details": broadcast_response.text
        }), broadcast_response.status_code

    broadcasts = broadcast_response.json().get("items", [])

    if not broadcasts:
        return jsonify({
            "status": "error",
            "message": "No active YouTube livestream found"
        }), 404

    snippet = broadcasts[0].get("snippet", {})
    live_chat_id = snippet.get("liveChatId")

    if not live_chat_id:
        return jsonify({
            "status": "error",
            "message": "Active broadcast has no live chat ID"
        }), 404

    # Read live chat.
    chat_response = requests.get(
        "https://www.googleapis.com/youtube/v3/liveChat/messages",
        headers=headers,
        params={
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "maxResults": 200
        },
        timeout=30
    )

    if chat_response.status_code != 200:
        return jsonify({
            "status": "error",
            "message": "Could not read live chat",
            "details": chat_response.text
        }), chat_response.status_code

    chat_data = chat_response.json()

    messages = []

    for item in chat_data.get("items", []):
        snippet = item.get("snippet", {})
        author = item.get("authorDetails", {})

        messages.append({
            "id": item.get("id"),
            "author": author.get("displayName"),
            "type": snippet.get("type"),
            "text": snippet.get("displayMessage"),
            "published_at": snippet.get("publishedAt")
        })

    return jsonify({
        "status": "ok",
        "live_chat_id": live_chat_id,
        "polling_interval_ms": chat_data.get("pollingIntervalMillis"),
        "messages": messages
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
