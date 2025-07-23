// Fixed Sales Order Payment Collection Script
// File: apps/alhabbai/alhabbai/public/js/sales_order.js

console.log("🔍 Loading fixed Sales Order script...");

frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        console.log("🔍 Sales Order refresh - docstatus:", frm.doc.docstatus);
        
        // Only show payment collection for submitted documents
        if (frm.doc.docstatus === 1) {
            // Calculate outstanding but DON'T update fields automatically
            calculate_and_display_outstanding(frm);
            
            // Add payment collection button if there's outstanding amount
            if (frm.doc.custom_outstanding_amount > 0) {
                frm.add_custom_button(__('Collect Payment'), function() {
                    collect_advance_payment(frm);
                }, __('Payment'));
            }
            
            // Add button to view payment entry if exists
            if (frm.doc.custom_payment_entry) {
                frm.add_custom_button(__('View Payment Entry'), function() {
                    frappe.set_route("Form", "Payment Entry", frm.doc.custom_payment_entry);
                }, __('Payment'));
            }
        }
        
        // Set query for payment account
        frm.set_query("custom_payment_account", function() {
            return {
                filters: {
                    "company": frm.doc.company,
                    "account_type": ["in", ["Cash", "Bank"]],
                    "is_group": 0,
                    "disabled": 0
                }
            };
        });
    },
    
    // Only handle field changes for DRAFT documents
    custom_advance_payment_amount: function(frm) {
        if (frm.doc.docstatus === 0) {  // Only for draft documents
            calculate_outstanding_amount_draft(frm);
        }
    },
    
    grand_total: function(frm) {
        if (frm.doc.docstatus === 0) {  // Only for draft documents
            calculate_outstanding_amount_draft(frm);
        }
    },
    
    custom_mode_of_payment: function(frm) {
        if (frm.doc.custom_mode_of_payment) {
            // Auto-set payment account based on mode of payment
            frappe.call({
                method: "alhabbai.alhabbai.utils.get_default_payment_account",
                args: {
                    mode_of_payment: frm.doc.custom_mode_of_payment,
                    company: frm.doc.company
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("custom_payment_account", r.message);
                    }
                }
            });
        }
    },
    
    custom_collect_payment_button: function(frm) {
        if (frm.doc.docstatus === 1) {
            collect_advance_payment(frm);
        }
    }
});

// Calculate outstanding for DRAFT documents (can modify fields)
function calculate_outstanding_amount_draft(frm) {
    if (frm.doc.docstatus !== 0) return; // Only for draft documents
    
    try {
        let totalAmount = frm.doc.grand_total || 0;
        let advancePaid = frm.doc.advance_paid || 0;
        let currentPayment = frm.doc.custom_advance_payment_amount || 0;
        
        let outstanding = Math.max(0, totalAmount - advancePaid - currentPayment);
        
        frm.set_value("custom_outstanding_amount", outstanding);
        
        // Update payment status
        let totalPaid = advancePaid + currentPayment;
        let status = "Pending";
        
        if (totalPaid >= totalAmount) {
            status = "Fully Paid";
        } else if (totalPaid > 0) {
            status = "Partially Paid";
        }
        
        frm.set_value("custom_payment_status", status);
        
        console.log("🔍 Draft calculation - Outstanding:", outstanding, "Status:", status);
    } catch (error) {
        console.error("🔍 Error in draft calculation:", error);
    }
}

