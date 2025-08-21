from flask import Blueprint, request, jsonify
from pymongo import MongoClient
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.task import Task
from utils.email_utils import send_email
import os
from bson import ObjectId
from datetime import datetime

task_bp = Blueprint('task', __name__)
client = MongoClient(os.getenv("MONGO_URI"))
db = client.EmployeeManagement


def send_assignment_notification(emails, title, deadline, body_extra=''):
  for email in emails:
      send_email(
          subject="New Task Assigned",
          recipient=email,
          body=f"You have been assigned a new task: {title}\nDeadline: {deadline}\n{body_extra}",
          meta={"status": "Assigned", "title": title}
      )


@task_bp.route('/create', methods=['POST'])
@jwt_required()
def create_task():
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})
  if current_user["role"] not in ["Admin", "Manager"]:
      return jsonify({"msg": "You do not have permission to create tasks."}), 403

  data = request.json
  assigned_to = data['assigned_to']  # list of employee_ids
  deadline = data['deadline']
  tasks_created = []

  if data.get('assign_to_all'):
      employees = db.users.find({"role": "Employee"})
      assigned_to = [emp['employee_id'] for emp in employees]

  employees = list(db.users.find({"employee_id": {"$in": assigned_to}, "role": "Employee"}))
  if not employees:
      return jsonify({"msg": "Assigned user(s) must be valid employees."}), 400

  for emp in employees:
      task = Task(
          data['title'], data['description'], emp['employee_id'],
          data['priority'], data['status'], deadline
      )
      t_id = db.tasks.insert_one({
          **task.__dict__,
          "created_by": current_user['username'],
          "created_at": datetime.utcnow().isoformat()
      }).inserted_id
      tasks_created.append(str(t_id))

  send_assignment_notification(
      [emp['email'] for emp in employees],
      data['title'], deadline
  )
  return jsonify({"msg": "Tasks created for assigned employees.", "task_ids": tasks_created}), 201


@task_bp.route('/update/<task_id>', methods=['PUT'])
@jwt_required()
def update_task(task_id):
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})
  data = request.json
  task = db.tasks.find_one({'_id': ObjectId(task_id)})

  if not task:
      return jsonify({"msg": "Task not found"}), 404

  # Prevent updates to overdue tasks by employees (optional stronger lock)
  if task.get('status') == 'Overdue' and current_user['role'] == 'Employee':
      return jsonify({"msg": "Task is overdue and cannot be updated by employee."}), 403

  # Employee updating own task (status changes)
  if current_user['role'] == 'Employee':
      if task['assigned_to'] != current_user['employee_id']:
          return jsonify({"msg": "Can only update your own tasks."}), 403
      new_status = data.get('status')
      if not new_status:
          return jsonify({"msg": "Nothing to update"}), 400
      db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': new_status}})

      # Notify managers/admins when status becomes "In Progress" or "Done"
      if new_status in ['In Progress', 'Done']:
          managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
          meta = {
              "status": new_status,
              "task_id": str(task['_id']),
              "title": task.get('title'),
              "employee_id": current_user['employee_id'],
              "username": current_user['username']
          }
          subject = f"Task {new_status} Notification"
          notify_body = (
              f"Employee ID: {current_user['employee_id']}\n"
              f"Name: {current_user['username']}\n"
              f"Task: {task.get('title')}\n"
              f"Status: {new_status}"
          )
          for mgr in managers:
              send_email(subject=subject, recipient=mgr['email'], body=notify_body, meta=meta)
      return jsonify({"msg": "Task status updated"}), 200

  # Admin/Manager can update full task
  else:
      db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': data})
      return jsonify({"msg": "Task updated"}), 200


@task_bp.route('/complete/<task_id>', methods=['POST'])
@jwt_required()
def complete_task(task_id):
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})
  if current_user['role'] != 'Employee':
      return jsonify({"msg": "Only assigned employees may complete tasks."}), 403

  task = db.tasks.find_one({'_id': ObjectId(task_id)})
  if not task or task['assigned_to'] != current_user['employee_id']:
      return jsonify({"msg": "Not authorized for this task."}), 403

  # Set status to Done
  db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': 'Done'}})

  # Notify managers/admins of submission
  managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
  meta = {
      "status": "Done",
      "task_id": str(task['_id']),
      "title": task.get('title'),
      "employee_id": current_user['employee_id'],
      "username": current_user['username']
  }
  notify_body = (
      f"Employee ID: {current_user['employee_id']}\n"
      f"Name: {current_user['username']}\n"
      f"Task '{task['title']}' has been submitted (Done)."
  )
  for mgr in managers:
      send_email(
          subject="Task Submitted (Done)",
          recipient=mgr['email'],
          body=notify_body,
          meta=meta
      )

  # Also send a notification to employee (receipt)
  send_email(
      subject="Task Completed",
      recipient=current_user['email'],
      body=f"You have completed: {task['title']}!",
      meta=meta
  )
  return jsonify({"msg": "Task completed notification sent!"}), 200


@task_bp.route('/delete/<task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})
  if current_user["role"] not in ["Admin", "Manager"]:
      return jsonify({"msg": "Only admins and managers can delete tasks."}), 403
  db.tasks.delete_one({'_id': ObjectId(task_id)})
  return jsonify({"msg": "Task deleted successfully."}), 200


@task_bp.route('/', methods=['GET'])
@jwt_required()
def get_tasks():
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})

  # Only show tasks assigned to employee, ALL tasks for admin/manager
  if current_user['role'] == 'Employee':
      tasks = list(db.tasks.find({"assigned_to": current_user['employee_id']}))
  else:
      tasks = list(db.tasks.find())

  for t in tasks:
      t["_id"] = str(t["_id"])
  return jsonify(tasks)


@task_bp.route('/<task_id>', methods=['GET'])
@jwt_required()
def get_task(task_id):
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})
  task = db.tasks.find_one({"_id": ObjectId(task_id)})
  if not task:
      return jsonify({"msg": "Task not found"}), 404

  # Employees can only fetch their own tasks
  if current_user['role'] == 'Employee' and task['assigned_to'] != current_user['employee_id']:
      return jsonify({"msg": "Not authorized"}), 403

  task["_id"] = str(task["_id"])
  return jsonify(task)


# NEW: Mark overdue and notify Admin/Manager
@task_bp.route('/mark-overdue/<task_id>', methods=['POST'])
@jwt_required()
def mark_overdue(task_id):
  user_id = get_jwt_identity()
  current_user = db.users.find_one({"_id": ObjectId(user_id)})

  task = db.tasks.find_one({'_id': ObjectId(task_id)})
  if not task:
      return jsonify({"msg": "Task not found"}), 404

  # If already completed, no action
  if task.get('status') == 'Done':
      return jsonify({"msg": "Task already completed"}), 200

  # If already marked overdue, avoid duplicate notifications
  already_overdue = (task.get('status') == 'Overdue')

  # Mark as Overdue
  db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': 'Overdue'}})

  if not already_overdue:
      # Send email to admins and managers
      managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
      meta = {
          "status": "Overdue",
          "task_id": str(task['_id']),
          "title": task.get('title'),
          "employee_id": task['assigned_to']
      }
      notify_body = (
          f"Task '{task.get('title')}' assigned to Employee ID: {task['assigned_to']} "
          f"was not completed before the deadline."
      )
      for mgr in managers:
          send_email(
              subject="Task Overdue Alert",
              recipient=mgr['email'],
              body=notify_body,
              meta=meta
          )

  return jsonify({"msg": "Overdue processed"}), 200
