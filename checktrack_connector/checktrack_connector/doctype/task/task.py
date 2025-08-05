# For license information, please see license.txt

import frappe
from frappe.utils.nestedset import NestedSet

class Task(NestedSet):
    def before_save(self):
        # Store the status transition for use in on_update
        if not hasattr(self, '_original_status'):
            if self.is_new():
                self._original_status = None
            else:
                old_doc = frappe.get_doc('Task', self.name)
                self._original_status = old_doc.workflow_status.lower() if old_doc.workflow_status else None

        if self.watchers:
            ids = [row.employee for row in self.watchers if row.employee]
            self.watchers_id = "," + ",".join(ids) + "," if ids else ""
        else:
            self.watchers_id = ""

    def on_update(self):
        set_dynamic_fields(self)
        # First handle linked document status update
        self.update_linked_doc_status()

        self.update_linked_doc_task_field()

        # Then handle submission logic when status changes to Completed/Cancelled
        try:
            current_status = self.workflow_status.lower() if self.workflow_status else None
            is_status_change = not hasattr(self, '_original_status') or self._original_status != current_status
            task_type_name = self.type or "Task"
            submittable_statuses = []
            try:
                task_type_doc = frappe.get_doc("Task Type", task_type_name)
                submittable_statuses = [
                    row.workflow_status.lower()
                    for row in task_type_doc.status_flow
                    if row.end_state == 1
                ]
            except Exception as e:
                frappe.log_error(
                    title="Dynamic End State Fallback Error",
                    message=f"Failed to fetch Task Type '{task_type_name}' for Task '{self.name}':\n{e}"
                )

            # Check status in a case-insensitive way
            if is_status_change and current_status in submittable_statuses:
                self.try_submit_self()
                self.try_submit_linked_doc()
        except Exception:
            frappe.log_error(
                title="Task Submission Error",
                message=f"Failed to submit Task {self.name} or linked doc:\n{frappe.get_traceback()}"
            )

    def update_linked_doc_status(self):
        if not (self.type and self.task_type_doc):
            return
        try:
            if frappe.db.exists(self.type, self.task_type_doc):
                doc = frappe.get_doc(self.type, self.task_type_doc)
                doc.workflow_status = self.workflow_status
                doc.save()
                frappe.log_error(
                    title="Linked Document Status Sync",
                    message=f"Updated workflow_status of linked doc '{self.type}' ({self.task_type_doc}) to '{self.workflow_status}' from Task '{self.name}'."
                )
            else:
                frappe.log_error(
                    title="Linked Document Missing",
                    message=f"Linked document '{self.type}' ({self.task_type_doc}) not found for Task '{self.name}'."
                )
        except Exception:
            frappe.log_error(
                title="Linked Document Sync Error",
                message=f"Failed to update status of linked doc '{self.type}' ({self.task_type_doc}) from Task '{self.name}':\n{frappe.get_traceback()}"
            )

    def try_submit_self(self):
        try:
            self.reload()  # Make sure we have the latest version just change
            if self.docstatus == 0:
                if hasattr(self, 'validate_for_submit'):
                    self.validate_for_submit()
                self.submit()
                frappe.log_error(
                    title="Task Self Submitted",
                    message=f"Task '{self.name}' submitted successfully (workflow_status: {self.workflow_status})."
                )
        except Exception:
            raise  # Error logged by caller

    def try_submit_linked_doc(self):
        if not (self.type and self.task_type_doc):
            return
        if not frappe.db.exists(self.type, self.task_type_doc):
            return
        try:
            doc = frappe.get_doc(self.type, self.task_type_doc)
            if doc.docstatus == 0:
                doc.submit()
                frappe.log_error(
                    title="Linked Document Submitted",
                    message=f"Linked doc '{self.type}' ({self.task_type_doc}) submitted from Task '{self.name}'."
                )
        except Exception:
            raise  # Error logged by caller

    def update_linked_doc_task_field(self):
        """Update 'task' field in the dynamically linked document with the Task's name (ID)"""
        if not (self.type and self.task_type_doc):
            return
        try:
            if frappe.db.exists(self.type, self.task_type_doc):
                linked_doc = frappe.get_doc(self.type, self.task_type_doc)
                if hasattr(linked_doc, "task"):
                    linked_doc.task = self.name
                    # Try multiple permission bypass methods
                    linked_doc.flags.ignore_permissions = True
                    linked_doc.flags.ignore_validate = True
                    linked_doc.save(ignore_permissions=True)
                    frappe.db.commit()  # Ensure changes are committed
                    frappe.log_error(
                        title="Linked Document Task Field Update",
                        message=f"Set 'task' field of '{self.type}' ({self.task_type_doc}) to Task ID '{self.name}'"
                    )
        except Exception as e:
            frappe.log_error(
                title="Linked Doc Task Field Update Error",
                message=f"Failed to update 'task' field of linked doc '{self.type}' ({self.task_type_doc}) from Task '{self.name}':\n{str(e)}\n{frappe.get_traceback()}"
            )
            
