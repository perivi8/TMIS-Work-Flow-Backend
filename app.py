from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from routes.user_routes import user_bp
from routes.task_routes import task_bp
from routes.email_notifications import email_notifications_bp
from routes.status import status_bp    # <-- NEW IMPORT

app = Flask(__name__)
app.config.from_object(Config)

# ✅ Enable CORS for both localhost & Vercel
CORS(app, origins=[
    "http://localhost:4200",
    "https://tmis-work-flow.vercel.app/"
], supports_credentials=True)

# ✅ Automatically allow all OPTIONS requests (preflight)
@app.before_request
def handle_options():
    from flask import request
    if request.method == 'OPTIONS':
        return '', 200

jwt = JWTManager(app)

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(task_bp, url_prefix='/api/tasks')
app.register_blueprint(email_notifications_bp, url_prefix='/api/notifications/emails')
app.register_blueprint(status_bp, url_prefix='/api/status')    # <-- NEW ROUTE

if __name__ == '__main__':
    app.run(debug=True)
