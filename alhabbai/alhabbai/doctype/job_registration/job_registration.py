# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class JobRegistration(Document):
	pass



@frappe.whitelist()
def create_government_purchase_invoice(job_registration, amount=100):
    #Function to create purchase invoice and make payment from prepaid card

    try:
        # Verify that the Job Registration exists
        if not frappe.db.exists("Job Registration", job_registration):
            frappe.msgprint(f"Job Registration {job_registration} not found")
            return "Error: Job Registration not found"
        
        frappe.logger().info(f"Found job registration: {job_registration}")
        
        # Create a new Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = "Government"
        pi.posting_date = frappe.utils.today()
        pi.due_date = frappe.utils.today()
        
        # Add an item for Government Fees
        pi.append("items", {
            "item_code": "Government Fees",
            "qty": 1,
            "rate": amount,
            "amount": amount,
            "expense_account": "Government Charges - AH"
        })
        
        # Insert the invoice (which calculates totals, etc.)
        pi.insert()
        
        # Update fields to mark the invoice as paid
        pi.is_paid = 1
        pi.mode_of_payment = "Government Prepaid Card"
        pi.cash_bank_account = "Prepaid Card 1 - AH"
        # Set paid_amount equal to the total (assuming full payment)
        pi.paid_amount = pi.grand_total
        # Zero out outstanding amount
        pi.outstanding_amount = 0
        
        # Save changes and submit if required by your workflow
        pi.save()
        
        frappe.msgprint(f"Created and marked as paid Purchase Invoice: {pi.name}")
        return pi.name
        
    except Exception as e:
        error_msg = f"Error in create_government_purchase_invoice: {str(e)}"
        frappe.log_error(error_msg)
        frappe.msgprint(error_msg)
        return f"Error: {str(e)}"

    
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

