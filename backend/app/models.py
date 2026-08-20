from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Document(db.Model):
    """Un fragment de contenu issu de la plateforme cible, quelle qu'elle soit.

    `source_type` retient d'où il vient (html, json, wordpress, shopify, pdf,
    supabase...) et `site_id` à quel site client il appartient, ce qui permet
    de servir plusieurs sites depuis la même API sans mélanger les contenus.
    """

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    source_url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(300))
    content = db.Column(db.Text, nullable=False)
    external_id = db.Column(db.String(300), unique=True, index=True, nullable=False)
    source_type = db.Column(db.String(30), default="html", index=True)
    site_id = db.Column(db.String(120), default="default", index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatLog(db.Model):
    """Historique des questions/réponses, utile pour du debug ou des analytics."""

    __tablename__ = "chat_logs"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.String(120))
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
