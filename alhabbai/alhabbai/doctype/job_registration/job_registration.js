// ---------------------------------------------------------------
// Job Registration Workflow JS (Final Auto-Submit Version)
// ---------------------------------------------------------------
frappe.ui.form.on("Job Registration", {
    onload(frm) {
        // Hide candidate field if no customer
        frm.toggle_display("custom_candidate", !!frm.doc.customer);
        if (frm.doc.customer) set_custom_candidate_query(frm);
    },

    customer(frm) {
        frm.toggle_display("custom_candidate", !!frm.doc.customer);
        frm.set_value("custom_candidate", "");
        if (frm.doc.customer) set_custom_candidate_query(frm);
    },

    refresh(frm) {
        console.log("🔍 Refresh:", frm.doc.custom_workflow_status, frm.doc.docstatus);
        // Hide default Submit for Receptionist/Typist
        if (frm.doc.docstatus === 0 && !frappe.user_roles.includes("Verifier")) {
        frm.hide_submit();
        }


        // Header indicator
        if (frm.doc.custom_workflow_status) {
            frm.page.set_indicator(
                frm.doc.custom_workflow_status,
                frm.doc.custom_workflow_status === "Draft"
                    ? "blue"
                    : frm.doc.custom_workflow_status === "Pending"
                    ? "orange"
                    : "green"
            );
        }

        calculate_pending_balance(frm);

        // ---------------------------------------------------------------
        //  Verifier Button (auto-submit + create SO)
        // ---------------------------------------------------------------
        if (
            frm.doc.docstatus === 0 &&
            frm.doc.custom_workflow_status === "Pending" &&
            frappe.user_roles.includes("Verifier")
        ) {
            frm.page.clear_primary_action();
            frm.add_custom_button(__("Verify & Create Proforma"), function () {
                frappe.confirm(
                    __("This will verify, submit, and create a Proforma Invoice. Continue?"),
                    function () {
                        frappe.call({
                            method: "alhabbai.alhabbai.doctype.job_registration.job_registration.verify_and_create_proforma",
                            args: { job_registration: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Verifying & Submitting..."),
                            callback(r) {
                                if (!r.exc) frm.reload_doc();
                            },
                        });
                    }
                );
            }).addClass("btn-primary");
        }

        // Auto-calculate customer discount if items exist
        if (frm.doc.customer && frm.doc.service_package?.length > 0) {
            calculate_customer_discount(frm);
        }
    },

    validate(frm) {
        update_total_amount(frm);
        checkChildTableEntries(frm);
        calculate_pending_balance(frm);
    },

    advance_payment(frm) {
        calculate_pending_balance(frm);
    },
    custom_discount_amount(frm) {
        calculate_pending_balance(frm);
    },
    total_amount(frm) {
        calculate_pending_balance(frm);
    },

    after_save(frm) {
        console.log("🔍 After save triggered");
        if (frm.doc.custom_workflow_status === "Pending") {
            create_government_purchase_invoice(frm);
        }
        // checkChildTableEntries(frm);
    },
});

// ---------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------
function set_custom_candidate_query(frm) {
    frm.set_query("custom_candidate", function () {
        return { filters: { customer: frm.doc.customer, docstatus: 1 } };
    });
}

function calculate_pending_balance(frm) {
    let total = flt(frm.doc.total_amount);
    let disc = flt(frm.doc.custom_discount_amount);
    let adv = flt(frm.doc.advance_payment);
    let pending = Math.max(0, total - disc - adv);
    frm.set_value("pending_balance", pending);
}

function update_total_amount(frm) {
    let total = 0;
    (frm.doc.service_package || []).forEach((r) => (total += flt(r.amount)));
    frm.set_value("total_amount", total);
    calculate_pending_balance(frm);
}

function calculate_customer_discount(frm) {
    if (!frm.doc.customer || !frm.doc.service_package?.length) {
        frm.set_value("custom_discount_amount", 0);
        calculate_pending_balance(frm);
        return;
    }

    let items = frm.doc.service_package.map((i) => ({ service_package_item: i.service_package_item }));

    frappe.call({
        method: "alhabbai.alhabbai.doctype.job_registration.job_registration.get_customer_discount_for_items",
        args: { customer: frm.doc.customer, service_items: JSON.stringify(items) },
        callback(r) {
            if (r.message) {
                frm.set_value("custom_discount_amount", r.message.total_discount || 0);
                calculate_pending_balance(frm);
            }
        },
    });
}

function checkChildTableEntries(frm) {
    const hasDocs = frm.doc.table_tujy && frm.doc.table_tujy.length > 0;
    if (frm.doc.docstatus === 0) {
        frm.set_value("custom_workflow_status", hasDocs ? "Pending" : "Draft");
    }
}

function create_government_purchase_invoice(frm, amount = null) {
    frappe.db
        .get_value("Purchase Invoice", { custom_job_registration: frm.doc.name, docstatus: ["!=", 2] }, ["name"])
        .then((r) => {
            if (r?.message?.name) {
                frappe.show_alert({
                    message: __("Purchase Invoice {0} already exists", [r.message.name]),
                    indicator: "yellow",
                });
                return;
            }

            frappe.call({
                method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_government_purchase_invoice",
                args: { job_registration: frm.doc.name, amount },
                freeze: true,
                freeze_message: __("Creating Purchase Invoice..."),
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __("Purchase Invoice {0} created successfully", [r.message]),
                            indicator: "green",
                        });
                    }
                    frm.reload_doc();
                },
                error() {
                    frappe.show_alert({
                        message: __("Failed to create Purchase Invoice"),
                        indicator: "red",
                    });
                },
            });
        });
}


// ---------------------------------------------------------------
// Service Package child table - AUTO PRICE FETCH + DISCOUNT UPDATE
// ---------------------------------------------------------------
frappe.ui.form.on("Job Registration Service Item", {
    service_package_item(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.service_package_item) return;

        console.log("🔍 Fetching price for:", row.service_package_item);

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
                    qty: 1,
                },
            },
            freeze: true,
            freeze_message: __("Fetching price..."),
            callback: function (r) {
                if (r.message) {
                    let rate = r.message.price_list_rate || r.message.rate || 0;
                    frappe.model.set_value(cdt, cdn, "amount", rate);
                    console.log("✅ Price fetched:", rate);
                } else {
                    frappe.model.set_value(cdt, cdn, "amount", 0);
                    console.warn("⚠️ No price found for", row.service_package_item);
                }

                // Update totals and discounts
                update_total_amount(frm);
                setTimeout(() => calculate_customer_discount(frm), 300);
            },
        });
    },

    amount(frm) {
        update_total_amount(frm);
        setTimeout(() => calculate_customer_discount(frm), 100);
    },

    service_package_remove(frm) {
        update_total_amount(frm);
        setTimeout(() => calculate_customer_discount(frm), 100);
    },
});
// ---------------------------------------------------------------
// Documents child table - keep workflow synced
// ---------------------------------------------------------------
frappe.ui.form.on("Documents", {
    table_tujy_add(frm) {
        checkChildTableEntries(frm);
        frm.page.set_indicator("Pending", "orange");
        frm.refresh_field("custom_workflow_status");
        // Optional auto-save (uncomment if you want immediate save)
        // frm.save();
    },
    table_tujy_remove(frm) {
        checkChildTableEntries(frm);
        frm.refresh_field("custom_workflow_status");
    }
});
