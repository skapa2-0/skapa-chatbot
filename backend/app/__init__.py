from flask import Flask
from flask_cors import CORS

from .config import Config
from .models import db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Le widget doit pouvoir appeler l'API depuis n'importe quel site client.
    CORS(app, resources={r"/api/*": {"origins": Config.ALLOWED_ORIGINS}})

    db.init_app(app)
    with app.app_context():
        db.create_all()

    from .routes import bp
    app.register_blueprint(bp)

    return app
