# Copyright (c) 2025, satat tech llp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf


class ServiceReport(Document):
    def after_insert(self):
        if not self.csr_no:
            self.db_set("csr_no",self.name)
            
        if self.email:
            try:
                # Render HTML with specific letterhead and print format
                html = frappe.get_print(
                    self.doctype,
                    self.name,
                    print_format="Service Report",
                    doc=self,
                    letterhead="Neer Instruments"
                )

                # Convert to PDF
                pdf_content = get_pdf(html)

                # Send Email
                frappe.sendmail(
                    recipients=[self.email],
                    subject=f"Service Report- {self.name}",
                    message="Dear Customer,<br><br>Please find attached the service report.<br><br>Regards,<br>Neer Instruments",
                    attachments=[{
                        "fname": f"{self.name}.pdf",
                        "fcontent": pdf_content
                    }]
                )

            except Exception:
                frappe.log_error(frappe.get_traceback(), "Service Report Email Error")