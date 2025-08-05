# Copyright (c) 2025, satat tech llp and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PreventiveMaintenanceReport(Document):
    def after_insert(self):
        if not self.csr_no:
            self.db_set("csr_no",self.name)
