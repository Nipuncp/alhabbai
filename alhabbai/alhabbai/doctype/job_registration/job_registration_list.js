frappe.listview_settings['Job Registration'] = {
    onload: function(listview) {
        const isReceptionist = frappe.user.has_role('Receptionist');
        const isTypist = frappe.user.has_role('Typist');
        const isVerifier = frappe.user.has_role('Verifier');
        const isAdmin = frappe.user.has_role('Administrator');

        // Skip filters for admin
        if (isAdmin) return;

        let filters = [];

        if (isReceptionist && !isTypist && !isVerifier) {
            // Receptionist: only draft
            filters.push([
                "Job Registration", "custom_workflow_status", "=", "Draft"
            ]);
        } else if (isTypist && !isVerifier) {
            // Typist: draft and pending
            filters.push([
                "Job Registration", "custom_workflow_status", "in", ["Draft", "Pending"]
            ]);
        } else if (isVerifier) {
            // Verifier: pending and submitted
            filters.push([
                "Job Registration", "custom_workflow_status", "in", ["Pending", "Verified"]
            ]);
        }

        if (filters.length) {
            // Apply filters
            listview.filter_area.add(filters);
            
            // Lock the filters
            listview.filter_area.filters.forEach(filter => {
                if (filter[1] === "custom_workflow_status") {
                    filter.lock = true;
                }
            });
        }

        // Hide workflow state filter if not admin
        if (!isAdmin && listview.page.fields_dict.workflow_state) {
            listview.page.fields_dict.workflow_state.$wrapper.hide();
        }
    },
    
    get_indicator: function(doc) {
        const indicators = {
            'Draft': ['Draft', 'blue'],
            'Pending': ['Pending', 'orange'],
            'Verified': ['Verified', 'green']
        };
        
        if (doc.custom_workflow_status && indicators[doc.custom_workflow_status]) {
            const [label, color] = indicators[doc.custom_workflow_status];
            return [__(label), color, "custom_workflow_status,=," + doc.custom_workflow_status];
        }
        
        // Fallback for other statuses
        return [__("Unknown"), "gray", "custom_workflow_status,=," + doc.custom_workflow_status];
    }
};