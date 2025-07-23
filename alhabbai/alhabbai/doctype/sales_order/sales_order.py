# File: apps/alhabbai/alhabbai/doctype/sales_order/sales_order.py
# Sales Order controller extension for payment collection

import frappe
from frappe import _
from frappe.utils import flt, today, now
from erpnext.accounts.utils import get_account_currency

@frappe.whitelist()
def create_advance_payment_entry(sales_order, payment_amount, mode_of_payment, payment_account, reference_no=""):
    """
    Create Payment Entry for advance payment against Sales Order
    This is the main function called by the JavaScript
    """
    try:
        # Get Sales Order document
        so = frappe.get_doc("Sales Order", sales_order)
        
        # Validate payment amount
        payment_amount = flt(payment_amount)
        if payment_amount <= 0:
            frappe.throw(_("Payment amount must be greater than zero"))
        
        # Check if payment doesn't exceed outstanding
        outstanding = flt(so.grand_total) - flt(so.advance_paid)
        if payment_amount > outstanding:
            frappe.throw(_("Payment amount cannot exceed outstanding amount of {0}").format(outstanding))
        
        # Create Payment Entry
        pe = frappe.new_doc("Payment Entry")
        
        # Basic details
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = so.customer
        pe.posting_date = today()
        pe.company = so.company
        
        # Payment details
        pe.mode_of_payment = mode_of_payment
        pe.paid_amount = payment_amount
        pe.received_amount = payment_amount
        pe.paid_from = get_party_account("Customer", so.customer, so.company)
        pe.paid_to = payment_account
        
        # Reference details
        pe.reference_no = reference_no
        pe.reference_date = today()
        
        # Set currency details
        company_currency = frappe.get_cached_value("Company", so.company, "default_currency")
        pe.paid_from_account_currency = company_currency
        pe.paid_to_account_currency = get_account_currency(payment_account)
        
        # Add reference to Sales Order
        pe.append("references", {
            "reference_doctype": "Sales Order",
            "reference_name": so.name,
            "allocated_amount": payment_amount
        })
        
        # Insert and submit the payment entry
        pe.insert(ignore_permissions=True)
        pe.submit()
        
        # Update Sales Order with payment details
        update_sales_order_payment_status(so, pe, payment_amount)
        
        frappe.msgprint(_("Payment Entry {0} created successfully").format(pe.name))
        return pe.name
        
    except Exception as e:
        error_msg = f"Error creating payment entry: {str(e)}"
        frappe.log_error(error_msg)
        frappe.throw(_(error_msg))

def update_sales_order_payment_status(sales_order, payment_entry, payment_amount):
    """
    Update Sales Order with payment information
    """
    try:
        # Update Sales Order fields using db_set (works even after submit)
        sales_order.db_set("custom_payment_entry", payment_entry.name)
        sales_order.db_set("advance_paid", flt(sales_order.advance_paid) + flt(payment_amount))
        
        # Calculate outstanding amount
        outstanding = flt(sales_order.grand_total) - flt(sales_order.advance_paid)
        sales_order.db_set("custom_outstanding_amount", outstanding)
        
        # Update payment status
        if outstanding <= 0:
            payment_status = "Fully Paid"
        elif flt(sales_order.advance_paid) > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"
        
        sales_order.db_set("custom_payment_status", payment_status)
        
        # Clear payment collection fields for next payment
        sales_order.db_set("custom_advance_payment_amount", 0)
        sales_order.db_set("custom_payment_reference", "")
        
        frappe.db.commit()
        
        frappe.msgprint(_("Sales Order payment status updated successfully"))
        
    except Exception as e:
        error_msg = f"Error updating sales order payment status: {str(e)}"
        frappe.log_error(error_msg)

def get_party_account(party_type, party, company):
    """
    Get party account for payment entry
    """
    if party_type == "Customer":
        return frappe.get_cached_value("Company", company, "default_receivable_account")
    elif party_type == "Supplier":
        return frappe.get_cached_value("Company", company, "default_payable_account")
    return None

