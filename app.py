import os
import time
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "https://loki9632.github.io"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response
# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")

REDIRECT_URI = (
    "https://brick-ball-chat.hostless.app/oauth2callback"
)

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# --------------------------------------------------
# TEMPORARY STORAGE
# --------------------------------------------------

credentials = {
    "access_token": None,
    "refresh_token": None,
    "expires_at": 0
}

# Live chat polling state
chat_state = {
    "live_chat_id": None,
    "next_page_token": None,
    "initialized": False
}

# Supported free chat commands
GAME_COMMANDS = {
    "!laser",
    "!bigpaddle",
    "!multiball",
    "!slow",
    "!shield",
    "!clearrow"
}


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

def get_access_token():

    access_token = credentials.get("access_token")
    refresh_token = credentials.get("refresh_token")

    if not access_token:
        return None

    # Refresh token if access token is about to expire
    if time.time() >= credentials.get("expires_at", 0) - 60:

        if not refresh_token:
            return None

        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            },
            timeout=30
        )

        if response.status_code != 200:
            print("Token refresh failed:", response.text)
            return None

        tokens = response.json()

        credentials["access_token"] = tokens["access_token"]

        credentials["expires_at"] = (
            time.time() + tokens.get("expires_in", 3600)
        )

        access_token = credentials["access_token"]

    return access_token


# --------------------------------------------------
# YOUTUBE API HELPERS
# --------------------------------------------------

def get_active_broadcast(access_token):

    response = requests.get(
        f"{YOUTUBE_API}/liveBroadcasts",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "part": "id,snippet",
            "broadcastStatus": "active",
            "broadcastType": "all"
        },
        timeout=30
    )

    if response.status_code != 200:
        return None, response

    broadcasts = response.json().get("items", [])

    if not broadcasts:
        return None, None

    return broadcasts[0], None


def read_chat_messages(access_token, live_chat_id, page_token=None):

    params = {
        "liveChatId": live_chat_id,
        "part": "snippet,authorDetails",
        "maxResults": 200
    }

    if page_token:
        params["pageToken"] = page_token

    response = requests.get(
        f"{YOUTUBE_API}/liveChat/messages",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params=params,
        timeout=30
    )

    return response


# --------------------------------------------------
# BASIC ROUTES
# --------------------------------------------------

@app.route("/")
def home():

    return jsonify({
        "message": "Brick Ball Chat backend is online",
        "status": "running"
    })


@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })


# --------------------------------------------------
# GOOGLE LOGIN
# --------------------------------------------------

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


# --------------------------------------------------
# GOOGLE OAUTH CALLBACK
# --------------------------------------------------

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

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        },
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
    credentials["refresh_token"] = (
        tokens.get("refresh_token")
        or credentials.get("refresh_token")
    )

    credentials["expires_at"] = (
        time.time() + tokens.get("expires_in", 3600)
    )

    # Reset chat state after authorization
    chat_state["live_chat_id"] = None
    chat_state["next_page_token"] = None
    chat_state["initialized"] = False

    return jsonify({
        "status": "authorized",
        "message": "YouTube authorization successful"
    })


# --------------------------------------------------
# GET ACTIVE BROADCAST
# --------------------------------------------------

@app.route("/youtube/broadcast")
def youtube_broadcast():

    access_token = get_access_token()

    if not access_token:

        return jsonify({
            "status": "error",
            "message": "YouTube is not authorized. Open /login first."
        }), 401

    broadcast, error_response = get_active_broadcast(access_token)

    if error_response:

        return jsonify({
            "status": "error",
            "message": "YouTube API request failed",
            "details": error_response.text
        }), error_response.status_code

    if not broadcast:

        return jsonify({
            "status": "ok",
            "broadcasts": []
        })

    snippet = broadcast.get("snippet", {})

    return jsonify({
        "status": "ok",
        "broadcasts": [{
            "video_id": broadcast.get("id"),
            "title": snippet.get("title"),
            "live_chat_id": snippet.get("liveChatId")
        }]
    })


