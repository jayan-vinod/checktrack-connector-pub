import frappe
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf

class CalibrationReport(Document):
    def before_save(self):
        all_within_range = True

        for row in self.parameters or []:
            try:
                span = float(row.span or 0)
                offline = float(row.offline or 0)
                if span != 0:
                    variation = round(((offline - span) / span) * 100, 2)
                    row.variation = variation
                    if abs(variation) > 5:
                        all_within_range = False
                else:
                    row.variation = 0
            except:
                row.variation = 0
                all_within_range = False

        self.result = "The calibration test pass." if all_within_range else "The calibration test failed."
