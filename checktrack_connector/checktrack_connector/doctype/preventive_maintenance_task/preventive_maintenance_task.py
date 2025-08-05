# Copyright (c) 2025, Satat Tech LLP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class PreventiveMaintenanceTask(Document):
    pass
    # def before_save(self):
    #     # Log when before_save is triggered
    #     frappe.log_error(f"PreventiveMaintenanceTask Updated: {self.name}, Status: {self.status}", "PreventiveMaintenanceTask Log")

    #     # Fetch all Task records linked to this PreventiveMaintenanceTask
    #     tasks = frappe.get_all(
    #         "Task",
    #         filters={
    #             "task_type_doc": self.name,  # The task should be linked to this PreventiveMaintenanceTask
    #             "type": self.doctype         # Ensure the task's type matches this DocType
    #         },
    #         fields=["name", "status"]
    #     )

    #     # If no tasks are found, log it for debugging
    #     if not tasks:
    #         frappe.log_error(f"No linked tasks found for PreventiveMaintenanceTask: {self.name}", "PreventiveMaintenanceTask Log")

    #     # Update status of each Task record
    #     for t in tasks:
    #         frappe.log_error(f"Updating Task: {t.name} with new status: {self.status}", "PreventiveMaintenanceTask Log")
    #         frappe.db.set_value("Task", t.name, "status", self.status)
