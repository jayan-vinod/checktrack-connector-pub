import requests
from checktrack_connector.api import DATA_API_URL, USER_API_URL
import frappe
from frappe import conf
from frappe import _


def get_last_value(url):
    parts = url.rstrip('/').split('/')
    return parts[-1]

def send_notification(doc, docname, prefix, tenantId):
    try:
        current_assign_to = doc.assign_to

        if not current_assign_to:
            return

        # Get the User email linked to the assigned Employee
        assigned_user_email = frappe.db.get_value("Employee", current_assign_to, "work_email")

        # Check if the task is assigned to the current user's linked Employee
        if assigned_user_email == frappe.session.user:
            frappe.logger().info(f"Skipping self-assignment notification for {docname}")
            return

        # Determine if we should send the notification
        send_notification_flag = False

        if doc.flags.in_insert or doc.is_new():
            # New document: send notification if assign_to is set
            send_notification_flag = True
        else:
            # Existing document: send notification if assign_to changed
            previous_doc = doc.get_doc_before_save()
            if previous_doc:
                previous_assign_to = previous_doc.assign_to
                if previous_assign_to != current_assign_to:
                    send_notification_flag = True

        if not send_notification_flag:
            frappe.logger().info(f"No change in assign_to for {docname}, skipping notification.")
            return

        # Get the current user (assigner) details
        current_user = frappe.get_doc("User", frappe.session.user)
        assigner_name = current_user.full_name or current_user.name

        # Extract employee IDs from child table 'assign_to'
        list_of_employee_ids = [{"$oid": doc.assign_to}]

        if not list_of_employee_ids:
            frappe.logger().warn(f"No employees assigned to task {docname}, skipping notification.")
            return

        # Get API URLs
        USER_API_URL = frappe.get_hooks().get("user_api_url")
        DATA_API_URL = frappe.get_hooks().get("data_api_url")

        USER_API_URL = USER_API_URL[0] if isinstance(USER_API_URL, list) and USER_API_URL else USER_API_URL
        DATA_API_URL = DATA_API_URL[0] if isinstance(DATA_API_URL, list) and DATA_API_URL else DATA_API_URL

        # Prepare notification payload
        notification_data = {
            "prefix": prefix,
            "listOfEmployeeIds": list_of_employee_ids,
            "notificationPayload": {
                "title": "Task",
                "body": f"{assigner_name} has assigned the task \"{doc.task_name}\" to you",
                "data": {
                    "route": "/tasks/view",
                    "arguments": {
                        "doctype": "Task",
                        "docname": docname,
                        "isEdit": False,
                        "readOnly": True,
                        "selectedMenu": "summary"
                    }
                }
            },
            "tenantId": tenantId
        }

        # Send notification via API
        url = f"{USER_API_URL}/notification/send"
        access_token = get_app_admin_bearer_auth()
        notification_headers = {
            "Authorization": access_token,
            'Content-Type': 'application/json; charset=UTF-8',
            'No-Auth-Challenge': 'true'
        }

        response = requests.post(url, json=notification_data, headers=notification_headers)
        response.raise_for_status()

        frappe.logger().info(f"Notification sent for task {docname}")

        return response

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Notification sending failed")

