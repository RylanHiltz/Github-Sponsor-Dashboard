import os

from flask import Flask
from backend.api.users import users_bp
from backend.api.statistics import stats_bp
from backend.api.queue import queue_bp
from backend.api.oauth import oauth_bp
from flask_cors import CORS

app = Flask(__name__)
# Needed for OAuth state (session). Set `FLASK_SECRET_KEY` in .env for stable behavior.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
CORS(app)
app.register_blueprint(users_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(queue_bp)
app.register_blueprint(oauth_bp)


@app.route("/")
def index():
    return "Hello World!"


if __name__ == "__main__":
    app.run(debug=True)