def set_dynamic_fields(doc):
    # Find the field mapping document for the Task doctype
    task_type = doc.type or "Task"
    mapping_doc = frappe.get_doc("Task Type", task_type)
    if not mapping_doc:
        return

    for mapping in mapping_doc.field_mapping:
        try:
            value = doc
            prev_doc = doc
            prev_field = None

            for part in mapping.source_path.split("."):
                if not value:
                    value = ""  # If any intermediate object is None, break and assign ""
                    break

                # If value is a string, try to resolve as linked document
                if isinstance(value, str) and prev_doc and prev_field:
                    value = resolve_linked_doc(prev_doc, prev_field, value)

                prev_doc = value
                prev_field = part

                value = getattr(value, part, "") if hasattr(value, part) else ""

            # Default to empty string if None
            final_value = value if value else ""
            final_label = mapping.label_text or ""

            # Set both in object and DB
            setattr(doc, mapping.target_field, final_value)
            setattr(doc, mapping.label_field, final_label)

            doc.db_set(mapping.target_field, final_value)
            doc.db_set(mapping.label_field, final_label)

        except Exception as e:
            frappe.log_error(f"Failed to resolve path: {mapping.source_path}\nError: {e}", "Task Mapping Error")
            doc.db_set(mapping.target_field, "")
            doc.db_set(mapping.label_field, mapping.label_text or "")

    # Handle status-based color assignment
    try:
        current_status = doc.workflow_status
        status_color = next(
            (row.color for row in mapping_doc.status_flow if row.workflow_status == current_status), None
        )

        if status_color:
            doc.color = status_color
            doc.db_set("color", status_color)

    except Exception as e:
        frappe.log_error(f"Failed to assign color for status: {doc.status}\nError: {e}", "Status Color Mapping Error")
        doc.db_set("color", "")

def resolve_linked_doc(parent_doc, fieldname, value):
    """Get linked DocType from fieldname of parent_doc and fetch the document by value."""
    try:
        if not hasattr(parent_doc, "doctype") or not value:
            return value

        meta = frappe.get_meta(parent_doc.doctype)
        field = next((f for f in meta.fields if f.fieldname == fieldname), None)

        if field and field.fieldtype == "Link":
            return frappe.get_doc(field.options, value)
        elif field and field.fieldtype == "Dynamic Link":
            linked_doctype = getattr(parent_doc, field.options, None)
            return frappe.get_doc(linked_doctype, value) if linked_doctype else value

    except Exception as e:
        frappe.log_error(f"Failed to resolve linked doc for field: {fieldname}\nError: {e}", "Link Resolver Error")
        return value

    return value


# def get_permission_query_conditions(user):
# 	if not user:
# 		user = frappe.session.user

# 	if user == "Administrator" or has_unrestricted_role(user):
# 		return ""

# 	user_email = frappe.db.get_value("User", user, "email")
# 	employee = frappe.db.get_value("Employee", {"work_email": user}, "name")

# 	conditions = []

# 	# Condition for assign_to field
# 	if employee:
# 		conditions.append(f"`tabTask`.`assign_to` = '{employee}'")

# 	# Condition for watchers
# 	if user_email:
# 		watcher_condition = f"""exists (
# 			select 1 from `tabWatchers Table` watcher
# 			where watcher.parent = `tabTask`.name
# 			and watcher.employee_email = '{user_email}'
# 		)"""
# 		conditions.append(watcher_condition)

# 	# Combine both conditions with OR if both exist
# 	if conditions:
# 		return "(" + " or ".join(conditions) + ")"
# 	else:
# 		return "1=0"  # Deny access if no match found

# def has_permission(doc, user=None):
# 	if not user:
# 		user = frappe.session.user

# 	if user == "Administrator" or has_unrestricted_role(user):
# 		return True

# 	user_email = frappe.db.get_value("User", user, "email")
# 	employee = frappe.db.get_value("Employee", {"work_email": user}, "name")

# 	# Check assign_to field
# 	if employee and doc.assign_to == employee:
# 		return True

# 	# Check watchers table
# 	watchers = doc.get("watchers", [])
# 	for watcher in watchers:
# 		if watcher.employee_email == user_email:
# 			return True

# 	return False

# def has_unrestricted_role(user):
#     """Check if the user has any role that grants unrestricted access to all tasks"""

#     unrestricted_roles = ["System Manager","Projects User"]

#     user_roles = frappe.get_roles(user)

#     for role in unrestricted_roles:
#         if role in user_roles:
#             return True

#     return False
