import io
import csv
import frappe
import urllib.parse
import json
import requests
from frappe.utils.file_manager import save_file
from frappe.core.doctype.data_import.data_import import start_import, get_import_status

USER_API_URL = frappe.get_hooks().get("user_api_url")
DATA_API_URL = frappe.get_hooks().get("data_api_url")
if isinstance(USER_API_URL, list) and USER_API_URL:
    USER_API_URL = USER_API_URL[0]
if isinstance(DATA_API_URL, list) and DATA_API_URL:
    DATA_API_URL = DATA_API_URL[0]

def assign_all_roles_to_user(user_email):
    all_roles = [
        "Academics User", "Accounts Manager", "Accounts User", "Agriculture Manager", 
        "Agriculture User", "Analytics", "Auditor", "Blogger", "CT Owner", "Customer", 
        "Dashboard Manager", "Delivery Manager", "Delivery User", "Fleet Manager", 
        "Fulfillment User", "HR Manager", "HR User", "Inbox User", "Item Manager", 
        "Knowledge Base Contributor", "Knowledge Base Editor", "Maintenance Manager",
        "Maintenance User", "Manufacturing Manager", "Manufacturing User","Newsletter Manager",
        "Prepared Report User", "Projects Manager", "Projects User", "Purchase Manager",
        "Purchase Master Manager", "Purchase User", "Quality Manager", "Report Manager",
        "Sales Manager", "Sales Master Manager", "Sales User", "Script Manager", 
        "Stock Manager", "Stock User", "Supplier", "Support Team", "System Manager", 
        "Translator", "Website Manager", "Workspace Manager"
    ]
    
    try:
        user_doc = frappe.get_doc("User", user_email)
        user_doc.roles = []
        
        # Add all roles
        for role in all_roles:
            # Check if role exists in the system
            if frappe.db.exists("Role", role):
                user_doc.append("roles", {
                    "role": role
                })
            else:
                frappe.log_error(f"Role {role} does not exist in the system", "Role Assignment Error")
        
        user_doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.msgprint(f"Successfully assigned {len(all_roles)} roles to user {user_email}")
        
    except Exception as e:
        frappe.log_error(f"Error assigning roles to user {user_email}: {str(e)}", "User Role Assignment Error")
        frappe.throw(f"Failed to assign roles: {str(e)}")

