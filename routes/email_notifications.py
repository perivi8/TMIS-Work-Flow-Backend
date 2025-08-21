from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import os

email_notifications_bp = Blueprint('email_notifications', __name__)
client = MongoClient(os.getenv("MONGO_URI"))
db = client.EmployeeManagement

# GET /api/notifications/emails
@email_notifications_bp.route('/', methods=['GET'])
@jwt_required()
def list_email_notifications():
    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user_email = user.get('email')
    if not user_email:
        return jsonify([])

    cursor = db.email_notifications.find(
        {"recipient": user_email}
    ).sort("timestamp", DESCENDING).limit(20)

    emails = []
    for e in cursor:
        e["_id"] = str(e["_id"])
        emails.append(e)
    return jsonify(emails), 200

# POST /api/notifications/emails/mark-read
@email_notifications_bp.route('/mark-read', methods=['POST'])
@jwt_required()
def mark_read():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"msg": "No IDs provided"}), 400

    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user_email = user.get('email')
    if not user_email:
        return jsonify({"msg": "No email"}), 400

    object_ids = []
    for _id in ids:
        try:
            object_ids.append(ObjectId(_id))
        except Exception:
            pass

    if not object_ids:
        return jsonify({"msg": "Invalid IDs"}), 400

    db.email_notifications.update_many(
        {"_id": {"$in": object_ids}, "recipient": user_email},
        {"$set": {"read": True}}
    )
    return jsonify({"success": True}), 200

# POST /api/notifications/emails/remove
@email_notifications_bp.route('/remove', methods=['POST'])
@jwt_required()
def remove_email():
    data = request.get_json(silent=True) or {}
    notif_id = data.get("id")
    if not notif_id:
        return jsonify({"msg": "No ID provided"}), 400

    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user_email = user.get('email')
    if not user_email:
        return jsonify({"msg": "No email"}), 400

    try:
        oid = ObjectId(notif_id)
    except Exception:
        return jsonify({"msg": "Invalid ID"}), 400

    result = db.email_notifications.delete_one({"_id": oid, "recipient": user_email})

    if result.deleted_count == 0:
        return jsonify({"msg": "Notification not found or already removed"}), 404

    return jsonify({"success": True}), 200