# --------------------------------------------------
# READ CHAT MESSAGES
# --------------------------------------------------

@app.route("/youtube/chat")
def youtube_chat():

    access_token = get_access_token()

    if not access_token:

        return jsonify({
            "status": "error",
            "message": "YouTube is not authorized. Open /login first."
        }), 401

    broadcast, error_response = get_active_broadcast(access_token)

    if error_response:

        return jsonify({
            "status": "error",
            "message": "Could not find active broadcast",
            "details": error_response.text
        }), error_response.status_code

    if not broadcast:

        return jsonify({
            "status": "error",
            "message": "No active YouTube livestream found"
        }), 404

    live_chat_id = broadcast.get("snippet", {}).get("liveChatId")

    if not live_chat_id:

        return jsonify({
            "status": "error",
            "message": "Live chat ID not found"
        }), 404

    response = read_chat_messages(
        access_token,
        live_chat_id
    )

    if response.status_code != 200:

        return jsonify({
            "status": "error",
            "message": "Could not read live chat",
            "details": response.text
        }), response.status_code

    data = response.json()

    messages = []

    for item in data.get("items", []):

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
        "polling_interval_ms": data.get("pollingIntervalMillis"),
        "messages": messages
    })


# --------------------------------------------------
# GET NEW GAME COMMANDS
# --------------------------------------------------

@app.route("/youtube/commands")
def youtube_commands():

    access_token = get_access_token()

    if not access_token:

        return jsonify({
            "status": "error",
            "message": "YouTube is not authorized. Open /login first."
        }), 401

    broadcast, error_response = get_active_broadcast(access_token)

    if error_response:

        return jsonify({
            "status": "error",
            "message": "Could not find active broadcast",
            "details": error_response.text
        }), error_response.status_code

    if not broadcast:

        chat_state["live_chat_id"] = None
        chat_state["next_page_token"] = None
        chat_state["initialized"] = False

        return jsonify({
            "status": "ok",
            "commands": [],
            "message": "No active livestream"
        })

    live_chat_id = broadcast.get("snippet", {}).get("liveChatId")

    if not live_chat_id:

        return jsonify({
            "status": "error",
            "message": "Live chat ID not found"
        }), 404

    # Reset state when a different livestream starts
    if chat_state["live_chat_id"] != live_chat_id:

        chat_state["live_chat_id"] = live_chat_id
        chat_state["next_page_token"] = None
        chat_state["initialized"] = False

    response = read_chat_messages(
        access_token,
        live_chat_id,
        chat_state["next_page_token"]
    )

    if response.status_code != 200:

        return jsonify({
            "status": "error",
            "message": "Could not read live chat",
            "details": response.text
        }), response.status_code

    data = response.json()

    new_page_token = data.get("nextPageToken")

    polling_interval = data.get(
        "pollingIntervalMillis", 1000
    )

    # First request establishes a baseline.
    # Existing messages are deliberately ignored.
    if not chat_state["initialized"]:

        chat_state["next_page_token"] = new_page_token
        chat_state["initialized"] = True

        return jsonify({
            "status": "ok",
            "commands": [],
            "message": "Chat initialized. Waiting for new commands.",
            "polling_interval_ms": polling_interval
        })

    commands = []

    for item in data.get("items", []):

        snippet = item.get("snippet", {})
        author = item.get("authorDetails", {})

        # Only normal text messages are free commands.
        if snippet.get("type") != "textMessageEvent":
            continue

        command = (
            snippet.get("displayMessage", "")
            .strip()
            .lower()
        )

        if command in GAME_COMMANDS:

            commands.append({
                "id": item.get("id"),
                "author": author.get("displayName"),
                "command": command,
                "type": "free"
            })

    # Save cursor for the next request.
    if new_page_token:
        chat_state["next_page_token"] = new_page_token

    return jsonify({
        "status": "ok",
        "commands": commands,
        "polling_interval_ms": polling_interval
    })


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
