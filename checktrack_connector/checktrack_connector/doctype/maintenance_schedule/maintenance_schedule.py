# Copyright (c) 2025, satat tech llp and contributors
# For license information, please see license.txt


import frappe
from frappe import _, throw
from frappe.utils import add_days, cint, cstr, date_diff, formatdate, getdate

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.utilities.transaction_base import TransactionBase, delete_events


class MaintenanceSchedule(TransactionBase):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext.maintenance.doctype.maintenance_schedule_detail.maintenance_schedule_detail import (
			MaintenanceScheduleDetail,
		)

		address_display: DF.TextEditor | None
		amended_from: DF.Link | None
		company: DF.Link
		# Individual fields instead of items table
		item_code: DF.Link | None
		item_name: DF.Data | None
		serial_no: DF.Data | None
		start_date: DF.Date | None
		end_date: DF.Date | None
		periodicity: DF.Select | None
		no_of_visits: DF.Int | None
		sales_person: DF.Link | None
		employee: DF.Data | None
		customer: DF.Link | None
		customer_name: DF.Data | None
		customer_email_id: DF.Data | None
		naming_series: DF.Literal["MAT-MSH-.YYYY.-"]
		schedules: DF.Table[MaintenanceScheduleDetail]
		status: DF.Literal["", "Draft", "Submitted", "Cancelled"]
		territory: DF.Link | None
		transaction_date: DF.Date
	# end: auto-generated types

	@frappe.whitelist()
	def generate_schedule(self):
		if self.docstatus != 0:
			return
		self.set("schedules", [])
		
		# Validate that we have the required individual fields
		self.validate_maintenance_detail()
		
		s_list = self.create_schedule_list(self.start_date, self.end_date, self.no_of_visits, self.sales_person)
		
		for i in range(self.no_of_visits):
			child = self.append("schedules")
			child.serial_no = self.serial_no
			child.item_code = self.item_code
			child.item_name = self.item_name
			child.scheduled_date = s_list[i].strftime("%Y-%m-%d")
			child.idx = i + 1
			child.sales_person = self.sales_person
			child.employee = self.employee
			child.customer = self.customer
			child.customer_name = self.customer_name
			child.customer_email_id = self.customer_email_id
			child.completion_status = "Pending"

	@frappe.whitelist()
	def validate_end_date_visits(self):
		days_in_period = {"Weekly": 7, "Monthly": 30, "Quarterly": 91, "Half Yearly": 182, "Yearly": 365}
		
		if self.periodicity and self.periodicity != "Random" and self.start_date:
			if not self.end_date:
				if self.no_of_visits:
					self.end_date = add_days(
						self.start_date, self.no_of_visits * days_in_period[self.periodicity]
					)
				else:
					self.end_date = add_days(self.start_date, days_in_period[self.periodicity])

			diff = date_diff(self.end_date, self.start_date) + 1
			no_of_visits = cint(diff / days_in_period[self.periodicity])

			if not self.no_of_visits or self.no_of_visits == 0:
				self.end_date = add_days(self.start_date, days_in_period[self.periodicity])
				diff = date_diff(self.end_date, self.start_date) + 1
				self.no_of_visits = cint(diff / days_in_period[self.periodicity])

			elif self.no_of_visits > no_of_visits:
				self.end_date = add_days(
					self.start_date, self.no_of_visits * days_in_period[self.periodicity]
				)

			elif self.no_of_visits < no_of_visits:
				self.end_date = add_days(
					self.start_date, self.no_of_visits * days_in_period[self.periodicity]
				)

	def on_submit(self):
		if not self.get("schedules"):
			throw(_("Please click on 'Generate Schedule' to get schedule"))
		self.validate_schedule()

		# # Update Customer AMC
		# if self.customer and self.serial_no:
		# 	customer_doc = frappe.get_doc("Customer", self.customer)
		# 	for customer_item in customer_doc.customer_items:
		# 		if customer_item.serial_no == self.serial_no:
		# 			customer_item.amc = self.name
		# 			customer_item.amc_expiry_date = self.end_date
		# 			break
		# 	customer_doc.save()
		# 	frappe.msgprint(f"Updated Customer AMC for {self.customer}")

		# Update Customer Items AMC
		if self.serial_no:
			# Find Customer Items by serial_no
			customer_items = frappe.get_all("Customer Items", filters={"serial_no": self.serial_no}, fields=["name"])
			if not customer_items:
				frappe.msgprint(f"No Customer Items found with Serial No: {self.serial_no}", raise_exception=True)
			else:
				# Get the first matching Customer Items
				customer_items_name = customer_items[0]["name"]
				customer_items = frappe.get_doc("Customer Items", customer_items_name)
				customer_items.amc = self.name
				customer_items.amc_expiry_date = self.end_date
				customer_items.save()
				frappe.msgprint(f"Updated AMC and AMC expiry for {customer_items.serial_no}")

		for entry in self.schedules:
			# Create a new Preventive Maintenance Task record
			pm_task = frappe.new_doc("Preventive Maintenance Task")
			pm_task.customer = entry.customer
			pm_task.item = entry.serial_no
			pm_task.insert()

			# Get the User linked to the Employee (if needed)
			# Skip this if 'assigned_to' links to Employee directly
			user_id = frappe.db.get_value("Employee", entry.employee, "name")
			if not user_id:
				frappe.throw(f"No User found for Employee {entry.employee}")

			# Create a new Task
			task = frappe.new_doc("Task")
			task.task_name = f"Preventive Maintenance - {entry.scheduled_date}"
			task.due_date = entry.scheduled_date
			task.assign_to = user_id  # or entry.employee if linked directly
			task.type = "Preventive Maintenance Task"
			task.task_type_doc = pm_task.name
			task.insert()

		self.db_set("status", "Submitted")

	def create_schedule_list(self, start_date, end_date, no_of_visit, sales_person):
		schedule_list = []
		start_date_copy = start_date
		date_diff = (getdate(end_date) - getdate(start_date)).days
		add_by = date_diff / no_of_visit

		for _visit in range(cint(no_of_visit)):
			if getdate(start_date_copy) < getdate(end_date):
				start_date_copy = add_days(start_date_copy, add_by)
				if len(schedule_list) < no_of_visit:
					schedule_date = self.validate_schedule_date_for_holiday_list(
						getdate(start_date_copy), sales_person
					)
					if schedule_date > getdate(end_date):
						schedule_date = getdate(end_date)
					schedule_list.append(schedule_date)

		return schedule_list

	def validate_schedule_date_for_holiday_list(self, schedule_date, sales_person):
		validated = False

		employee = frappe.db.get_value("Sales Person", sales_person, "employee")
		if employee:
			holiday_list = get_holiday_list_for_employee(employee)
		else:
			holiday_list = frappe.get_cached_value("Company", self.company, "default_holiday_list")

		holidays = frappe.db.sql_list(
			"""select holiday_date from `tabHoliday` where parent=%s""", holiday_list
		)

		if not validated and holidays:
			# max iterations = len(holidays)
			for _i in range(len(holidays)):
				if schedule_date in holidays:
					schedule_date = add_days(schedule_date, -1)
				else:
					validated = True
					break

		return schedule_date

	def validate_dates_with_periodicity(self):
		if self.start_date and self.end_date and self.periodicity and self.periodicity != "Random":
			date_diff = (getdate(self.end_date) - getdate(self.start_date)).days + 1
			days_in_period = {
				"Weekly": 7,
				"Monthly": 30,
				"Quarterly": 90,
				"Half Yearly": 180,
				"Yearly": 365,
			}

			if date_diff < days_in_period[self.periodicity]:
				throw(
					_(
						"To set {0} periodicity, difference between from and to date must be greater than or equal to {1}"
					).format(self.periodicity, days_in_period[self.periodicity])
				)

	def validate_maintenance_detail(self):
		if not self.item_code:
			throw(_("Please select item code"))
		elif not self.start_date or not self.end_date:
			throw(_("Please select Start Date and End Date for Item {0}").format(self.item_code))
		elif not self.no_of_visits:
			throw(_("Please mention no of visits required"))

		if getdate(self.start_date) >= getdate(self.end_date):
			throw(_("Start date should be less than end date for Item {0}").format(self.item_code))

	def validate_items_table_change(self):
		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return False
		
		fields = [
			"item_code",
			"start_date", 
			"end_date",
			"periodicity",
			"sales_person",
			"no_of_visits",
		]
		
		for field in fields:
			if cstr(getattr(doc_before_save, field, "")) != cstr(getattr(self, field, "")):
				return True
		return False

	def validate_no_of_visits(self):
		return len(self.schedules) != self.no_of_visits

	def validate(self):
		self.validate_end_date_visits()
		self.validate_maintenance_detail()
		self.validate_dates_with_periodicity()
		if not self.schedules or self.validate_items_table_change() or self.validate_no_of_visits():
			self.generate_schedule()

	def on_update(self):
		self.db_set("status", "Draft")

	def validate_schedule(self):
		# Since we only have one item now, just check if schedules exist for the item
		schedule_items = [m.item_code for m in self.get("schedules")]
		
		if not schedule_items or self.item_code not in schedule_items:
			throw(_("Maintenance Schedule is not generated for the item. Please click on 'Generate Schedule'"))

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		delete_events(self.doctype, self.name)

	def on_trash(self):
		delete_events(self.doctype, self.name)

	@frappe.whitelist()
	def get_pending_data(self, data_type, s_date=None, item_name=None):
		if data_type == "date":
			dates = ""
			for schedule in self.schedules:
				if schedule.item_name == item_name and schedule.completion_status == "Pending":
					dates = dates + "\n" + formatdate(schedule.scheduled_date, "dd-MM-yyyy")
			return dates
		elif data_type == "items":
			# Since we only have one item now, return it if it has pending schedules
			for schedule in self.schedules:
				if schedule.completion_status == "Pending":
					return self.item_name
			return ""
		elif data_type == "id":
			for schedule in self.schedules:
				if schedule.item_name == item_name and s_date == formatdate(
					schedule.scheduled_date, "dd-mm-yyyy"
				):
					return schedule.name


