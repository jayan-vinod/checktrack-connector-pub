// Copyright (c) 2025, satat tech llp and contributors
// For license information, please see license.txt

frappe.ui.form.on('CheckTrack Integration', {
    refresh: function (frm) {
        if (frm.page.btn_primary) {
            frm.page.btn_primary.hide();
        }
        if (!frm.is_new()) {

            check_tenant_exists(frm, function(exists) {
                if (exists) {

                    frm.fields.forEach(field => {
                        frm.set_df_property(field.df.fieldname, 'hidden', true);
                    });
                    frm.dashboard.clear_headline();
                    frm.dashboard.set_headline(
                        `<div class="alert alert-success" style="margin-bottom: 0px;">
                            <strong>${__("Connected to Checktrack")}</strong>
                        </div>`
                    );
                    frm.set_indicator(__('Connected to Frappe'), 'green');
                    frm.remove_custom_button('Connect');

                } else {
                    let d_password = "";
                    frm.fields.forEach(field => {
                        frm.set_df_property(field.df.fieldname, 'hidden', false);
                    });
                    frm.dashboard.clear_headline();
                    frappe.call({
                        method: 'checktrack_connector.api.get_decrypted_password_for_doc',
                        args: {
                            docname: frm.doc.name
                        },
                        callback: function(r) {
                            d_password = r.message;
                            // console.log("Decrypted password: ", d_password);
                        },
                    });
                    frm.add_custom_button(__('Connect'), function () {

                        if (!frm.doc.email || !frm.doc.password) {
                            frappe.msgprint(__('Please fill in all required fields before CheckTrack intergration.'), __('Validation Error'));
                            return;
                        }
                        // frm.fields.forEach(field => {
                        //     frm.set_df_property(field.df.fieldname, 'read_only', true);
                        // });

                        let $btn = $('.btn-primary:contains("Connect")');
                        let original_text = $btn.text();
                        $btn.prop('disabled', true);
                        $btn.html(`<i class="fa fa-spinner fa-spin"></i> ${__("Connecting...")}`);


                        const enable_form = function() {
                            $btn.prop('disabled', false);
                            $btn.html(original_text);
                            frm.enable_save();
                            // frm.fields.forEach(field => {
                            //     frm.set_df_property(field.df.fieldname, 'read_only', false);
                            // });
                        };

                        new Promise((resolve, reject) => {
                            if (frm.is_dirty()) {
                                frm.save()
                                    .then(() => {
                                        resolve();
                                    })
                                    .catch(reject);
                            } else {
                                resolve();
                            }
                        })
                        .then(() => {
                            return new Promise((resolve, reject) => {
                                frappe.call({
                                    method: 'checktrack_connector.api.check_tenant_exists',
                                    args: {
                                        email: frm.doc.email,
                                        password: d_password || ""
                                    },
                                    callback: function(response) {
                                        resolve(response.message && response.message.exists);
                                    },
                                    error: function(err) {
                                        reject(err);
                                    }
                                });
                            });
                        })
                        .then((exists) => {
                            return new Promise((resolve, reject) => {
                                frappe.call({
                                    method: 'checktrack_connector.api.get_decrypted_password_for_doc',
                                    args: { docname: frm.doc.name },
                                    callback: function(r) {
                                        const d_password = r.message;
                                        // console.log("password: ", d_password);

                                        if (!d_password) {
                                            reject(new Error("Decrypted password not found"));
                                            return;
                                        }

                                        frappe.call({
                                            method: 'checktrack_connector.api.checktrack_integration',
                                            args: {
                                                email: frm.doc.email,
                                                password: d_password
                                            },
                                            callback: function(response) {
                                                resolve(response);
                                            },
                                            error: function(err) {
                                                reject(err);
                                            }
                                        });
                                    },
                                    error: function(err) {
                                        reject(err);
                                    }
                                });
                            });
                        })
                        .then((response) => {
                            enable_form();

                            if (response.message) {
                                if (response.message.is_fully_integration) {
                                    frappe.msgprint(__('Checktrack successfully integration.'));
                                    frm.reload_doc();
                                }
                            } else {
                                frappe.msgprint(__('Failed to integrat!'));
                            }
                        })
                        .catch((error) => {
                            console.error(error);
                            enable_form();
                            frappe.msgprint(__('Connection failed: ') + (error.message || ''));
                        });

                    }).addClass('btn-primary');
                }
            });
        }
    },

    email: function(frm) {
        frm.trigger('refresh');
    },

    password: function(frm) {
        frm.raw_password = frm.fields_dict.password.input.value;

        frm.trigger('refresh');
    },
});

function check_tenant_exists(frm, callback) {

    frappe.call({
        method: 'checktrack_connector.api.check_tenant_exists',
        args: {
            email: frappe.session.user 
        },
        callback: function (response) {
            var exists = response.message && response.message.exists;
            if (callback) callback(exists);
        },
        error: function(err) {
            console.error("Error checking tenant exists:", err);
            if (callback) callback(false);
        }
    });
}