def send_status_change_notification(doc, docname, prefix, tenantId):
    try:
        # Check if status has changed
        previous_doc = doc.get_doc_before_save()
        
        # Determine if notification should be sent
        send_notification = False
        
        if previous_doc is None:
            # New document: no status change to notify
            frappe.logger().info(f"New task {docname}, no status change notification.")
            return
        else:
            # Existing document: check if status changed
            previous_status = previous_doc.workflow_status
            current_status = doc.workflow_status
            if previous_status != current_status:
                send_notification = True

        if not send_notification:
            frappe.logger().info(f"Status unchanged for task {docname}, skipping notification.")
            return

        # Get current user (who changed the status)
        current_user = frappe.get_doc("User", frappe.session.user)
        changer_name = current_user.full_name or current_user.name

        # Collect all employees to notify (watchers + assigned person)
        employee_ids_to_notify = set()
        
        # Add watchers from child table
        for row in doc.watchers:
            employee_ids_to_notify.add(row.employee)
        
        # Add assigned person if exists
        if doc.assign_to:
            employee_ids_to_notify.add(doc.assign_to)

        # Get current user's linked employee to exclude from notifications
        current_user_employee = frappe.db.get_value("Employee", {"work_email": frappe.session.user}, "name")
        
        # Remove current user's employee from notification list if present
        if current_user_employee and current_user_employee in employee_ids_to_notify:
            employee_ids_to_notify.remove(current_user_employee)
            frappe.logger().info(f"Excluded current user's employee {current_user_employee} from notifications for {docname}")

        # Convert to required format
        list_of_employee_ids = [{"$oid": emp_id} for emp_id in employee_ids_to_notify]

        if not list_of_employee_ids:
            frappe.logger().warn(f"No valid recipients for task {docname} status change notification, skipping.")
            return

        # Get API URLs
        USER_API_URL = frappe.get_hooks().get("user_api_url")
        if isinstance(USER_API_URL, list) and USER_API_URL:
            USER_API_URL = USER_API_URL[0]

        # Prepare notification payload
        notification_data = {
            "prefix": prefix,
            "listOfEmployeeIds": list_of_employee_ids,
            "notificationPayload": {
                "title": "Task Status Updated",
                "body": f"The status of task \"{doc.task_name}\" has changed from \"{previous_status}\" to \"{current_status}\" by \"{changer_name}\"",
                "data": {
                    "route": "/tasks/view",
                    "arguments": {
                        "doctype": "Task",
                        "docname": docname,
                        "isEdit": False,
                        "readOnly": True,
                        "selectedMenu": "summary"
                    }
                }
            },
            "tenantId": tenantId
        }

        # Send notification
        url = f"{USER_API_URL}/notification/send"
        access_token = get_app_admin_bearer_auth()
        notification_headers = {
            "Authorization": access_token,
            'Content-Type': 'application/json; charset=UTF-8',
            'No-Auth-Challenge': 'true'
        }

        response = requests.post(url, json=notification_data, headers=notification_headers)
        response.raise_for_status()

        frappe.logger().info(f"Status change notification sent for task {docname} to {len(list_of_employee_ids)} recipients")
        return response

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Status change notification failed")

def sync_or_update_task_in_mongo(doc, method):
    if doc.mongo_task_id:
        response = update_task_in_mongo(doc, method)
    else:
        response = sync_task_to_mongo(doc, method)

# NEW HANDLERS FOR SUBMIT/CANCEL EVENTS
def handle_task_submit(doc, method):
    """Handle task submission - sync to mongo and send notifications"""
    try:
        # Update task in mongo when submitted
        if doc.mongo_task_id:
            response = update_task_in_mongo(doc, method)
        else:
            response = sync_task_to_mongo(doc, method)
        
        # Send feedback request if task is completed
        frappe.logger().info(f"Task {doc.name} submitted and synced successfully")
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Failed to handle task submit for {doc.name}")

def handle_task_cancel(doc, method):
    """Handle task cancellation - sync to mongo and send notifications"""
    try:
        # Update task in mongo when cancelled
        if doc.mongo_task_id:
            response = update_task_in_mongo(doc, method)
        else:
            response = sync_task_to_mongo(doc, method)
            
        frappe.logger().info(f"Task {doc.name} cancelled and synced successfully")
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Failed to handle task cancel for {doc.name}")