// Calculate and DISPLAY outstanding for SUBMITTED documents (read-only)
function calculate_and_display_outstanding(frm) {
    if (frm.doc.docstatus !== 1) return; // Only for submitted documents
    
    try {
        let totalAmount = frm.doc.grand_total || 0;
        let advancePaid = frm.doc.advance_paid || 0;
        let currentPayment = frm.doc.custom_advance_payment_amount || 0;
        
        let outstanding = Math.max(0, totalAmount - advancePaid - currentPayment);
        
        // DON'T modify the document, just log for debugging
        console.log("🔍 Submitted doc calculation:", {
            totalAmount,
            advancePaid,
            currentPayment,
            outstanding,
            storedOutstanding: frm.doc.custom_outstanding_amount,
            status: frm.doc.custom_payment_status
        });
        
        // If there's a discrepancy, show a message but don't modify
        if (Math.abs(outstanding - (frm.doc.custom_outstanding_amount || 0)) > 0.01) {
            console.log("🔍 Outstanding amount needs update:", outstanding, "vs", frm.doc.custom_outstanding_amount);
        }
        
    } catch (error) {
        console.error("🔍 Error in submitted calculation:", error);
    }
}

// Payment collection function
function collect_advance_payment(frm) {
    if (frm.doc.docstatus !== 1) {
        frappe.msgprint(__("Please submit the Sales Order first"));
        return;
    }
    
    console.log("🔍 Collecting payment for submitted document...");
    
    // Basic validation
    if (!frm.doc.custom_advance_payment_amount || frm.doc.custom_advance_payment_amount <= 0) {
        frappe.msgprint(__("Please enter advance payment amount"));
        return;
    }
    
    if (!frm.doc.custom_mode_of_payment) {
        frappe.msgprint(__("Please select mode of payment"));
        return;
    }
    
    if (!frm.doc.custom_payment_account) {
        frappe.msgprint(__("Please select payment account"));
        return;
    }
    
    // Confirm and process
    frappe.confirm(
        __("Collect advance payment of {0}?", [format_currency(frm.doc.custom_advance_payment_amount)]),
        function() {
            frappe.call({
                method: "alhabbai.alhabbai.doctype.sales_order.sales_order.create_advance_payment_entry",
                args: {
                    sales_order: frm.doc.name,
                    payment_amount: frm.doc.custom_advance_payment_amount,
                    mode_of_payment: frm.doc.custom_mode_of_payment,
                    payment_account: frm.doc.custom_payment_account,
                    reference_no: frm.doc.custom_payment_reference || ""
                },
                freeze: true,
                freeze_message: __("Creating Payment Entry..."),
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: __("Success"),
                            message: __("Payment Entry {0} created successfully", [r.message]),
                            indicator: "green"
                        });
                        
                        // Reload the form to get updated values from server
                        frm.reload_doc();
                    }
                },
                error: function(r) {
                    console.error("🔍 Payment error:", r);
                    frappe.msgprint({
                        title: __("Error"),
                        message: __("Failed to create payment entry"),
                        indicator: "red"
                    });
                }
            });
        }
    );
}

// Function to manually refresh payment status (if needed)
function refresh_payment_status(frm) {
    if (frm.doc.docstatus === 1) {
        frappe.call({
            method: "alhabbai.alhabbai.utils.get_sales_order_payment_summary",
            args: {
                sales_order: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    console.log("🔍 Payment summary from server:", r.message);
                    
                    // Show current status without modifying the form
                    frappe.show_alert({
                        message: `Outstanding: ${format_currency(r.message.outstanding)}, Status: ${r.message.payment_status}`,
                        indicator: r.message.outstanding > 0 ? 'orange' : 'green'
                    });
                }
            }
        });
    }
}

console.log("✅ Fixed Sales Order script loaded successfully");



// // Sales Order Payment Collection Client Script
// // File: apps/alhabbai/alhabbai/public/js/sales_order.js

// frappe.ui.form.on('Sales Order', {
//     refresh: function(frm) {
//         console.log("🔍 Sales Order payment collection script loaded");
        
//         // Calculate outstanding amount on refresh
//         calculate_outstanding_amount(frm);
        
//         // Set filter for Payment Account field
//         frm.set_query("custom_payment_account", function() {
//             return {
//                 filters: {
//                     "company": frm.doc.company,
//                     "account_type": ["in", ["Cash", "Bank"]],
//                     "is_group": 0,
//                     "disabled": 0
//                 }
//             };
//         });
        