def create_schedule_logs(doc, method):
	for row in doc.schedules:
		frappe.msgprint(f"Creating log for Item Code: {row.item_code}")
		
		log = frappe.new_doc("Schedule Log")
		log.serial_no = row.serial_no
		log.item_code = row.item_code
		log.item_name = row.item_name
		log.scheduled_date = row.scheduled_date
		log.actual_date = row.actual_date
		log.assign_to = row.employee
		log.completion_status = row.completion_status
		log.customer = row.customer
		log.customer_name = row.customer_name
		log.customer_email_id = row.customer_email_id
		log.maintenance_schedule = doc.name
		log.insert()

		if row.employee:
			employee = row.employee.strip()
			employee = frappe.get_list(
				"Employee",
				filters={"teammember_id": employee},
				fields=["name"],
				limit=1
			)

			if employee:
				emp_doc = frappe.get_doc("Employee", employee[0].name)

				task_row = emp_doc.append("tasks", {})
				task_row.serial_no = row.serial_no
				task_row.item_code = row.item_code
				task_row.item_name = row.item_name
				task_row.scheduled_date = row.scheduled_date
				task_row.actual_date = row.actual_date
				task_row.completion_status = row.completion_status
				task_row.maintenance_schedule = doc.name

				emp_doc.save()
				frappe.msgprint(f"Task added for Employee (id): {employee}")
			else:
				frappe.log_error(f"Employee with id '{employee}' not found.", "Task Creation Failed")
				
@frappe.whitelist()
def get_assigned_employee(customer):
    # Get the first open ToDo for the customer
    todo = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Customer",
            "reference_name": customer,
            "status": "Open"
        },
        fields=["allocated_to"],
        limit=1
    )

    if not todo:
        return None

    email = todo[0]["allocated_to"]

    # Get employee by matching ToDo email with work_email in Employee
    employee = frappe.get_value("Employee", {"work_email": email}, "name")
    return employee  # returns employee ID (i.e., the "name" field of Employee)
