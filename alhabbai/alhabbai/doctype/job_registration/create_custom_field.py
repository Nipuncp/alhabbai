import frappe

def execute():
    try:
        # Check if field already exists
        if not frappe.get_meta("Purchase Invoice").has_field("custom_job_registration"):
            doc = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Purchase Invoice",
                "fieldname": "custom_job_registration",
                "label": "Job Registration",
                "fieldtype": "Link",
                "options": "Job Registration",
                "insert_after": "amended_from",
                "unique": 0,
                "in_list_view": 1,
                "in_standard_filter": 1
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            print("Custom field created successfully")
        else:
            print("Custom field already exists")
    except Exception as e:
        print(f"Error: {str(e)}")