def send_status_change_notification_for_submit_cancel(doc, docname, prefix, tenantId, status_action):
    """Send notification for submit/cancel actions"""
    try:
        # Get current user (who performed the action)
        current_user = frappe.get_doc("User", frappe.session.user)
        changer_name = current_user.full_name or current_user.name

        current_status = doc.workflow_status
        
        # Collect all employees to notify (watchers + assigned person)
        employee_ids_to_notify = set()
        
        # Add watchers from child table
        for row in doc.watchers:
            employee_ids_to_notify.add(row.employee)
        
        # Add assigned person if exists
        if doc.assign_to:
            employee_ids_to_notify.add(doc.assign_to)

        # Get current user's linked employee to exclude from notifications
        current_user_employee = frappe.db.get_value("Employee", {"work_email": frappe.session.user}, "name")
        
        # Remove current user's employee from notification list if present
        if current_user_employee and current_user_employee in employee_ids_to_notify:
            employee_ids_to_notify.remove(current_user_employee)
            frappe.logger().info(f"Excluded current user's employee {current_user_employee} from {status_action} notifications for {docname}")

        # Convert to required format
        list_of_employee_ids = [{"$oid": emp_id} for emp_id in employee_ids_to_notify]

        if not list_of_employee_ids:
            frappe.logger().warn(f"No valid recipients for task {docname} {status_action} notification, skipping.")
            return

        # Get API URLs
        USER_API_URL = frappe.get_hooks().get("user_api_url")
        if isinstance(USER_API_URL, list) and USER_API_URL:
            USER_API_URL = USER_API_URL[0]

        # Prepare notification payload
        action_text = "completed" if status_action == "submit" else "cancelled"
        notification_data = {
            "prefix": prefix,
            "listOfEmployeeIds": list_of_employee_ids,
            "notificationPayload": {
                "title": f"Task {current_status}",
                "body": f"Task \"{doc.task_name}\" has been {current_status} by {changer_name}",
                "data": {
                    "route": "/tasks/view",
                    "arguments": {
                        "doctype": "Task",
                        "docname": docname,
                        "isEdit": False,
                        "readOnly": True,
                        "selectedMenu": "summary"
                    }
                }
            },
            "tenantId": tenantId
        }

        # Send notification
        url = f"{USER_API_URL}/notification/send"
        access_token = get_app_admin_bearer_auth()
        notification_headers = {
            "Authorization": access_token,
            'Content-Type': 'application/json; charset=UTF-8',
            'No-Auth-Challenge': 'true'
        }

        response = requests.post(url, json=notification_data, headers=notification_headers)
        response.raise_for_status()

        frappe.logger().info(f"Status change notification sent for task {docname} - {action_text} to {len(list_of_employee_ids)} recipients")
        return response

    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Status change notification failed for {status_action}")
      
def sync_or_update_project_in_mongo(doc, method):
    if doc.mongo_project_id:
        response = update_project_in_mongo(doc, method)
    else:
        response = sync_project_to_mongo(doc, method)

def get_app_admin_bearer_auth():

    try:
        USER_API_URL = frappe.get_hooks().get("user_api_url")
        DATA_API_URL = frappe.get_hooks().get("data_api_url")

        if isinstance(USER_API_URL, list) and USER_API_URL:
            USER_API_URL = USER_API_URL[0]
        if isinstance(DATA_API_URL, list) and DATA_API_URL:
            DATA_API_URL = DATA_API_URL[0]

        email = conf.get("checktrack_admin_email")
        password = conf.get("checktrack_admin_password") 
        
        url = f"{USER_API_URL}/login"
        auth_payload = {"email": email, "password": password}
        HEADERS = {"Content-Type": "application/json"}
        auth_response = requests.post(url, headers=HEADERS, json=auth_payload)

        if auth_response.status_code != 200:
            frappe.throw("CheckTrack intergation failed. Invalid email or password.")

        auth_data = auth_response.json()
        frappe.log_error(message=f"Auth response keys: {list(auth_data.keys())}", title="Auth Debug")

        access_token = auth_data.get("accessToken")
        return f"Bearer {access_token}"

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_app_admin_bearer_auth failed")
        frappe.throw("Failed to generate admin token.") 

