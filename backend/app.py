from flask import Flask
from backend.api.users import users_bp
from backend.api.statistics import stats_bp
from backend.api.queue import queue_bp
from backend.api.graph import graph_bp
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.register_blueprint(users_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(queue_bp)
app.register_blueprint(graph_bp)


@app.route("/")
def index():
    return "Hello World!"


if __name__ == "__main__":
    app.run(debug=True)
