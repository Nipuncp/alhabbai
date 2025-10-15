frappe.listview_settings['Job Registration'] = {
    add_fields: ["custom_workflow_status"],

    onload: function (listview) {
        if (listview._custom_filter_applied) return;
        listview._custom_filter_applied = true;

        const isReceptionist = frappe.user.has_role('Receptionist');
        const isTypist = frappe.user.has_role('Typist');
        const isVerifier = frappe.user.has_role('Verifier');
        const isAdmin = frappe.user.has_role('Administrator');

        if (isAdmin) return;

        let filters = [];

        if (isReceptionist && !isTypist && !isVerifier) {
            filters.push(["Job Registration", "custom_workflow_status", "=", "Draft"]);
        } else if (isTypist && !isVerifier) {
            filters.push(["Job Registration", "custom_workflow_status", "in", ["Draft", "Pending"]]);
        } else if (isVerifier) {
            filters.push(["Job Registration", "custom_workflow_status", "in", ["Pending", "Verified"]]);
        }

        if (filters.length) {
            listview.filter_area.add(filters);
            listview.refresh();

            // Lock filters
            listview.filter_area.filters.forEach(f => {
                if (f[1] === "custom_workflow_status") f.lock = true;
            });
        }

        // Hide built-in workflow filter for non-admins
        if (!isAdmin && listview.page.fields_dict.workflow_state) {
            listview.page.fields_dict.workflow_state.$wrapper.hide();
        }
    },

    get_indicator: function (doc) {
    if (!doc.custom_workflow_status) {
        return ["Unknown", "gray", "custom_workflow_status,=,"];
    }

    switch (doc.custom_workflow_status) {
        case "Draft":
            return ["Draft", "red", "custom_workflow_status,=,Draft"];
        case "Pending":
            return ["Pending", "orange", "custom_workflow_status,=,Pending"];
        case "Verified":
            return ["Verified", "green", "custom_workflow_status,=,Verified"];
        default:
            return [doc.custom_workflow_status, "gray", "custom_workflow_status,=," + doc.custom_workflow_status];
    }
}
};
// ---------------------------------------------------------------
// Fix default "Status" column to use custom_workflow_status
// ---------------------------------------------------------------
frappe.listview_settings["Job Registration"].onload_post_render = function(listview) {
    // Hide the system-generated Status column (based on docstatus)
    listview.columns = listview.columns.filter(col => col.df.fieldname !== "status");
};
