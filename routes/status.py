from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from pymongo import MongoClient
from bson import ObjectId
import os

status_bp = Blueprint('status', __name__)
client = MongoClient(os.getenv("MONGO_URI"))
db = client.EmployeeManagement

@status_bp.route('/summary', methods=['GET'])
@jwt_required()
def status_summary():
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})

    if current_user['role'] == 'Employee':
        tasks = list(db.tasks.find({'assigned_to': current_user['employee_id']}))
    else:
        tasks = list(db.tasks.find())

    assigned = len(tasks)
    completed = sum(t.get('status') == 'Done' for t in tasks)
    in_progress = sum(t.get('status') == 'In Progress' for t in tasks)
    overdue = sum(t.get('status') == 'Overdue' for t in tasks)

    return jsonify({
        'assigned': assigned,
        'completed': completed,
        'in_progress': in_progress,
        'overdue': overdue
    }), 200

@status_bp.route('/update', methods=['POST'])
@jwt_required()
def status_update():
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    data = request.json
    new_status = data.get('status')
    task_id = data.get('task_id')  # can be extended to multiple tasks

    if current_user['role'] != 'Employee':
        return jsonify({"msg": "Not allowed"}), 403

    # Find one specific task
    task = db.tasks.find_one({'_id': ObjectId(task_id), 'assigned_to': current_user['employee_id']})
    if not task:
        return jsonify({"msg": "Task not found or not assigned to you"}), 404

    db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': new_status}})
    return jsonify({"msg": "Status updated"}), 200