@frappe.whitelist()
def automated_import_users(tenant_id=None, integration_email=None):
    try:
        if not tenant_id:
            return {"status": "error", "message": "tenant_id is required"}

        # Step 1: Fetch team members based on tenant_id
        team_members = frappe.get_all("Employee", filters={"company": tenant_id}, fields=["work_email", "first_name", "last_name"])

        if not team_members:
            return {"status": "error", "message": "No team members found for the provided tenant_id"}

        # Step 2: Prepare CSV data - Skip the integration email
        data = [
            ["email", "first_name", "last_name", "user_type", "roles.role", "enabled", "send_welcome_email"]
        ]
        
        skipped_count = 0
        for tm in team_members:
            # Skip if this email matches the integration email
            if integration_email and tm.work_email.lower().strip() == integration_email.lower().strip():
                skipped_count += 1
                continue
                
            # Validate email before adding to import data
            if not tm.work_email or not tm.work_email.strip():
                continue
                
            data.append([
                tm.work_email.strip(),
                tm.first_name or "",
                tm.last_name or "",
                "System User",
                "System Manager",
                1,
                0
            ])

        # Check if we have any data to import (excluding header)
        if len(data) <= 1:
            return {
                "status": "warning",
                "message": f"No users to import after skipping integration email(s). Skipped {skipped_count} email(s)."
            }
        


        # Step 3: Convert to CSV in-memory
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        for row in data:
            writer.writerow(row)
        csv_buffer.seek(0)

        # Step 4: Save file in Frappe's file system
        file_doc = save_file(
            fname="user_import.csv",
            content=csv_buffer.getvalue(),
            dt=None,
            dn=None,
            folder="Home",
            decode=False,
            is_private=0
        )
        frappe.db.commit()

        # Step 5: Create Data Import record
        import_doc = frappe.get_doc({
            "doctype": "Data Import",
            "reference_doctype": "User",
            "import_type": "Insert New Records",
            "import_file": file_doc.file_url,
            "submit_after_import": 0,
            "overwrite": 0,
            "ignore_encoding_errors": 1
        })
        import_doc.save()
        frappe.db.commit()

        # Step 6: Start import
        start_import(import_doc.name)

        # Step 7: Check import status
        status_info = get_import_status(import_doc.name)
        


        if status_info.get("status") == "Success":

            # Filter out the integration email from the list of users to process
            new_user_emails = [tm["work_email"] for tm in team_members if not (integration_email and tm["work_email"].lower().strip() == integration_email.lower().strip())]
            created_permission_ids = []
            failed_permissions = []

            # Step 8: Assign all roles to each newly created user
            for email in new_user_emails:
                if frappe.db.exists("User", email):
                    try:
                        assign_all_roles_to_user(email)
                        if not frappe.db.exists("User Permission", {
                            "user": email,
                            "allow": "Company",
                            "for_value": tenant_id
                        }):
                            doc = frappe.get_doc({
                                "doctype": "User Permission",
                                "user": email,
                                "allow": "Company",
                                "for_value": tenant_id,
                                "apply_to_all_doctypes": 1
                })
                            doc.insert(ignore_permissions=True)
                            created_permission_ids.append(doc.name)
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), f"User Permission Error for {email}")
                        failed_permissions.append(email)
                        break


            if failed_permissions:
                for perm_id in created_permission_ids:
                    try:
                        frappe.delete_doc("User Permission", perm_id, ignore_permissions=True)
                    except Exception as del_err:
                        pass
    
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": "User permission creation failed. Rolled back all permissions.",
                    "failed_user_permissions": failed_permissions
                }
            
            frappe.db.commit()

            success_message = f"Imported data into User from file {file_doc.file_url}"
            if skipped_count > 0:
                success_message += f" (Skipped {skipped_count} integration email(s))"
            
            return {
                "status": "success",
                "message": success_message,
                "skipped_count": skipped_count
            }
        else:
            error_message = f"Import failed with status: {status_info.get('status')}"
            if status_info.get("messages"):
                error_message += f" - Messages: {status_info.get('messages')}"
            
            return {
                "status": "error",
                "message": error_message,
                "details": status_info.get("messages")
            }

    except Exception as e:
        return {
            "status": "error",
            "message": "An error occurred during user import",
            "error": str(e)
        }
    
