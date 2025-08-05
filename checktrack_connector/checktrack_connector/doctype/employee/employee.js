// Copyright (c) 2025, satat tech llp and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee", {
    first_name: function(frm) {
        set_employee_name(frm);
    },
    last_name: function(frm) {
        set_employee_name(frm);
    },
    refresh: function(frm) {
        if (!frm.doc.employee_name) {
            set_employee_name(frm);
        }
    }
});

function set_employee_name(frm) {
    const firstName = frm.doc.first_name || '';
    const lastName = frm.doc.last_name || '';
    const fullName = `${firstName} ${lastName}`.trim();
    frm.set_value('employee_name', fullName);
}