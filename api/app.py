from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://appuser:supersecret@postgres:5432/moviedb")
engine = create_engine(DATABASE_URL, echo=False, future=True)
metadata = MetaData()

movies = Table(
    "movies", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("genre", String(100)),
    Column("status", Boolean, default=False),
    Column("image_url", String(500))
)

# create table if not exists and preload Nolan movies
with engine.begin() as conn:
    metadata.create_all(conn)
    result = conn.execute(movies.select())
    if result.first() is None:
        nolan_movies = [
            {"title": "Inception", "genre": "Sci-Fi", "status": False, "image_url": "https://images.unsplash.com/photo-1524985069026-dd778a71c7b4"},
            {"title": "Interstellar", "genre": "Sci-Fi", "status": False, "image_url": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564"},
            {"title": "The Dark Knight", "genre": "Action", "status": False, "image_url": "https://images.unsplash.com/photo-1517602302552-471fe67acf66"},
            {"title": "Tenet", "genre": "Sci-Fi/Action", "status": False, "image_url": "https://images.unsplash.com/photo-1522120692562-5d7a83e9f50a"}
        ]
        conn.execute(movies.insert(), nolan_movies)

@app.route("/movies", methods=["GET"])
def list_movies():
    with engine.connect() as conn:
        rows = conn.execute(movies.select()).mappings().all()
        return jsonify([dict(r) for r in rows])

@app.route("/movies", methods=["POST"])
def add_movie():
    data = request.get_json() or {}
    with engine.begin() as conn:
        res = conn.execute(movies.insert().values(
            title=data.get("title"),
            genre=data.get("genre"),
            status=False,
            image_url=data.get("image_url")
        ))
        return jsonify({"id": res.inserted_primary_key[0]}), 201

@app.route("/movies/<int:movie_id>", methods=["PUT"])
def mark_watched(movie_id):
    with engine.begin() as conn:
        res = conn.execute(movies.update().where(movies.c.id == movie_id).values(status=True))
        if res.rowcount:
            return jsonify({"status": "updated"})
        return jsonify({"error": "not found"}), 404

@app.route("/movies/<int:movie_id>", methods=["DELETE"])
def delete_movie(movie_id):
    with engine.begin() as conn:
        res = conn.execute(movies.delete().where(movies.c.id == movie_id))
        if res.rowcount:
            return jsonify({"deleted": movie_id})
        return jsonify({"error": "not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
