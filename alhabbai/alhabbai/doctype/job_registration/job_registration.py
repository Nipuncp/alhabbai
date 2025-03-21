# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class JobRegistration(Document):
	pass



@frappe.whitelist()
def create_government_purchase_invoice(job_registration, amount=100):
    # print("DEBUG: create_government_purchase_invoice called with job_registration: {} and amount: {}".format(job_registration, amount))
    frappe.logger().info("create_government_purchase_invoice called with job_registration: {} and amount: {}".format(job_registration, amount))
    # Ensure amount is provided
    if amount is None:
        frappe.throw("Amount must be provided to create a Purchase Invoice for Government Fees.")
    
    try:
        # Create Purchase Invoice (Draft for now)
        pi = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "supplier": "Government",
            "posting_date": frappe.utils.today(),
            "due_date": frappe.utils.today(),
            "items": [{
                "item_code": "Government Fees",
                "qty": 1,
                "rate": amount,
                "amount": amount,
                "expense_account": "Government Charges - AH"  # Make sure this account exists
            }],
            "total": amount,
            "grand_total": amount,
            "outstanding_amount": 0,
            "is_paid": 1,  # Mark as paid
            # Add the cash_bank_account field to resolve the error
            "cash_bank_account": "Prepaid Card 1 - AH",  # Ensure this account exists in your Chart of Accounts
            "payments": [{
                "mode_of_payment": "Government Prepaid Card",
                "account": "Prepaid Card 1 - AH",  # Ensure this account exists in your Chart of Accounts
                "amount": amount
            }]
        })
        
        # print("DEBUG: Inserting Purchase Invoice draft...")
        frappe.logger().info("DEBUG: Inserting Purchase Invoice draft...")
        frappe.logger().info("DEBUG: Draft Purchase Invoice {} created.".format(pi.name))
        # print("DEBUG: Draft Purchase Invoice {} created.".format(pi.name))
        
        # Uncomment the next line to auto-submit when you are ready:
        # pi.submit()  
        # print("DEBUG: Draft Purchase Invoice {} submitted.".format(pi.name))

        return pi.name

    except Exception as e:
        frappe.log_error("Failed to create Purchase Invoice: {}".format(str(e)), "Job Registration Automation")
        # print("DEBUG: Error creating Purchase Invoice: {}".format(str(e)))
        return None
    
@frappe.whitelist()
def create_sales_order_from_job_registration(job_registration):
    """
    Create a Sales Order from a Job Registration document by using each entry in the
    'service_package' child table as an item in the Sales Order.
    
    The function:
    - Loads the Job Registration document.
    - Iterates over the child table entries (each containing a service_package_item and amount).
    - Creates a Sales Order with the customer from the Job Registration.
    - Adds each service package item to the Sales Order items list.
    - Computes the total amount from the child items.
    """
    # Retrieve the Job Registration document
    jr = frappe.get_doc("Job Registration", job_registration)
    if not jr:
        frappe.throw("Job Registration not found.")
    
    # Ensure the Job Registration has a customer defined
    if not jr.customer:
        frappe.throw("Customer is not specified in the Job Registration.")

    # Build the items list for the Sales Order from the service_package child table
    items = []
    total_amount = 0
    for child in jr.service_package:
        # Each child row uses the service_package_item as the item code.
        item_entry = {
            "item_code": child.service_package_item,
            "qty": 1,             # You can adjust quantity if needed
            "rate": child.amount, # Using the amount as the rate
            "amount": child.amount
        }
        items.append(item_entry)
        total_amount += child.amount

    # Create the Sales Order document using the customer from Job Registration
    so = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": jr.customer,
        "transaction_date": frappe.utils.today(),
        "delivery_date": frappe.utils.today(),
        "items": items,
        "total": total_amount,
        "grand_total": total_amount,
        # Optionally, link back to the Job Registration
        "job_registration": jr.name
    })
    
    # Insert the Sales Order (draft status)
    so.insert(ignore_permissions=True)
    frappe.msgprint("Sales Order {} created successfully.".format(so.name))
    
    return so.name

