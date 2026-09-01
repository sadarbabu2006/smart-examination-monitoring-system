"""Flask application factory for the Milestone 1 backend."""

from flask import Flask, jsonify

from .config import Config
from .database.db import init_app


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    init_app(app)

    from .routes.auth_routes import auth_bp
    from .routes.exam_routes import exam_bp
    from .routes.monitoring_routes import monitoring_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(monitoring_bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "smart-examination-monitoring"})

    # --- Candidate Frontend Page Routes ---
    @app.get("/")
    def index():
        from flask import redirect, session
        if session.get("candidate_id"):
            return redirect("/dashboard")
        return redirect("/login")

    @app.get("/register")
    def register_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "register.html")

    @app.get("/login")
    def login_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "login.html")

    @app.get("/dashboard")
    def dashboard_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "dashboard.html")

    @app.get("/profile")
    def profile_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "dashboard.html")


    @app.get("/exam-instructions")
    def instructions_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "instructions.html")

    @app.get("/face-verification")
    def verification_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "verification.html")

    @app.get("/exam")
    def exam_page():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "exam.html")

    @app.get("/exam-client")
    def exam_client():
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", "exam_client.html")

    @app.get("/frontend/static/<path:filename>")
    def static_files(filename):
        from flask import send_from_directory
        from .config import PROJECT_ROOT
        return send_from_directory(PROJECT_ROOT / "frontend" / "static", filename)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "endpoint not found"}), 404

    return app
