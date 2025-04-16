frappe.ui.form.on("Job Registration Service Item", {
    service_package_item: function(frm, cdt, cdn) {
        console.log("🔍 DEBUG: Service Package Item selected");
        var row = locals[cdt][cdn];
        
        if (row.service_package_item) {
            console.log("🔍 DEBUG: Fetching price for item:", row.service_package_item);
            
            // Use erpnext's get_item_details method which is more reliable
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
                    console.log("📋 DEBUG: get_item_details response:", r);
                    
                    if (r.message) {
                        // If we got a valid response, use the price_list_rate
                        if (r.message.price_list_rate !== undefined) {
                            console.log("✅ DEBUG: Found price:", r.message.price_list_rate);
                            frappe.model.set_value(cdt, cdn, 'amount', r.message.price_list_rate);
                        } else if (r.message.rate !== undefined) {
                            console.log("✅ DEBUG: Using rate:", r.message.rate);
                            frappe.model.set_value(cdt, cdn, 'amount', r.message.rate);
                        } else {
                            console.log("⚠️ DEBUG: No price information found, using 0");
                            frappe.model.set_value(cdt, cdn, 'amount', 0);
                        }
                    } else {
                        console.error("❌ ERROR: No response from get_item_details");
                        frappe.model.set_value(cdt, cdn, 'amount', 0);
                    }
                    
                    update_total_amount(frm);
                }
            });
        }
    },
    amount: function(frm, cdt, cdn) {
        console.log("🔍 DEBUG: Amount updated");
        update_total_amount(frm);
    },
    service_package_remove: function(frm) {
        console.log("🔍 DEBUG: Service Package Item removed");
        update_total_amount(frm);
    }
});