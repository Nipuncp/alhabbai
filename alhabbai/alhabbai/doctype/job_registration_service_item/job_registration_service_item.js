frappe.ui.form.on("Job Registration Service Item", {
    service_package_item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.service_package_item) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Item Price",
                    filters: {
                        item_code: row.service_package_item,
                        price_list: "Standard Selling"  // Change as needed
                    },
                    fieldname: "price_list_rate"
                },
                callback: function(r) {
                    if (r.message) {
                        row.amount = r.message.price_list_rate || 0;
                        frm.refresh_field("service_items");
                        update_total_amount(frm);
                    }
                }
            });
        }
    }
});

function update_total_amount(frm) {
    let total = 0;
    frm.doc.service_items.forEach(row => {
        total += row.amount || 0;
    });
    frm.set_value("total_amount", total);
    frm.refresh_field("total_amount");
}