//         // Add custom button for payment collection (only for submitted docs with outstanding)
//         if (frm.doc.docstatus === 1 && frm.doc.custom_outstanding_amount > 0) {
//             frm.add_custom_button(__('Collect Payment'), function() {
//                 collect_advance_payment(frm);
//             }, __('Payment'));
            
//             // Add button to view payment entry if exists
//             if (frm.doc.custom_payment_entry) {
//                 frm.add_custom_button(__('View Payment Entry'), function() {
//                     frappe.set_route("Form", "Payment Entry", frm.doc.custom_payment_entry);
//                 }, __('Payment'));
//             }
//         }
        
//         // Toggle payment field visibility
//         toggle_payment_fields(frm);
//     },
    
//     grand_total: function(frm) {
//         calculate_outstanding_amount(frm);
//     },
    
//     custom_advance_payment_amount: function(frm) {
//         calculate_outstanding_amount(frm);
//         validate_advance_amount(frm);
//     },
    
//     custom_mode_of_payment: function(frm) {
//         if (frm.doc.custom_mode_of_payment) {
//             // Auto-set payment account based on mode of payment
//             frappe.call({
//                 method: "alhabbai.alhabbai.utils.get_default_payment_account",
//                 args: {
//                     mode_of_payment: frm.doc.custom_mode_of_payment,
//                     company: frm.doc.company
//                 },
//                 callback: function(r) {
//                     if (r.message) {
//                         frm.set_value("custom_payment_account", r.message);
//                     }
//                 }
//             });
//         }
//     },
    
//     custom_collect_payment_button: function(frm) {
//         collect_advance_payment(frm);
//     }
// });

// // Calculate outstanding amount in real-time
// function calculate_outstanding_amount(frm) {
//     let totalAmount = frm.doc.grand_total || 0;
//     let advancePaid = frm.doc.advance_paid || 0;
//     let currentPayment = frm.doc.custom_advance_payment_amount || 0;
    
//     let outstanding = totalAmount - advancePaid - currentPayment;
//     outstanding = Math.max(0, outstanding);
    
//     console.log("🔍 Outstanding calculation:", {
//         totalAmount,
//         advancePaid,
//         currentPayment,
//         outstanding
//     });
    
//     frm.set_value("custom_outstanding_amount", outstanding);
    
//     // Update payment status
//     update_payment_status(frm, totalAmount, advancePaid + currentPayment);
// }

// // Update payment status based on amounts
// function update_payment_status(frm, total, paid) {
//     let status = "Pending";
    
//     if (paid >= total) {
//         status = "Fully Paid";
//     } else if (paid > 0) {
//         status = "Partially Paid";
//     }
    
//     frm.set_value("custom_payment_status", status);
// }

// // Validate advance payment amount
// function validate_advance_amount(frm) {
//     let advance_amount = frm.doc.custom_advance_payment_amount || 0;
//     let grand_total = frm.doc.grand_total || 0;
//     let outstanding = frm.doc.custom_outstanding_amount || 0;
    
//     if (advance_amount > grand_total) {
//         frappe.msgprint(__("Advance payment cannot exceed grand total"));
//         frm.set_value("custom_advance_payment_amount", 0);
//         return;
//     }
    
//     if (advance_amount > outstanding + advance_amount) {
//         frappe.msgprint(__("Advance payment cannot exceed outstanding amount"));
//         frm.set_value("custom_advance_payment_amount", outstanding);
//     }
// }

// // Toggle payment fields visibility
// function toggle_payment_fields(frm) {
//     let show_collection_fields = frm.doc.docstatus === 1;
    
//     frm.toggle_display("payment_collection_section", show_collection_fields);
//     frm.toggle_display("payment_status_section", true); // Always show status
// }

// // Main function to collect advance payment
// function collect_advance_payment(frm) {
//     console.log("🔍 Collecting advance payment...");
    