@frappe.whitelist()
def cancel_payment_entry(sales_order, payment_entry):
    """
    Cancel payment entry and update sales order
    """
    try:
        # Cancel payment entry
        pe = frappe.get_doc("Payment Entry", payment_entry)
        if pe.docstatus == 1:
            pe.cancel()
        
        # Update sales order
        so = frappe.get_doc("Sales Order", sales_order)
        
        # Find the amount that was paid
        paid_amount = 0
        for ref in pe.references:
            if ref.reference_doctype == "Sales Order" and ref.reference_name == sales_order:
                paid_amount = ref.allocated_amount
                break
        
        # Update sales order fields
        so.db_set("custom_payment_entry", "")
        so.db_set("advance_paid", flt(so.advance_paid) - flt(paid_amount))
        
        # Recalculate outstanding and status
        outstanding = flt(so.grand_total) - flt(so.advance_paid)
        so.db_set("custom_outstanding_amount", outstanding)
        
        if flt(so.advance_paid) <= 0:
            so.db_set("custom_payment_status", "Pending")
        else:
            so.db_set("custom_payment_status", "Partially Paid")
        
        frappe.db.commit()
        return True
        
    except Exception as e:
        error_msg = f"Error canceling payment entry: {str(e)}"
        frappe.log_error(error_msg)
        frappe.throw(_(error_msg))

# Hooks for automatic calculation
def sales_order_on_update_after_submit(doc, method):
    """
    Hook to run after Sales Order is updated after submit
    """
    calculate_outstanding_amount(doc)

def sales_order_before_save(doc, method):
    """
    Hook to run before Sales Order is saved
    """
    calculate_outstanding_amount(doc)

def calculate_outstanding_amount(doc):
    """
    Calculate and set outstanding amount in Sales Order
    """
    if hasattr(doc, 'grand_total') and hasattr(doc, 'advance_paid'):
        outstanding = flt(doc.grand_total) - flt(doc.advance_paid)
        outstanding = max(0, outstanding)
        
        # Set outstanding amount
        if hasattr(doc, 'custom_outstanding_amount'):
            doc.custom_outstanding_amount = outstanding
        
        # Set payment status
        if hasattr(doc, 'custom_payment_status'):
            if outstanding <= 0:
                doc.custom_payment_status = "Fully Paid"
            elif flt(doc.advance_paid) > 0:
                doc.custom_payment_status = "Partially Paid"
            else:
                doc.custom_payment_status = "Pending"

# Test function for debugging
@frappe.whitelist()
def test_payment_collection():
    """
    Test function to verify payment collection setup
    """
    try:
        # Check if required doctypes exist
        required_doctypes = ["Sales Order", "Payment Entry", "Mode of Payment", "Account"]
        missing_doctypes = []
        
        for dt in required_doctypes:
            if not frappe.db.exists("DocType", dt):
                missing_doctypes.append(dt)
        
        if missing_doctypes:
            return {"status": "error", "message": f"Missing DocTypes: {', '.join(missing_doctypes)}"}
        
        # Check if custom fields exist
        custom_fields = [
            "Sales Order-custom_advance_payment_amount",
            "Sales Order-custom_mode_of_payment",
            "Sales Order-custom_payment_account",
            "Sales Order-custom_outstanding_amount",
            "Sales Order-custom_payment_status"
        ]
        
        missing_fields = []
        for field in custom_fields:
            if not frappe.db.exists("Custom Field", field):
                missing_fields.append(field)
        
        if missing_fields:
            return {"status": "warning", "message": f"Missing custom fields: {', '.join(missing_fields)}"}
        
        return {"status": "success", "message": "Payment collection setup is complete and ready to use!"}
        
    except Exception as e:
        return {"status": "error", "message": f"Error during test: {str(e)}"}