@frappe.whitelist()
def import_project(tenant_id, tenant_prefix, access_token,company_name):
    try:
        # Handle tenant_id if it's a dict (MongoDB ObjectId format)
        if isinstance(tenant_id, dict) and '$oid' in tenant_id:
            tenant_id = tenant_id['$oid']
        else:
            tenant_id = str(tenant_id)
            
        limit = 1000
        filter_query = {"tenant._id": {"$oid": tenant_id}}
        url = f"{DATA_API_URL}/{tenant_prefix}_projects?filter={urllib.parse.quote(json.dumps(filter_query))}&pagesize={limit}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "No-Auth-Challenge": "true",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            projects = response.json()
            if not isinstance(projects, list):
                return {"status": "error", "message": "No project found for the provided tenant_id"}
            data = [
                ["project_name", "description","status","company","mongo_project_id"]
            ]
            for project in projects:
                data.append([
                    project.get("name"),
                    project.get("description"),
                    project.get("status").capitalize(),
                    company_name,
                    project.get("_id", {}).get("$oid")
                ])
            
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            for row in data:
                writer.writerow(row)
            csv_buffer.seek(0)

            file_doc = save_file(
                fname="project_import.csv",
                content=csv_buffer.getvalue(),
                dt=None,
                dn=None,
                folder="Home",
                decode=False,
                is_private=0
            )
            frappe.db.commit()

            # Step 5: Create Data Import record
            import_doc = frappe.get_doc({
                "doctype": "Data Import",
                "reference_doctype": "Project",
                "import_type": "Insert New Records",
                "import_file": file_doc.file_url,
                "submit_after_import": 0,
                "overwrite": 0,
                "ignore_encoding_errors": 1
            })
            import_doc.save()
            frappe.db.commit()

            start_import(import_doc.name)

            status_info = get_import_status(import_doc.name)

            if status_info.get("status") in ["Success", "Partial Success"]:

                created_projects = frappe.get_all("Project",fields=["name", "mongo_project_id"])
                project_id_map = {
                    proj["mongo_project_id"]: proj["name"]
                    for proj in created_projects if proj.get("mongo_project_id")
                }
                task_list  = get_task(tenant_id=tenant_id, tenant_prefix=tenant_prefix, access_token=access_token)
                
                task_data = [
                    ["task_name", "description","assign_to","project","workflow_status","company","mongo_task_id"]
                ]

                for task in task_list:
                    project_data = task.get("project")
                    mongo_proj_id = None

                    if isinstance(project_data, dict):
                        mongo_proj_id = project_data.get("_id", {}).get("$oid")

                    frappe_project_name = project_id_map.get(mongo_proj_id, None)

                    assigned_to = (
                        task.get("assignedTo") and task.get("assignedTo", [{}])[0].get("_id", {}).get("$oid")
                    ) or None

                    task_data.append([
                        task.get("name"),
                        task.get("description", ""),
                        assigned_to,
                        frappe_project_name,
                        "Pending" if task.get("status") in ["active", "inactive"] else task.get("status", "Pending"),
                        company_name,
                        task.get("_id", {}).get("$oid")
                    ])

                csv_buffer_task = io.StringIO()
                writer_task = csv.writer(csv_buffer_task)
                for row in task_data:
                    writer_task.writerow(row)
                csv_buffer_task.seek(0)

                file_doc_task = save_file(
                    fname="task_import.csv",
                    content=csv_buffer_task.getvalue(),
                    dt=None,
                    dn=None,
                    folder="Home",
                    decode=False,
                    is_private=0
                )
                frappe.db.commit()

                # Step 5: Create Data Import record
                import_doc_task = frappe.get_doc({
                    "doctype": "Data Import",
                    "reference_doctype": "Task",
                    "import_type": "Insert New Records",
                    "import_file": file_doc_task.file_url,
                    "submit_after_import": 0,
                    "overwrite": 0,
                    "ignore_encoding_errors": 1
                })
                import_doc_task.save()
                frappe.db.commit()

                start_import(import_doc_task.name)

                status_info_task = get_import_status(import_doc_task.name)

                if status_info_task.get("status") in ["Success", "Partial Success"]:
                    return {
                        "status": "success",
                        "message": f"Imported data of task and project done"
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Task Import failed project",
                        "details": status_info_task.get("messages")
                    }
            else:
                return {
                    "status": "error",
                    "message": "Project and Task Import failed project",
                    "details": status_info.get("messages")
                }


        else:
            return {
                "status": "error",
                "message": "Something went wrong!"
            }
        
    except Exception as e:
        return {
            "status": "error",
            "message": "An error occurred during project import",
            "error": str(e)
        }
    

def get_task(tenant_id, tenant_prefix, access_token):
    try:
        # Handle tenant_id if it's a dict (MongoDB ObjectId format)
        if isinstance(tenant_id, dict) and '$oid' in tenant_id:
            tenant_id = tenant_id['$oid']
        else:
            tenant_id = str(tenant_id)
            
        all_tasks = []
        headers = {
            "Authorization": f"Bearer {access_token}",
            "No-Auth-Challenge": "true",
            "Content-Type": "application/json"
        }

        filter_query = {"tenant._id": {"$oid": tenant_id}}
        base_url = f"{DATA_API_URL}/{tenant_prefix}_tasks"

        pagesize = 100
        page = 1

        while True:
            url = (f"{base_url}?filter={urllib.parse.quote(json.dumps(filter_query))}&pagesize={pagesize}&page={page}")
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                batch = response.json()
                if not batch:
                    break
                all_tasks.extend(batch)
                page += 1
            else:
                break

        return all_tasks

    except Exception as e:
        return {
            "status": "error",
            "message": "An error occurred during tasks fetch",
            "error": str(e)
        }
    