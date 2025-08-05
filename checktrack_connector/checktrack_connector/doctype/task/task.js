frappe.ui.form.on("Task", {
    onload: async function(frm) {
        const original_save = frm.save;
        frm.save = function(...args) {
            if (!frm.is_dirty()) {
                // Skip alert
                console.log("Suppressing 'No changes in document' alert");
                return Promise.resolve(frm);
            }
            return original_save.apply(frm, args);
        };
        
        // Get all task type names (these are the doctype names stored in Task Type)
        const task_types = await frappe.db.get_list('Task Type', {
            fields: ['name'],
            pluck: 'name'
        });
        
        // Remove 'Task' from the list if it exists
        const filtered_task_types = (task_types || []).filter(type => type !== 'Task');
        
        // Set query filter for type field to show only doctypes present in Task Type (excluding 'Task')
        frm.set_query('type', function() {
            return {
                filters: [
                    ['DocType', 'name', 'in', filtered_task_types]
                ]
            };
        });

        // Set query for task_type dynamic link to show no existing options (only "Create new" will appear)
        frm.set_query('task_type_doc', function() {
            if (frm.doc.type) {
                return {
                    filters: [
                        [frm.doc.type, 'name', '=', 'null*'] // This ensures no records match
                    ]
                };
            }
            return {};
        });

        // Set default workflow status for new documents
        if (frm.is_new() && !frm.doc.workflow_status) {
            await set_default_workflow_status(frm);
        }
    },

    refresh(frm) {
        render_status_ui(frm);
        // Set field properties based on type field
        set_task_type_doc_requirements(frm);
    },

    workflow_status(frm) {
        render_status_ui(frm);
    },

    type: async function(frm) {
        render_status_ui(frm); // re-render when type changes
        
        // Set field requirements when type changes
        set_task_type_doc_requirements(frm);
        
        // Clear task_type_doc if type is cleared
        if (!frm.doc.type) {
            frm.set_value('task_type_doc', '');
        }
        
        // Re-apply the query filter when type changes
        frm.set_query('task_type_doc', function() {
            if (frm.doc.type) {
                return {
                    filters: [
                        [frm.doc.type, 'name', '=', 'null*'] // This ensures no records match
                    ]
                };
            }
            return {};
        });

        // Update default workflow status when type changes
        if (frm.is_new()) {
            await set_default_workflow_status(frm);
        }
    },

    validate: async function(frm) {
        // Validation: if type is selected, task_type_doc must also be selected
        if (frm.doc.type && !frm.doc.task_type_doc) {
            frappe.msgprint(__('Please select Task Type Doc when Type is selected'));
            frappe.validated = false;
            return;
        }

        // Check if workflow status has changed and validate required fields
        if (frm.doc.workflow_status && frm.doc.__islocal !== 1) {
            // Get the original workflow status from the server
            const original_doc = await frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Task",
                    name: frm.doc.name
                }
            });

            const original_status = original_doc.message?.workflow_status;
            
            // If status has changed, validate required fields
            if (original_status !== frm.doc.workflow_status) {
                const validation_result = await validate_required_fields_for_status(frm, frm.doc.workflow_status);
                
                if (!validation_result.valid) {
                    // Show error message with missing fields
                    let message = validation_result.message;
                    if (validation_result.missing_fields && validation_result.missing_fields.length > 0) {
                        message += "<br><br><strong>Missing fields:</strong><br>";
                        message += validation_result.missing_fields.map(field => `• ${field}`).join('<br>');
                    }
                    
                    frappe.msgprint({
                        title: __('Required Fields Missing'),
                        message: message,
                        indicator: 'red'
                    });
                    
                    frappe.validated = false;
                    return;
                }
            }
        }
    }
});

// New function to set default workflow status based on start_state
async function set_default_workflow_status(frm) {
    try {
        const task_type = frm.doc.type || "Task";
        
        // Get the Task Type document with status flow
        const task_type_doc = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Task Type",
                name: task_type
            }
        });
        
        const status_flow = task_type_doc.message?.status_flow || [];
        
        // Find the status with start_state = 1
        const start_status_row = status_flow.find(row => row.start_state === 1);
        
        if (start_status_row && start_status_row.workflow_status) {
            // Set the default workflow status
            frm.set_value('workflow_status', start_status_row.workflow_status);
        } else {
            // Fallback to 'Pending' if no start state is found
            frm.set_value('workflow_status', 'Pending');
        }
        
    } catch (error) {
        console.error("Error setting default workflow status:", error);
        // Fallback to 'Pending' on error
        frm.set_value('workflow_status', 'Pending');
    }
}

function set_task_type_doc_requirements(frm) {
    // Set task_type_doc as required if type is selected
    if (frm.doc.type) {
        frm.set_df_property('task_type_doc', 'reqd', 1);
        frm.set_df_property('task_type_doc', 'bold', 1);
    } else {
        frm.set_df_property('task_type_doc', 'reqd', 0);
        frm.set_df_property('task_type_doc', 'bold', 0);
    }
}

