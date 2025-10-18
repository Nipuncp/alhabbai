// ---------------------------------------------------------------
// Job Registration Workflow JS (Stable, Clean, No Dirty Form)
// ---------------------------------------------------------------

function set_header_indicator(frm) {
    if (frm.doc.docstatus === 1) {
        frm.page.set_indicator("Verified", "green");
        return;
    }
    if (frm.doc.docstatus === 2) {
        frm.page.set_indicator("Cancelled", "red");
        return;
    }

    const status = frm.doc.custom_workflow_status || "Draft";
    const color = {
        Draft: "blue",
        Pending: "orange",
        Verified: "green",
    }[status] || "gray";

    frm.page.set_indicator(status, color);
}

frappe.ui.form.on("Job Registration", {
    onload(frm) {
        frm.toggle_display("custom_candidate", !!frm.doc.customer);
        if (frm.doc.customer) set_custom_candidate_query(frm);
        set_header_indicator(frm);
    },

    customer(frm) {
        frm.toggle_display("custom_candidate", !!frm.doc.customer);
        frm.set_value("custom_candidate", "");
        if (frm.doc.customer) set_custom_candidate_query(frm);
    },

    refresh(frm) {
        console.log("🔍 Refresh:", frm.doc.custom_workflow_status, frm.doc.docstatus);
        set_header_indicator(frm);

        // ---------------------------------------------------------------
        // Hide Submit for non-Verifier, but keep Save for new docs
        // ---------------------------------------------------------------
        if (
                frm.doc.docstatus === 0 &&
                !frappe.user_roles.includes("Verifier")
            ) {
                // Explicitly hide only the Submit button, not Save
                const submitBtn = frm.page.wrapper.find('[data-label="Submit"]');
                if (submitBtn && submitBtn.length) submitBtn.hide();
            }

        // ---------------------------------------------------------------
        // Verifier button: Verify and Submit
        // ---------------------------------------------------------------
        if (
            frm.doc.docstatus === 0 &&
            frm.doc.custom_workflow_status === "Pending" &&
            frappe.user_roles.includes("Verifier")
        ) {
            frm.page.clear_primary_action();
            frm.add_custom_button(__("Verify"), function () {
                frappe.confirm(
                    __("Are you sure you want to verify and submit this Job Registration?"),
                    function () {
                        frappe.call({
                            method: "alhabbai.alhabbai.doctype.job_registration.job_registration.submit_job_registration",
                            args: { name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Verifying and submitting..."),
                            callback(r) {
                                if (!r.exc) {
                                    frappe.msgprint(
                                        __("✅ Job Registration verified and submitted successfully.")
                                    );
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                );
            }).addClass("btn-primary");
        }

        // ---------------------------------------------------------------
        // Receptionist: Create / View Proforma Invoice
        // ---------------------------------------------------------------
        if (
            !frm.is_new() &&
            frm.doc.custom_workflow_status === "Pending" &&
            frappe.user_roles.includes("Receptionist")
        ) {
            frappe.db
                .get_value(
                    "Sales Order",
                    { custom_job_registration: frm.doc.name, docstatus: ["!=", 2] },
                    "name"
                )
                .then((r) => {
                    if (r && r.message && r.message.name) {
                        frm.add_custom_button(
                            __("View Proforma Invoice"),
                            () => frappe.set_route("Form", "Sales Order", r.message.name),
                            __("Actions")
                        );
                    } else {
                        frm.add_custom_button(
                            __("Create Proforma Invoice"),
                            () => {
                                frappe.call({
                                    method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_sales_order_from_job_registration",
                                    args: { job_registration: frm.doc.name },
                                    freeze: true,
                                    freeze_message: __("Creating Proforma Invoice..."),
                                    callback: function (r) {
                                        if (r.message) {
                                            frappe.msgprint(
                                                __(
                                                    "📄 Proforma Invoice <b>{0}</b> created successfully.",
                                                    [r.message]
                                                )
                                            );
                                            frappe.set_route("Form", "Sales Order", r.message);
                                        }
                                    },
                                });
                            },
                            __("Actions")
                        );
                    }
                });
        }

        // Auto-discount recalculation when customer + service_package exists
        if (frm.doc.customer && frm.doc.service_package?.length > 0) {
            calculate_customer_discount(frm);
        }

        // ✅ Remove Frappe's default "Submit this document to confirm" banner
        frm.page.wrapper.querySelector(".form-message")?.remove();

        // ✅ Reset dirty flag after all visual refreshes
        frm.dirty = false;
        frm.doc.__unsaved = 0;
    },

    validate(frm) {
        update_total_amount(frm);
        checkChildTableEntries(frm);
        calculate_pending_balance(frm);
        set_header_indicator(frm);
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
        set_header_indicator(frm);
    },
});

// ---------------------------------------------------------------
// Helper Functions
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

    // ✅ Update only if changed to avoid dirty form
    if (flt(frm.doc.pending_balance) !== pending) {
        frm.set_value("pending_balance", pending);
    }
}

function update_total_amount(frm) {
    let total = 0;
    (frm.doc.service_package || []).forEach((r) => (total += flt(r.amount)));
    if (flt(frm.doc.total_amount) !== total) {
        frm.set_value("total_amount", total);
    }
    calculate_pending_balance(frm);
}

function calculate_customer_discount(frm) {
    if (!frm.doc.customer || !frm.doc.service_package?.length) {
        if (flt(frm.doc.custom_discount_amount)) {
            frm.set_value("custom_discount_amount", 0);
            calculate_pending_balance(frm);
        }
        return;
    }

    let items = frm.doc.service_package.map((i) => ({
        service_package_item: i.service_package_item,
    }));

    frappe.call({
        method: "alhabbai.alhabbai.doctype.job_registration.job_registration.get_customer_discount_for_items",
        args: { customer: frm.doc.customer, service_items: JSON.stringify(items) },
        callback(r) {
            if (r.message) {
                let new_disc = flt(r.message.total_discount || 0);
                if (flt(frm.doc.custom_discount_amount) !== new_disc) {
                    frm.set_value("custom_discount_amount", new_disc);
                }
                calculate_pending_balance(frm);
            }
        },
    });
}

function checkChildTableEntries(frm) {
    const hasDocs = frm.doc.table_tujy && frm.doc.table_tujy.length > 0;
    if (frm.doc.docstatus === 0) {
        const new_status = hasDocs ? "Pending" : "Draft";
        if (frm.doc.custom_workflow_status !== new_status) {
            frm.set_value("custom_workflow_status", new_status);
        }
    }
}

function create_government_purchase_invoice(frm, amount = null) {
    frappe.db
        .get_value(
            "Purchase Invoice",
            { custom_job_registration: frm.doc.name, docstatus: ["!=", 2] },
            ["name"]
        )
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
// Service Package Child Table
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
// Documents Child Table
// ---------------------------------------------------------------
frappe.ui.form.on("Documents", {
    table_tujy_add(frm) {
        checkChildTableEntries(frm);
        frm.page.set_indicator("Pending", "orange");
        frm.refresh_field("custom_workflow_status");
    },
    table_tujy_remove(frm) {
        checkChildTableEntries(frm);
        frm.refresh_field("custom_workflow_status");
    },
});
