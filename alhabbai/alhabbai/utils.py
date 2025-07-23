# File: apps/alhabbai/alhabbai/utils.py
# Backend utility methods for Sales Order payment collection

import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def get_default_payment_account(mode_of_payment, company):
    """
    Get default payment account for mode of payment
    Called by JavaScript when user selects payment method
    """
    try:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment, "company": company},
            "default_account"
        )
        return account
    except Exception as e:
        frappe.log_error(f"Error getting default payment account: {str(e)}")
        return None

@frappe.whitelist()
def get_payment_accounts(doctype, txt, searchfield, start, page_len, filters):
    """
    Get query for payment accounts - only Cash and Bank accounts
    Used for filtering account dropdown
    """
    company = filters.get("company") or frappe.defaults.get_user_default("Company")
    
    return frappe.db.sql("""
        SELECT name, account_name 
        FROM `tabAccount` 
        WHERE company = %s 
        AND account_type IN ('Cash', 'Bank')
        AND is_group = 0
        AND disabled = 0
        AND (name LIKE %s OR account_name LIKE %s)
        ORDER BY name
        LIMIT %s OFFSET %s
    """, (company, f"%{txt}%", f"%{txt}%", page_len, start))

@frappe.whitelist()
def get_outstanding_amount(sales_order):
    """
    Get outstanding amount for a sales order
    """
    try:
        so = frappe.get_doc("Sales Order", sales_order)
        outstanding = flt(so.grand_total) - flt(so.advance_paid)
        return max(0, outstanding)
    except Exception as e:
        frappe.log_error(f"Error getting outstanding amount: {str(e)}")
        return 0

@frappe.whitelist()
def validate_payment_amount(sales_order, payment_amount):
    """
    Validate if payment amount is acceptable
    """
    try:
        so = frappe.get_doc("Sales Order", sales_order)
        payment_amount = flt(payment_amount)
        outstanding = flt(so.grand_total) - flt(so.advance_paid)
        
        if payment_amount <= 0:
            return {"valid": False, "message": "Payment amount must be greater than zero"}
        
        if payment_amount > outstanding:
            return {"valid": False, "message": f"Payment amount cannot exceed outstanding amount of {outstanding}"}
        
        return {"valid": True, "message": "Payment amount is valid"}
        
    except Exception as e:
        frappe.log_error(f"Error validating payment amount: {str(e)}")
        return {"valid": False, "message": "Error validating payment amount"}

@frappe.whitelist()
def get_sales_order_payment_summary(sales_order):
    """
    Get complete payment summary for a sales order
    """
    try:
        so = frappe.get_doc("Sales Order", sales_order)
        
        # Get all payment entries for this sales order
        payment_entries = frappe.get_all(
            "Payment Entry Reference",
            filters={
                "reference_doctype": "Sales Order",
                "reference_name": sales_order
            },
            fields=["parent", "allocated_amount"]
        )
        
        payments = []
        total_paid = 0
        
        for pe_ref in payment_entries:
            pe = frappe.get_doc("Payment Entry", pe_ref.parent)
            if pe.docstatus == 1:  # Only submitted payments
                payments.append({
                    "payment_entry": pe.name,
                    "posting_date": pe.posting_date,
                    "amount": pe_ref.allocated_amount,
                    "mode_of_payment": pe.mode_of_payment,
                    "reference_no": pe.reference_no
                })
                total_paid += flt(pe_ref.allocated_amount)
        
        outstanding = flt(so.grand_total) - total_paid
        
        return {
            "grand_total": so.grand_total,
            "total_paid": total_paid,
            "outstanding": max(0, outstanding),
            "payments": payments,
            "payment_status": "Fully Paid" if outstanding <= 0 else ("Partially Paid" if total_paid > 0 else "Pending")
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting payment summary: {str(e)}")
        return None

# Utility function for formatting currency (used in JavaScript)

def format_currency(amount, currency=None):
    """Format currency for display"""
    if not currency:
        currency = frappe.defaults.get_global_default("currency")
    return frappe.utils.fmt_money(amount, currency=currency)


# Helper function to get party account
def get_party_account(party_type, party, company):
    """
    Get party account for payment entry
    """
    if party_type == "Customer":
        return frappe.get_cached_value("Company", company, "default_receivable_account")
    elif party_type == "Supplier":
        return frappe.get_cached_value("Company", company, "default_payable_account")
    return None