def sync_task_to_mongo(doc, method):

    USER_API_URL = frappe.get_hooks().get("user_api_url")
    DATA_API_URL = frappe.get_hooks().get("data_api_url")

    if isinstance(USER_API_URL, list) and USER_API_URL:
        USER_API_URL = USER_API_URL[0]
    if isinstance(DATA_API_URL, list) and DATA_API_URL:
        DATA_API_URL = DATA_API_URL[0]

    watchers = []
    assignTo = []

    company_doc = frappe.get_doc("Company", doc.company)
    if doc.assign_to:
        assignToInfo = frappe.get_doc("Employee", doc.assign_to)
        assigned_to_ref = {
            "_id": {
                "$oid": assignToInfo.name
            },
            "_ref": f"{company_doc.prefix}_team_members",
            "_title": f"{assignToInfo.employee_name}"
        }
        assignTo.append(assigned_to_ref)
    for row in doc.watchers:
        watcher_ref = {
            "_id": {
                "$oid": row.employee
            },
            "_ref": f"{company_doc.prefix}_team_members",
            "_title": f"{row.employee_name}"
        }
        watchers.append(watcher_ref)

    payload = {
        "name": doc.task_name,
        "assignedTo": assignTo,
        "watchers": watchers,
        "description": doc.description,
        "frappe": {
            "_id": doc.name,
            "_ref": doc.doctype,
            "_title": doc.task_name
        },
        "tenant": {
            "_id": {
                "$oid" : company_doc.tenant_id
            },
            "_ref": "tenants",
            "_title": f"{company_doc.prefix}"
        }
    }
    if doc.project:
        try:
            project_doc = frappe.get_doc("Project", doc.project)
            
            payload["project"] = {
                "_id": {
                    "$oid": project_doc.mongo_project_id
                },
                "_ref": f"{company_doc.prefix}_projects",
                "_title": project_doc.project_name
            }
        except frappe.DoesNotExistError:
            frappe.log_error(f"Project '{doc.project}' not found", "Sync Task Error")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Failed to sync project '{doc.project}'")

    if doc.workflow_status:
        payload["status"] = doc.workflow_status
    else:
        payload["status"] = ""

    try:
        prefix = company_doc.prefix
        url = f"{DATA_API_URL}/{prefix}_tasks"
        access_token = get_app_admin_bearer_auth()
        task_headers = {
            "Authorization": access_token,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=task_headers)
        response.raise_for_status()

        mongo_id = get_last_value(response.headers['Location'])
        if mongo_id:
            doc.db_set("mongo_task_id", mongo_id, update_modified=False)
            # doc.reload()
            frappe.logger().info(f"[SYNC SUCCESS] Task '{doc.name}' synced to MongoDB with ID: {mongo_id}")
        else:
            frappe.logger().error(f"[SYNC FAILED] Task '{doc.name}' created in MongoDB but no ID returned.")

        # Send assignment notification
        notification_res = send_notification(doc,doc.name,prefix,company_doc.tenant_id)
        
        # For submit/cancel events, send appropriate status notification
        if method in ['on_submit', 'on_cancel']:
            status_action = 'submit' if method == 'on_submit' else 'cancel'
            send_status_change_notification_for_submit_cancel(doc, doc.name, prefix, company_doc.tenant_id, status_action)
        
        return response

    except Exception as e:
        frappe.logger().error(f"[SYNC ERROR] Task '{doc.name}' failed to sync to MongoDB.")
        frappe.throw(e)

def update_task_in_mongo(doc, method):
    
    USER_API_URL = frappe.get_hooks().get("user_api_url")
    DATA_API_URL = frappe.get_hooks().get("data_api_url")

    if isinstance(USER_API_URL, list) and USER_API_URL:
        USER_API_URL = USER_API_URL[0]
    if isinstance(DATA_API_URL, list) and DATA_API_URL:
        DATA_API_URL = DATA_API_URL[0]

    watchers = []
    assignTo = []

    company_doc = frappe.get_doc("Company", doc.company)
    if doc.assign_to:
        assignToInfo = frappe.get_doc("Employee", doc.assign_to)
        assigned_to_ref = {
            "_id": {
                "$oid": assignToInfo.name
            },
            "_ref": f"{company_doc.prefix}_team_members",
            "_title": f"{assignToInfo.employee_name}"
        }
        assignTo.append(assigned_to_ref)
    for row in doc.watchers:
        watcher_ref = {
            "_id": {
                "$oid": row.employee
            },
            "_ref": f"{company_doc.prefix}_team_members",
            "_title": f"{row.employee_name}"
        }
        watchers.append(watcher_ref)

    payload = {
        "name": doc.task_name,
        "assignedTo": assignTo,
        "watchers": watchers,
        "description": doc.description,
        "frappe": {
            "_id": doc.name,
            "_ref": doc.doctype,
            "_title": doc.task_name
        },
        "tenant": {
            "_id": {
                "$oid" : company_doc.tenant_id
            },
            "_ref": "tenants",
            "_title": f"{company_doc.prefix}"
        }
    }
    if doc.project:
        try:
            project_doc = frappe.get_doc("Project", doc.project)
            
            payload["project"] = {
                "_id": {
                    "$oid": project_doc.mongo_project_id
                },
                "_ref": f"{company_doc.prefix}_projects",
                "_title": project_doc.project_name
            }
        except frappe.DoesNotExistError:
            frappe.log_error(f"Project '{doc.project}' not found", "Sync Task Error")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Failed to sync project '{doc.project}'")

    if doc.workflow_status:
        payload["status"] = doc.workflow_status
    else:
        payload["status"] = ""

    try:
        prefix = company_doc.prefix
        url = f"{DATA_API_URL}/{prefix}_tasks/{doc.mongo_task_id}"
        access_token = get_app_admin_bearer_auth()
        task_headers = {
            "Authorization": access_token,
            "Content-Type": "application/json"
        }
        response = requests.patch(url, json=payload, headers=task_headers)
        response.raise_for_status()

        # Send assignment notification
        notification_res = send_notification(doc,doc.name,prefix,company_doc.tenant_id)
        
        # Handle different methods appropriately
        if method == 'on_update':
            # Regular update - send status change notification
            send_status_change_notification(doc,doc.name,prefix,company_doc.tenant_id)
        elif method in ['on_submit', 'on_cancel']:
            # Submit/Cancel - send appropriate notification
            status_action = 'submit' if method == 'on_submit' else 'cancel'
            send_status_change_notification_for_submit_cancel(doc, doc.name, prefix, company_doc.tenant_id, status_action)

        return response

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Mongo Update Failed")