//     // Validate required fields
//     if (!frm.doc.custom_advance_payment_amount || frm.doc.custom_advance_payment_amount <= 0) {
//         frappe.msgprint(__("Please enter advance payment amount"));
//         return;
//     }
    
//     if (!frm.doc.custom_mode_of_payment) {
//         frappe.msgprint(__("Please select mode of payment"));
//         return;
//     }
    
//     if (!frm.doc.custom_payment_account) {
//         frappe.msgprint(__("Please select payment account"));
//         return;
//     }
    
//     // Confirm payment collection
//     frappe.confirm(
//         __("Collect advance payment of {0}?", [format_currency(frm.doc.custom_advance_payment_amount)]),
//         function() {
//             // Create payment entry
//             frappe.call({
//                 method: "alhabbai.alhabbai.doctype.sales_order.sales_order.create_advance_payment_entry",
//                 args: {
//                     sales_order: frm.doc.name,
//                     payment_amount: frm.doc.custom_advance_payment_amount,
//                     mode_of_payment: frm.doc.custom_mode_of_payment,
//                     payment_account: frm.doc.custom_payment_account,
//                     reference_no: frm.doc.custom_payment_reference || ""
//                 },
//                 freeze: true,
//                 freeze_message: __("Creating Payment Entry..."),
//                 callback: function(r) {
//                     if (r.message) {
//                         frappe.msgprint({
//                             title: __("Success"),
//                             message: __("Payment Entry {0} created successfully", [r.message]),
//                             indicator: "green"
//                         });
                        
//                         // Refresh the form to show updated values
//                         frm.reload_doc();
//                     }
//                 },
//                 error: function(r) {
//                     console.error("🔍 Payment creation error:", r);
//                     frappe.msgprint({
//                         title: __("Error"),
//                         message: __("Failed to create payment entry. Please check console for details."),
//                         indicator: "red"
//                     });
//                 }
//             });
//         }
//     );
// }

// // Quick payment dialog (alternative to form fields)
// function show_quick_payment_dialog(frm) {
//     let dialog = new frappe.ui.Dialog({
//         title: __("Collect Advance Payment"),
//         fields: [
//             {
//                 fieldname: "payment_amount",
//                 label: __("Payment Amount"),
//                 fieldtype: "Currency",
//                 reqd: 1,
//                 default: frm.doc.custom_outstanding_amount
//             },
//             {
//                 fieldname: "mode_of_payment",
//                 label: __("Mode of Payment"),
//                 fieldtype: "Link",
//                 options: "Mode of Payment",
//                 reqd: 1,
//                 default: frm.doc.custom_mode_of_payment
//             },
//             {
//                 fieldname: "payment_account",
//                 label: __("Payment Account"),
//                 fieldtype: "Link",
//                 options: "Account",
//                 reqd: 1,
//                 get_query: function() {
//                     return {
//                         filters: {
//                             account_type: ["in", ["Cash", "Bank"]],
//                             company: frm.doc.company,
//                             is_group: 0
//                         }
//                     };
//                 }
//             },
//             {
//                 fieldname: "reference_no",
//                 label: __("Reference No"),
//                 fieldtype: "Data"
//             }
//         ],
//         primary_action_label: __("Collect Payment"),
//         primary_action: function(values) {
//             frappe.call({
//                 method: "alhabbai.alhabbai.doctype.sales_order.sales_order.create_advance_payment_entry",
//                 args: {
//                     sales_order: frm.doc.name,
//                     payment_amount: values.payment_amount,
//                     mode_of_payment: values.mode_of_payment,
//                     payment_account: values.payment_account,
//                     reference_no: values.reference_no || ""
//                 },
//                 freeze: true,
//                 callback: function(r) {
//                     if (r.message) {
//                         dialog.hide();
//                         frappe.msgprint(__("Payment collected successfully"));
//                         frm.reload_doc();
//                     }
//                 }
//             });
//         }
//     });
    
//     dialog.show();
// }

// console.log("✅ Sales Order payment collection script loaded successfully");