// Helper function to get field labels from doctype meta
async function get_field_labels(doctype, field_names) {
    try {
        // Get the doctype meta to access field definitions
        const meta = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "DocType",
                name: doctype
            }
        });
        
        const fields = meta.message?.fields || [];
        const field_labels = {};
        
        // Map field names to their labels
        field_names.forEach(field_name => {
            const field_def = fields.find(f => f.fieldname === field_name);
            field_labels[field_name] = field_def ? field_def.label : field_name;
        });
        
        return field_labels;
    } catch (error) {
        console.error("Error getting field labels:", error);
        // Return field names as fallback
        const fallback_labels = {};
        field_names.forEach(field_name => {
            fallback_labels[field_name] = field_name;
        });
        return fallback_labels;
    }
}

// New function to validate required fields for status change
async function validate_required_fields_for_status(frm, target_status) {
    const task_type = frm.doc.type || "Task";
    
    try {
        // Get the Task Type document with status flow
        const task_type_doc = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Task Type",
                name: task_type
            }
        });
        
        const status_flow = task_type_doc.message?.status_flow || [];
        
        // Find the status flow row for the target status
        const target_status_row = status_flow.find(row => row.workflow_status === target_status);
        
        if (!target_status_row || !target_status_row.required_fields) {
            return { valid: true }; // No required fields specified
        }
        
        // Parse required fields (assuming they're stored as comma-separated string with quotes)
        let required_fields = [];
        try {
            // Remove outer quotes and split by comma
            const fields_string = target_status_row.required_fields.replace(/^['"]|['"]$/g, '');
            required_fields = fields_string.split(',').map(field => field.trim().replace(/['"`]/g, ''));
        } catch (e) {
            console.error("Error parsing required fields:", e);
            return { valid: true }; // If parsing fails, allow the change
        }
        
        // Check if task_type_doc exists (required for field validation)
        if (!frm.doc.task_type_doc) {
            return {
                valid: false,
                message: "Task Type Doc is required before changing status.",
                missing_fields: []
            };
        }
        
        // Get the task_type_doc to check field values
        const task_type_doc_data = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: frm.doc.type,
                name: frm.doc.task_type_doc
            }
        });
        
        const doc_data = task_type_doc_data.message;
        const missing_field_names = [];
        
        // Check each required field
        required_fields.forEach(field => {
            if (!doc_data[field] || doc_data[field] === '' || doc_data[field] === null) {
                missing_field_names.push(field);
            }
        });
        
        if (missing_field_names.length > 0) {
            // Get field labels for the missing fields
            const field_labels = await get_field_labels(frm.doc.type, missing_field_names);
            
            // Convert field names to labels
            const missing_field_labels = missing_field_names.map(field_name => field_labels[field_name]);
            
            return {
                valid: false,
                message: `The following required fields must be filled before changing status to "${target_status}":`,
                missing_fields: missing_field_labels
            };
        }
        
        return { valid: true };
        
    } catch (error) {
        console.error("Error validating required fields:", error);
        frappe.msgprint("Error occurred while validating required fields. Please try again.");
        return { valid: false, message: "Validation error occurred." };
    }
}

function render_status_ui(frm) {
    const wrapper_id = 'custom-status-overview-wrapper';
    let wrapper = $(`#${wrapper_id}`);
    if (!wrapper.length) {
        frm.dashboard.add_section(`
            <div id="${wrapper_id}" style="padding-top: 12px;"></div>
        `, __("Status Overview"));
        wrapper = $(`#${wrapper_id}`);
    }
    wrapper.empty();

    // If no type selected, use "Task" as default type
    const task_type = frm.doc.type || "Task";

    // Call server to get status list based on selected type (or "Task" if no type selected)
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Task Type",
            filters: {
                name: task_type
            },
            fields: ["name"],
            limit: 1
        },
        callback: function (res) {
            const doc = res.message?.[0];
            if (!doc) {
                render_status_dropdown(wrapper, frm, ['Pending'], []);
                return;
            }
            
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Task Type",
                    name: doc.name
                },
                callback: function (r) {
                    const status_flow = r.message.status_flow || [];
                    const all_statuses = status_flow.map(row => row.workflow_status);
                    
                    if (!all_statuses.length) {
                        render_status_dropdown(wrapper, frm, ['Pending'], []);
                        return;
                    }

                    // Get valid next statuses based on current status
                    const current_status = frm.doc.workflow_status;
                    let valid_next_statuses = [];

                    if (current_status) {
                        // Find all rows where workflow_status matches current status
                        const matching_rows = status_flow.filter(row => row.workflow_status === current_status);
                        
                        // Get all possible next statuses and split comma-separated values
                        valid_next_statuses = matching_rows
                            .map(row => row.workflow_status_change_to)
                            .filter(status => status) // Remove empty values
                            .flatMap(status => status.split(',')) // Split comma-separated values
                            .map(status => status.trim()) // Remove whitespace
                            .map(status => status.replace(/['"]/g, '')) // Remove quotes
                            .filter(status => status); // Remove empty strings
                        
                        // Remove duplicates
                        valid_next_statuses = [...new Set(valid_next_statuses)];
                        
                        // Always include current status as an option
                        if (!valid_next_statuses.includes(current_status)) {
                            valid_next_statuses.unshift(current_status);
                        }
                    } else {
                        // If no current status, show all available statuses
                        valid_next_statuses = all_statuses;
                    }

                    render_status_dropdown(wrapper, frm, all_statuses, valid_next_statuses);
                }
            });
        }
    });
}

