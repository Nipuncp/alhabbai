// Job Registration custom workflow
frappe.ui.form.on('Job Registration', {
    refresh: function(frm) {
        console.log("🔍 DEBUG: Refresh triggered, docstatus =", frm.doc.docstatus);
        console.log("🔍 DEBUG: Current workflow status =", frm.doc.custom_workflow_status);
        console.log("🔍 DEBUG: Document upload entries =", frm.doc.table_tujy ? frm.doc.table_tujy.length : 0);
        console.log("🔍 DEBUG: Service package entries =", frm.doc.service_package ? frm.doc.service_package.length : 0);

        // Set header status indicator
        if (frm.doc.custom_workflow_status) {
            frm.page.set_indicator(frm.doc.custom_workflow_status,
                frm.doc.custom_workflow_status === "Draft" ? "blue" :
                frm.doc.custom_workflow_status === "Pending" ? "orange" : "green"
            );
        }

        // Check entries and update status
        if (!frm.doc.__islocal) {  // Only show for saved documents
            frm.add_custom_button(__('Create Sales Order'), function() {
                frappe.call({
                    method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_sales_order_from_job_registration",
                    args: { job_registration: frm.doc.name },
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(__("Sales Order {0} created successfully.", [r.message]));
                            frappe.set_route("Form", "Sales Order", r.message);
                        }
                    }
                });
            }, __('Create'));
        }
        

        // Add Sales Order button for submitted documents
        // if (frm.doc.docstatus === 1) {
        //     frm.add_custom_button(__('Create Sales Order'), function() {
        //         frappe.call({
        //             method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_sales_order_from_job_registration",
        //             args: { job_registration: frm.doc.name },
        //             callback: function(r) {
        //                 if (r.message) {
        //                     frappe.msgprint(__("Sales Order {0} created successfully.", [r.message]));
        //                     frappe.set_route("Form", "Sales Order", r.message);
        //                 }
        //             }
        //         });
        //     });
        // }

        // Add Verify button for Verifier role when in Pending state
        if (frm.doc.docstatus === 0 && frm.doc.custom_workflow_status === "Pending" && frappe.user_roles.includes("Verifier")) {
            frm.page.clear_primary_action();
            frm.add_custom_button(__("Verify"), function() {
                frappe.confirm(
                    __("This will verify the document. Continue?"),
                    function() {
                        frm.set_value("custom_workflow_status", "Verified");
                        frm.save().then(() => {
                            setTimeout(() => frm.savesubmit(), 1000);
                        });
                    }
                );
            }).addClass("btn-primary");
        }
    },

    validate: function(frm) {
        console.log("🔍 DEBUG: Running validate()");
        update_total_amount(frm);
        checkChildTableEntries(frm);
    },

    on_submit: function(frm) {
        console.log("🔍 DEBUG: Job Registration submitted");
    },

    advance_payment: function(frm) {
        console.log("🔍 DEBUG: Advance Payment updated");
        // Calculate pending by subtracting advance payment from (total - discount)
        let totalAfterDiscount = (frm.doc.total_amount || 0) - (frm.doc.custom_discount_amount || 0);
        let pending = totalAfterDiscount - (frm.doc.advance_payment || 0);
        frm.set_value("pending_balance", pending);
        frm.refresh_field("pending_balance");
    },

    after_save: function(frm) {
        console.log("🔍 DEBUG: After save triggered");
        if (frm.doc.custom_workflow_status === "Pending") {
            create_government_purchase_invoice(frm);
        }
    }
});

