// Job Registration custom workflow - WORKING VERSION
// Job Registration - Candidate filter logic
// Job Registration - Candidate filter logic using 'custom_candidate'
frappe.ui.form.on('Job Registration', {
    onload: function(frm) {
        // Hide candidate field if no customer
        frm.toggle_display('custom_candidate', !!frm.doc.customer);

        // Apply filter if customer already exists
        if (frm.doc.customer) {
            set_custom_candidate_query(frm);
        }
    },

    customer: function(frm) {
        console.log("🔍 Customer changed:", frm.doc.customer);

        if (frm.doc.customer) {
            // Show candidate only when customer is chosen
            frm.toggle_display('custom_candidate', true);
            frm.set_value('custom_candidate', ''); // clear previous candidate
            set_custom_candidate_query(frm);
        } else {
            // Hide and clear candidate when customer is cleared
            frm.toggle_display('custom_candidate', false);
            frm.set_value('custom_candidate', '');
        }
    }
});

// Function to apply filter to custom_candidate field
function set_custom_candidate_query(frm) {
    frm.set_query('custom_candidate', function() {
        return {
            filters: {
                customer: frm.doc.customer,
                docstatus: 1   // ✅ show only submitted candidates
            }
        };
    });
}



frappe.ui.form.on('Job Registration', {
    refresh: function(frm) {
        console.log("🔍 DEBUG: Refresh triggered, docstatus =", frm.doc.docstatus);
        console.log("🔍 DEBUG: Current workflow status =", frm.doc.custom_workflow_status);

        // Set header status indicator
        if (frm.doc.custom_workflow_status) {
            frm.page.set_indicator(frm.doc.custom_workflow_status,
                frm.doc.custom_workflow_status === "Draft" ? "blue" :
                frm.doc.custom_workflow_status === "Pending" ? "orange" : "green"
            );
        }
        
        // Calculate pending balance on refresh
        calculate_pending_balance(frm);

        // Add Create Sales Order button
        if (!frm.doc.__islocal) {
            // Show Create Sales Order button only in Pending or Verified
            if (
                !frm.is_new() &&
                ["Pending", "Verified"].includes(frm.doc.custom_workflow_status)
            ) {
                frm.add_custom_button(__('Create Proforma Invoice'), function() {
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

        }

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

        // Auto-calculate customer discount on refresh if items exist
        if (frm.doc.customer && frm.doc.service_package && frm.doc.service_package.length > 0) {
            calculate_customer_discount(frm);
        }
    },

    validate: function(frm) {
        console.log("🔍 DEBUG: Running validate()");
        update_total_amount(frm);
        checkChildTableEntries(frm);
        calculate_pending_balance(frm);
    },

    customer: function(frm) {
        console.log("🔍 DEBUG: Customer changed to:", frm.doc.customer);
        // Clear existing discount when customer changes
        frm.set_value("custom_discount_amount", 0);
        
        // Recalculate discounts for existing items
        if (frm.doc.service_package && frm.doc.service_package.length > 0) {
            setTimeout(() => calculate_customer_discount(frm), 500);
        }
    },

    advance_payment: function(frm) {
        console.log("🔍 DEBUG: Advance Payment updated");
        calculate_pending_balance(frm);
    },
    
    custom_discount_amount: function(frm) {
        console.log("🔍 DEBUG: Discount amount updated");
        calculate_pending_balance(frm);
    },
    
    total_amount: function(frm) {
        console.log("🔍 DEBUG: Total amount updated");
        calculate_pending_balance(frm);
    },

    after_save: function(frm) {
        console.log("🔍 DEBUG: After save triggered");
        if (frm.doc.custom_workflow_status === "Pending") {
            create_government_purchase_invoice(frm);
        }
        checkChildTableEntries(frm);
    }
});

// Service Package child table - AUTO-CALCULATE DISCOUNT
frappe.ui.form.on("Job Registration Service Item", {
    service_package_item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log("🔍 DEBUG: Service item changed:", row.service_package_item);
        
        if (row.service_package_item) {
            // Get item price first
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
                        console.log("🔍 DEBUG: Set rate to:", rate);
                    } else {
                        frappe.model.set_value(cdt, cdn, 'amount', 0);
                    }
                    
                    // Update total and calculate customer discount
                    update_total_amount(frm);
                    
                    // IMPORTANT: Calculate customer discount after price is set
                    setTimeout(() => {
                        console.log("🔍 DEBUG: About to calculate customer discount...");
                        calculate_customer_discount(frm);
                    }, 300);
                }
            });
        }
    },
    
    amount: function(frm) {
        update_total_amount(frm);
        // Recalculate discount when amount changes
        setTimeout(() => calculate_customer_discount(frm), 100);
    },
    
    service_package_remove: function(frm) {
        update_total_amount(frm);
        // Recalculate discount when items are removed
        setTimeout(() => calculate_customer_discount(frm), 100);
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

// Calculate pending balance (SINGLE DISCOUNT FIELD)
function calculate_pending_balance(frm) {
    let totalAmount = frm.doc.total_amount ? parseFloat(frm.doc.total_amount) : 0;
    let discount = frm.doc.custom_discount_amount ? parseFloat(frm.doc.custom_discount_amount) : 0;
    let advancePayment = frm.doc.advance_payment ? parseFloat(frm.doc.advance_payment) : 0;
    
    console.log("🔍 DEBUG: Pending balance calculation:", {
        totalAmount,
        discount,
        advancePayment
    });
    
    let totalAfterDiscount = totalAmount - discount;
    let pending = Math.max(0, totalAfterDiscount - advancePayment);
    
    console.log("🔍 DEBUG: Final pending balance:", pending);
    
    frm.set_value("pending_balance", pending);
    frm.refresh_field("pending_balance");
}

// Update total amount
function update_total_amount(frm) {
    let total = 0;
    if (Array.isArray(frm.doc.service_package)) {
        frm.doc.service_package.forEach(row => {
            total += row.amount ? parseFloat(row.amount) : 0;
        });
    }
    
    frm.set_value("total_amount", total);
    calculate_pending_balance(frm);
}

// AUTO-CALCULATE CUSTOMER DISCOUNT
function calculate_customer_discount(frm) {
    console.log("🔍 DEBUG: === Starting calculate_customer_discount ===");
    console.log("🔍 DEBUG: Customer:", frm.doc.customer);
    console.log("🔍 DEBUG: Service items:", frm.doc.service_package?.length || 0);
    
    if (!frm.doc.customer || !frm.doc.service_package || frm.doc.service_package.length === 0) {
        console.log("🔍 DEBUG: No customer or no items, setting discount to 0");
        frm.set_value("custom_discount_amount", 0);
        calculate_pending_balance(frm);
        return;
    }
    
    // Prepare service items
    let service_items = frm.doc.service_package.map(item => ({
        service_package_item: item.service_package_item
    }));
    
    console.log("🔍 DEBUG: Calling server with:", service_items);
    
    frappe.call({
        method: "alhabbai.alhabbai.doctype.job_registration.job_registration.get_customer_discount_for_items",
        args: {
            customer: frm.doc.customer,
            service_items: JSON.stringify(service_items)
        },
        callback: function(r) {
            console.log("🔍 DEBUG: Server response:", r.message);
            if (r.message) {
                let total_discount = r.message.total_discount || 0;
                
                console.log("🔍 DEBUG: Setting discount to:", total_discount);
                
                // Set the discount
                frm.set_value("custom_discount_amount", total_discount);
                calculate_pending_balance(frm);
                
                // Show notification
                if (total_discount > 0) {
                    frappe.show_alert({
                        message: `Customer discount applied: ${total_discount}`,
                        indicator: 'green'
                    });
                }
            }
        },
        error: function(r) {
            console.error("🔍 DEBUG: Error:", r);
        }
    });
}

// Check child table entries for workflow
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

// Create government purchase invoice
function create_government_purchase_invoice(frm, amount = null) {
    console.log("🔍 DEBUG: Checking for existing PI");
    
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
                    frm.reload_doc();
                }
            },
            error: function(r) {
                console.error("🔍 DEBUG: PI creation failed:", r);
                frappe.show_alert({
                    message: `Failed to create Purchase Invoice`,
                    indicator: 'red'
                });
            }
        });
    });
}