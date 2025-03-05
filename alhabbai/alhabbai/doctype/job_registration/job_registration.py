# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe.utils import add_days, nowdate

@frappe.whitelist()
def create_sales_order_from_job(job_registration_name):
    """
    Creates a new Sales Order from the given Job Registration record,
    pulling line items from the 'package' child table (Sales Order Item).
    Returns the new Sales Order name.
    """
    # 1. Get the Job Registration doc
    job_reg = frappe.get_doc("Job Registration", job_registration_name)

    # 2. Create a new Sales Order
    so = frappe.new_doc("Sales Order")

    # 3. Set mandatory fields
    #    We now have a real Customer link in Job Registration (fieldname = 'customer')
    if not job_reg.customer:
        frappe.throw("Please set a Customer in the Job Registration before creating a Sales Order.")

    so.customer = job_reg.customer
    so.job_registration = job_reg.name  # Link back to the Job Registration

    # 4. Transfer child table rows from `job_reg.package` -> so.items
    #    Each row in `job_reg.package` references Sales Order Item structure, so fields like item_code, qty, rate, etc.
    if job_reg.package:
        for row in job_reg.package:
            so.append("items", {
                "item_code":       row.item_code,
                "item_name":       row.item_name,
                "description":     row.description,
                "qty":             row.qty or 1,
                "uom":             row.uom or "Nos",
                "conversion_factor": row.conversion_factor or 1,
                "rate":            row.rate or 0,
                "amount":          (row.qty or 1) * (row.rate or 0),
            })

    # 5. Set other mandatory or important fields
    #    For example, Sales Order requires a delivery_date.
    #    You can set it to today + 7 days, or any relevant date for your business flow.
    so.delivery_date = add_days(nowdate(), 7)

    # 6. Insert (save) without submitting automatically
    so.insert(ignore_permissions=True)
    # If you want to auto-submit, uncomment the next line:
    # so.submit()

    return so.name

from frappe.utils import nowdate

from frappe.utils import nowdate, generate_hash

@frappe.whitelist()
def create_government_payment(job_registration_name):
    """
    1) Creates a Purchase Invoice for government fees (in INR).
    2) Creates a Payment Entry in AED (multi-currency), paying from the Prepaid Government Card.
    3) Returns the names of the PI and PE.
    """
    # 1. Get the Job Registration doc
    job_reg = frappe.get_doc("Job Registration", job_registration_name)

    # 2. Create a new Purchase Invoice (assumed in INR)
    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier = "Government Department"
    pi.posting_date = nowdate()

    # Link back to Job Registration (assuming "job_registration" is a custom field on PI)
    pi.job_registration = job_reg.name

    # Add items. Adjust to your scenario or pull from Job Registration child table(s).
    pi.append("items", {
        "item_code": "Visa Fee",
        "qty": 1,
        "rate": 100.0,  # example fee amount in INR
    })

    pi.insert(ignore_permissions=True)
    pi.submit()

    # ------------------------------------------------------------------
    # 3. Create a multi-currency Payment Entry (AED -> INR)
    # ------------------------------------------------------------------
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.posting_date = nowdate()
    pe.party_type = "Supplier"
    pe.party = pi.supplier
    pe.company = pi.company
    pe.mode_of_payment = "Prepaid Government Card"
    pe.paid_from = "1234 - Government Prepaid Card 01 - A"  # account in AED (ensure it's set to Bank/Cash type)
    pe.paid_to = pi.credit_to                               # typically a Payable account in INR
    pe.job_registration = job_reg.name  # custom link field if present on Payment Entry

    # Reference the invoice (in INR)
    pe.append("references", {
        "reference_doctype": "Purchase Invoice",
        "reference_name": pi.name,
        "due_date": pi.due_date,
        "total_amount": pi.grand_total,  # in INR
        "outstanding_amount": pi.outstanding_amount,
        "allocated_amount": pi.outstanding_amount
    })

    # Example exchange rate: 1 AED = 22.5 INR
    exchange_rate = 22.5
    inr_outstanding = pi.outstanding_amount or 0

    # Convert INR outstanding to AED
    aed_to_pay = inr_outstanding / exchange_rate

    # Payment Entry multi-currency fields
    pe.paid_amount = aed_to_pay
    pe.source_exchange_rate = exchange_rate

    # Invoice is in INR (company currency), so received_amount = inr_outstanding
    pe.received_amount = inr_outstanding
    pe.target_exchange_rate = 1.0

    pe.allocate_payment_amount = 1
    pe.reference_no = f"AutoRef-{generate_hash(length=5)}"
    pe.reference_date = nowdate()

    pe.insert(ignore_permissions=True)
    pe.submit()

    return {
        "purchase_invoice": pi.name,
        "payment_entry": pe.name
    }

class JobRegistration(Document):
	pass