function render_status_dropdown(wrapper, frm, all_statuses, valid_next_statuses) {
    const is_submitted = frm.doc.docstatus === 1;
    const is_new_doc = frm.is_new(); // Check if document is new (not saved yet)
    
    // Use valid_next_statuses for dropdown options, fallback to all_statuses if empty
    const dropdown_options = valid_next_statuses.length > 0 ? valid_next_statuses : all_statuses;
    
    const status_display = `
        <div style="display: flex; align-items: center; gap: 16px;">
            <div style="
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background-color: #d1d1d1;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                color: #fff;
                font-size: 14px;
            ">
                ${frm.doc.workflow_status ? frm.doc.workflow_status.charAt(0).toUpperCase() : '-'}
            </div>
            <div>
                <div style="font-weight: 600; font-size: 14px;">
                    Current Status: ${frm.doc.workflow_status || 'Not Set'}
                </div>
                <div style="font-size: 12px; color: #888;">
                    Last Updated: ${frappe.datetime.get_datetime_as_string(frm.doc.modified)}
                </div>

                ${!is_submitted && !is_new_doc ? `
                <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                    <select id="workflow_status-dropdown" style="padding: 6px 10px; border-radius: 4px; border: 1px solid #ccc;">
                        ${dropdown_options.map(s => `
                            <option value="${s}" ${s === frm.doc.workflow_status ? "selected" : ""}>${s}</option>
                        `).join('')}
                    </select>
                    <button id="workflow_status-save-btn" style="
                        padding: 6px 12px; 
                        border-radius: 4px; 
                        border: 1px solid #007bff; 
                        background-color: #007bff; 
                        color: white; 
                        cursor: pointer;
                        font-size: 12px;
                        font-weight: 500;
                        display: none;
                    ">Save</button>
                </div>
                <div style="margin-top: 8px; font-size: 12px; color: #666; font-style: italic;">
                    Select a different status to show the Save button.
                </div>` : is_new_doc ? `
                <div style="margin-top: 8px; font-size: 12px; color: #888; font-style: italic;">
                    Status can be changed after saving the task.
                </div>` : ''}
            </div>
        </div>
    `;
    wrapper.html(status_display);

    // Only add event listeners if document is not submitted and not new
    if (!is_submitted && !is_new_doc) {
        setTimeout(() => {
            const dropdown = $('#workflow_status-dropdown');
            const saveBtn = $('#workflow_status-save-btn');
            const originalStatus = frm.doc.workflow_status;
            
            // Handle dropdown change
            dropdown.on('change', function () {
                const selected_status = $(this).val();
                
                // Show/hide save button based on whether status changed
                if (selected_status !== originalStatus) {
                    saveBtn.show();
                } else {
                    saveBtn.hide();
                }
            });
            
            // Handle save button click
            saveBtn.on('click', async function () {
                const selected_status = dropdown.val();
                
                if (selected_status !== originalStatus) {
                    try {
                        // First validate the status change without saving
                        const validation_result = await validate_required_fields_for_status(frm, selected_status);
                        
                        if (!validation_result.valid) {
                            // Show validation error
                            let message = validation_result.message;
                            if (validation_result.missing_fields && validation_result.missing_fields.length > 0) {
                                message += "<br><br><strong>Missing fields:</strong><br>";
                                message += validation_result.missing_fields.map(field => `• ${field}`).join('<br>');
                            }
                            
                            frappe.msgprint({
                                title: __('Required Fields Missing'),
                                message: message,
                                indicator: 'red'
                            });
                            
                            // Revert dropdown to original state
                            dropdown.val(originalStatus);
                            saveBtn.hide();
                            return;
                        }
                        
                        // Set the value first
                        await frm.set_value('workflow_status', selected_status);
                        
                        // Then save the document
                        await frm.save();
                        
                        // Hide button after successful save
                        saveBtn.hide();
                                       
                    } catch (error) {
                        console.error('Save failed:', error);
                        
                        // Revert the workflow_status field to original value
                        await frm.set_value('workflow_status', originalStatus);
                        
                        // Revert dropdown to original state
                        dropdown.val(originalStatus);
                        
                        // Hide the save button
                        saveBtn.hide();
                        
                        // Show error message
                        frappe.msgprint({
                            title: __('Save Failed'),
                            message: error.message || 'An error occurred while saving. Please try again.',
                            indicator: 'red'
                        });
                    }
                }
            });
        }, 100);
    }
}