// Service Package child table
frappe.ui.form.on("Job Registration Service Item", {
    service_package_item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.service_package_item) {
            console.log("🔍 DEBUG: Fetching price for item:", row.service_package_item);
            frappe.call({
                method: "erpnext.stock.get_item_details.get_item_details",
                args: {
                    args: {
                        item_code: row.service_package_item,
                        doctype: "Sales Order",
                        customer: frm.doc.customer,
                        company: frappe.defaults.get_default("company"),
                        transaction_date: frappe.datetime.get_today(),
                        price_list: "Standard Selling",
                        price_list_currency: frappe.defaults.get_default("currency"),
                        plc_conversion_rate: 1.0,
                        conversion_rate: 1.0,
                        qty: 1
                    }
                },
                callback: function(r) {
                    if (r.message) {
                        let rate = r.message.price_list_rate || r.message.rate || 0;
                        frappe.model.set_value(cdt, cdn, 'amount', rate);
                    } else {
                        frappe.model.set_value(cdt, cdn, 'amount', 0);
                    }
                    update_total_amount(frm);
                }
            });
        }
    },
    amount: function(frm) {
        update_total_amount(frm);
    },
    service_package_remove: function(frm) {
        update_total_amount(frm);
    }
});

// Documents child table
frappe.ui.form.on('Documents', {
    table_tujy_add: function(frm) {
        if (!frm.is_new()) {
            checkChildTableEntries(frm);
        }
    },
    table_tujy_remove: function(frm) {
        if (!frm.is_new()) {
            checkChildTableEntries(frm);
        }
    }
});

// Update status based on entries
function checkChildTableEntries(frm) {
    const hasDocumentsEntries = frm.doc.table_tujy && frm.doc.table_tujy.length > 0;
    console.log("🔍 DEBUG: Documents entries present:", hasDocumentsEntries);

    if (frm.doc.docstatus === 0 && !frm.is_new()) {
        if (hasDocumentsEntries && frm.doc.custom_workflow_status !== "Pending") {
            console.log("🔍 DEBUG: Setting status to Pending");
            frm.set_value("custom_workflow_status", "Pending");
        } else if (!hasDocumentsEntries && frm.doc.custom_workflow_status !== "Draft") {
            frm.set_value("custom_workflow_status", "Draft");
        }
    }
}

// Total + advance calculation
function update_total_amount(frm) {
    let total = 0;
    if (Array.isArray(frm.doc.service_package)) {
        frm.doc.service_package.forEach(row => {
            total += row.amount || 0;
        });
    }
    frm.set_value("total_amount", total);
    frm.set_value("pending_balance", total - (frm.doc.advance_payment || 0));
    frm.refresh_fields(["total_amount", "pending_balance"]);
}

// Call backend to create purchase invoice
function create_government_purchase_invoice(frm, amount = null) {
    console.log("🔍 DEBUG: Checking for existing PI");
    
    // Get list of PIs with our Job Registration
    frappe.db.get_value('Purchase Invoice', 
        { custom_job_registration: frm.doc.name, docstatus: ['!=', 2] }, 
        ['name']
    ).then(r => {
        if (r && r.message && r.message.name) {
            console.log("🔍 DEBUG: PI already exists:", r.message.name);
            frappe.show_alert({
                message: `Purchase Invoice ${r.message.name} already exists`,
                indicator: 'yellow'
            });
            return;
        }

        console.log("🔍 DEBUG: Creating new PI");
        frappe.call({
            method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_government_purchase_invoice",
            args: {
                job_registration: frm.doc.name,
                amount: amount
            },
            freeze: true,
            freeze_message: __("Creating Purchase Invoice..."),
            callback: function(r) {
                if (r.message) {
                    console.log("🔍 DEBUG: PI created successfully:", r.message);
                    frappe.show_alert({
                        message: `Purchase Invoice ${r.message} created successfully`,
                        indicator: 'green'
                    });
                    // Reload the form to reflect changes
                    frm.reload_doc();
                }
            },
            error: function(r) {
                console.error("🔍 DEBUG: PI creation failed:", r);
                frappe.show_alert({
                    message: `Failed to create Purchase Invoice: ${r._server_messages || "Unknown error"}`,
                    indicator: 'red'
                });
            }
        });
    }).catch(err => {
        console.error("🔍 DEBUG: Error checking existing PI:", err);
        frappe.show_alert({
            message: "Error checking for existing Purchase Invoice",
            indicator: 'red'
        });
    });
}

frappe.ui.form.on('Job Registration', {
    after_save: function(frm) {
        if (frm.doc.docstatus === 0) {
            checkChildTableEntries(frm);
        }
    }
});