def sync_project_to_mongo(doc, method):

    USER_API_URL = frappe.get_hooks().get("user_api_url")
    DATA_API_URL = frappe.get_hooks().get("data_api_url")

    if isinstance(USER_API_URL, list) and USER_API_URL:
        USER_API_URL = USER_API_URL[0]
    if isinstance(DATA_API_URL, list) and DATA_API_URL:
        DATA_API_URL = DATA_API_URL[0]
    frappe.log_error("Triggered sync_project_to_mongo", f"PROJECT NAME: {doc.name}")
    company_doc = frappe.get_doc("Company", doc.company)
    payload = {
        "name": doc.project_name,
        "assignedTo": [],
        "description": doc.description,
        "status": doc.status,
        "frappe": {
            "_id": doc.name,
            "_ref": doc.doctype,
            "_title": doc.project_name
        },
        "tenant": {
            "_id": {
                "$oid" : company_doc.tenant_id
            },
            "_ref": "tenants",
            "_title": f"{company_doc.prefix}"
        }
    }

    try:
        prefix = company_doc.prefix
        url = f"{DATA_API_URL}/{prefix}_projects"
        access_token = get_app_admin_bearer_auth()
        project_headers = {
            "Authorization": access_token,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=project_headers)
        response.raise_for_status()

        mongo_id = get_last_value(response.headers['Location'])
        if mongo_id:
            doc.mongo_project_id = mongo_id
            doc.save(ignore_permissions=True)
            frappe.logger().info(f"[SYNC SUCCESS] Project '{doc.name}' synced to MongoDB with ID: {mongo_id}")
        else:
            frappe.logger().error(f"[SYNC FAILED] Project '{doc.name}' created in MongoDB but no ID returned.")

        return response

    except Exception as e:
        frappe.logger().error(f"[SYNC ERROR] Project '{doc.name}' failed to sync to MongoDB.")
        frappe.throw(e)

def update_project_in_mongo(doc, method):
    
    USER_API_URL = frappe.get_hooks().get("user_api_url")
    DATA_API_URL = frappe.get_hooks().get("data_api_url")

    if isinstance(USER_API_URL, list) and USER_API_URL:
        USER_API_URL = USER_API_URL[0]
    if isinstance(DATA_API_URL, list) and DATA_API_URL:
        DATA_API_URL = DATA_API_URL[0]

    company_doc = frappe.get_doc("Company", doc.company)

    payload = {
        "name": doc.project_name,
        "assignedTo": [],
        "description": doc.description,
        "status": doc.status,
        "frappe": {
            "_id": doc.name,
            "_ref": doc.doctype,
            "_title": doc.project_name
        },
        "tenant": {
            "_id": {
                "$oid" : company_doc.tenant_id
            },
            "_ref": "tenants",
            "_title": f"{company_doc.prefix}"
        }
    }

    try:
        prefix = company_doc.prefix
        url = f"{DATA_API_URL}/{prefix}_projects/{doc.mongo_project_id}"
        access_token = get_app_admin_bearer_auth()
        project_headers = {
            "Authorization": access_token,
            "Content-Type": "application/json"
        }
        response = requests.patch(url, json=payload, headers=project_headers)
        response.raise_for_status()
        return response

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Mongo Update Failed")