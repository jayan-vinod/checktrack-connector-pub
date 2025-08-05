// Copyright (c) 2025, Satat Tech LLP and Contributors
// License: GNU General Public License v3. See license.txt

frappe.provide("checktrack_connector.maintenance");

frappe.ui.form.on("Maintenance Schedule", {

	onload: function (frm) {
		if (!frm.doc.status) {
			frm.set_value({ status: "Draft" });
		}
		if (frm.doc.__islocal) {
			frm.set_value({ transaction_date: frappe.datetime.get_today() });
			
			// Automatically set company based on currently logged in user's employee record
			set_company_from_user(frm);
		}
	},
	
	refresh: function (frm) {
		setTimeout(() => {
			frm.toggle_display("generate_schedule", !(frm.is_new() || frm.doc.docstatus));
			frm.toggle_display("schedule", !frm.is_new());
		}, 10);
	},

    customer: function(frm) {
        // Set query filter for serial_no field (now standalone)
        frm.set_query('serial_no', function() {
            return {
                filters: {
                    'customer': frm.doc.customer,
                }
            };
        });

        // Optionally clear serial_no if customer changes
        frm.set_value('serial_no', null);

        if (frm.doc.customer) {
            frappe.call({
                method: "checktrack_connector.checktrack_connector.doctype.maintenance_schedule.maintenance_schedule.get_assigned_employee",
                args: {
                    customer: frm.doc.customer
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('employee', r.message);
                    } else {
                        frm.set_value('employee', null);
                        frappe.msgprint("No employee assigned to this customer.");
                    }
                }
            });
        }
    }
});

// Function to set company based on currently logged in user
function set_company_from_user(frm) {
    // Get the current user's email
    const user_email = frappe.session.user;
    
    // Find employee record where work_email matches the current user's email
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Employee",
            filters: {
                "work_email": user_email
            },
            fields: ["company"]
        },
        callback: function(response) {
            if (response.message && response.message.length > 0) {
                // Employee found, set the company from employee's company field
                const employee_company = response.message[0].company;
                frm.set_value("company", employee_company);
            } else {
                // If no matching employee found, show message
                frappe.show_alert({
                    message: __("Could not find matching employee record with email: ") + user_email,
                    indicator: 'orange'
                }, 5);
            }
        }
    });
}