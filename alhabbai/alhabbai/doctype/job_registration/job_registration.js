frappe.ui.form.on("Job Registration", {
    refresh: function(frm) {
        console.log("🔍 DEBUG: Refresh triggered, docstatus =", frm.doc.docstatus);
        // Only show the button if the document is submitted (docstatus 1)
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Sales Order'), function() {
                frappe.call({
                    method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_sales_order_from_job_registration",  // Update this path if needed
                    args: {
                        job_registration: frm.doc.name
                    },
                    callback: function(response) {
                        if (response.message) {
                            frappe.msgprint(__("Sales Order {0} created successfully.", [response.message]));
                            // Optionally, redirect to the Sales Order
                            frappe.set_route("Form", "Sales Order", response.message);
                        }
                    },
                    error: function(error) {
                        frappe.msgprint(__("An error occurred while creating the Sales Order."));
                    }
                });
            });
        }
    },
    onload: function(frm) {
        console.log("🔍 DEBUG: Form Loaded");
        update_total_amount(frm);
    },
    validate: function(frm) {
        console.log("🔍 DEBUG: Running validate() function");
        update_total_amount(frm);
    },
    on_submit: function(frm) {
        console.log("🔍 DEBUG: Job Registration submitted");
        create_government_purchase_invoice(frm);
    },
    advance_payment: function(frm) {
        console.log("🔍 DEBUG: Advance Payment field changed");
        console.log("Advance Payment:", frm.doc.advance_payment);

        let pending_balance = (frm.doc.total_amount || 0) - (frm.doc.advance_payment || 0);
        frm.set_value("pending_balance", pending_balance);

        console.log("Pending Balance:", pending_balance);
        frm.refresh_field("pending_balance");
    }
});

// Trigger whenever a service package row is updated
frappe.ui.form.on("Job Registration Service Item", {
    service_package_item: function(frm, cdt, cdn) {
        console.log("🔍 DEBUG: Service Package Item selected");
        update_total_amount(frm);
    },
    amount: function(frm, cdt, cdn) {
        console.log("🔍 DEBUG: Amount updated");
        update_total_amount(frm);
    },
    service_package_remove: function(frm) { // Trigger on row delete
        console.log("🔍 DEBUG: Service Package Item removed");
        update_total_amount(frm);
    }
});

function update_total_amount(frm) {
    console.log("🔍 DEBUG: Running update_total_amount() function");

    let total = 0;

    // Ensure child table `service_package` exists before iterating
    if (!frm.doc.service_package || !Array.isArray(frm.doc.service_package)) {
        console.warn("⚠️ WARNING: Child table 'service_package' is undefined or not an array!");
        return;
    }

    console.log("📋 DEBUG: service_package data →", frm.doc.service_package);

    // Iterate through each row in the child table
    frm.doc.service_package.forEach(row => {
        console.log("🔹 DEBUG: Processing row:", row);
        console.log("🔹 DEBUG: Service Package Item:", row.service_package_item);
        console.log("🔹 DEBUG: Amount:", row.amount);

        if (row.amount) {
            total += row.amount;
        }
    });

    console.log("✅ DEBUG: Calculated Total Amount:", total);

    frm.set_value("total_amount", total);
    frm.set_value("pending_balance", total - (frm.doc.advance_payment || 0));

    frm.refresh_field("total_amount");
    frm.refresh_field("pending_balance");
}
function create_government_purchase_invoice(frm, government_fee_amount) {
    frappe.call({
        method: "alhabbai.alhabbai.doctype.job_registration.job_registration.create_government_purchase_invoice",
        args: {
            job_registration: frm.doc.name,
            amount: government_fee_amount
        },
        callback: function(response) {
            if (response.message) {
                console.log("✅ DEBUG: Purchase Invoice Created:", response.message);
                frappe.msgprint(`Purchase Invoice ${response.message} created for Government Fees.`);
            } else {
                console.error("❌ ERROR: Failed to create Purchase Invoice");
            }
        }
    });
}