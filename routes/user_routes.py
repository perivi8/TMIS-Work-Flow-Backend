import random
import string
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from pymongo import MongoClient
from flask_jwt_extended import create_access_token, jwt_required
from models.user import User
from bson import ObjectId
import os
import smtplib
from email.mime.text import MIMEText

user_bp = Blueprint('user', __name__)
client = MongoClient(os.getenv("MONGO_URI"))
db = client.EmployeeManagement


def send_verification_email(email, code):
    msg = MIMEText(f"Your verification code is: {code}")
    msg['Subject'] = "Email Verification"
    msg['From'] = os.getenv("SMTP_USER")
    msg['To'] = email

    with smtplib.SMTP(os.getenv("SMTP_SERVER"), os.getenv("SMTP_PORT")) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)


# ✅ Get all users (only verified)
@user_bp.route('/', methods=['GET', 'OPTIONS'])
@jwt_required(optional=True)
def get_users():
    if request.method == "OPTIONS":
        return '', 200

    # Return only users who are verified
    users = list(db.users.find({"is_verified": True}, {"password_hash": 0}))
    for user in users:
        user["_id"] = str(user["_id"])
    return jsonify(users), 200


# ✅ User detail
@user_bp.route('/<user_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@jwt_required(optional=True)
def user_detail(user_id):
    if request.method == "OPTIONS":
        return '', 200

    user = db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    if request.method == "GET":
        user["_id"] = str(user["_id"])
        return jsonify(user), 200

    if request.method == "PUT":
        data = request.json
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": data})
        return jsonify({"msg": "User updated"}), 200

    if request.method == "DELETE":
        db.users.delete_one({"_id": ObjectId(user_id)})
        return jsonify({"msg": "User deleted"}), 200


# ✅ Register with rules
@user_bp.route('/register', methods=['POST'])
def register():
    data = request.json

    required = ['username', 'email', 'password', 'confirm_password', 'employee_id']
    if not all(field in data and data[field] for field in required):
        return jsonify({"msg": "All fields are required!"}), 400

    # Confirm password check
    if data['password'] != data['confirm_password']:
        return jsonify({"msg": "Passwords do not match!"}), 400

    # Email duplicate check
    if db.users.find_one({"email": data['email']}):
        return jsonify({"msg": "User with this email already exists!"}), 400

    # Employee ID checks
    if not data['employee_id'].startswith("TMS"):
        return jsonify({"msg": "Employee ID must start with 'TMS'"}), 400

    if db.users.find_one({"employee_id": data['employee_id']}):
        return jsonify({"msg": "Employee ID already exists!"}), 400

    # Role detection by password prefix
    if data['password'].startswith("Admin123"):
        role = "Admin"
    elif data['password'].startswith("Manager123"):
        role = "Manager"
    else:
        role = "Employee"

    # Create user object
    user = User(data['username'], data['email'], data['password'], role)

    # Email verification code
    verification_code = ''.join(random.choices(string.digits, k=6))
    verification_expiry = datetime.utcnow() + timedelta(minutes=10)

    db.users.insert_one({
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": role,
        "employee_id": data['employee_id'],
        "is_verified": False,
        "verification_code": verification_code,
        "verification_expiry": verification_expiry
    })

    send_verification_email(user.email, verification_code)

    return jsonify({"msg": "Verification code sent to email"}), 201


# ✅ Verify Email
@user_bp.route('/verify-email', methods=['POST'])
def verify_email():
    data = request.json
    user = db.users.find_one({"email": data['email']})

    if not user:
        return jsonify({"msg": "User not found"}), 404

    if user.get("verification_code") != data['code']:
        return jsonify({"msg": "Invalid code"}), 400

    if datetime.utcnow() > user.get("verification_expiry"):
        return jsonify({"msg": "Code expired"}), 400

    db.users.update_one(
        {"email": data['email']},
        {"$set": {"is_verified": True}, "$unset": {"verification_code": "", "verification_expiry": ""}}
    )
    return jsonify({"msg": "Email verified successfully"}), 200


# ✅ Resend Code
@user_bp.route('/resend-code', methods=['POST'])
def resend_code():
    data = request.json
    user = db.users.find_one({"email": data['email']})

    if not user:
        return jsonify({"msg": "User not found"}), 404

    if user.get("is_verified"):
        return jsonify({"msg": "Email already verified"}), 400

    verification_code = ''.join(random.choices(string.digits, k=6))
    verification_expiry = datetime.utcnow() + timedelta(minutes=10)

    db.users.update_one(
        {"email": data['email']},
        {"$set": {"verification_code": verification_code, "verification_expiry": verification_expiry}}
    )

    send_verification_email(user['email'], verification_code)
    return jsonify({"msg": "New verification code sent"}), 200


# ✅ Login → only allowed if verified
@user_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    user = db.users.find_one({"email": data['email']})

    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401

    if not user.get("is_verified"):
        return jsonify({"msg": "Please verify your email before logging in"}), 403

    temp_user = User(user['username'], user['email'], "", user['role'])
    temp_user.password_hash = user['password_hash']

    if temp_user.verify_password(data['password']):
        token = create_access_token(identity=str(user['_id']))
        return jsonify({
            "token": token,
            "role": user['role'],
            "username": user['username'],
            "employee_id": user.get('employee_id', None)
        })

    return jsonify({"msg": "Invalid credentials"}), 401
