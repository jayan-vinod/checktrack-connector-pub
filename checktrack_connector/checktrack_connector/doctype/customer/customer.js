// Copyright (c) 2025, satat tech llp and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer', {
    onload: function(frm) {
        frm.fields_dict.customer_items.grid.get_field('serial_no').get_query = function(doc, cdt, cdn) {
            return {
                filters: {
                    customer: ''
                }
            };
        };
    },

});
