import frappe
from frappe.utils import flt, today
from erpnext.accounts.utils import get_account_currency


# --------------------------------------------------------------------------
# ON SUBMIT → AUTO PAYMENT ENTRY CREATION
# --------------------------------------------------------------------------
def sales_order_on_submit(doc, method):
    """Automatically create and link Payment Entry when Sales Order is submitted."""
    try:
        advance_amount = flt(doc.custom_advance_payment_amount or 0)
        if advance_amount <= 0:
            frappe.msgprint("No advance payment to create Payment Entry.")
            return

        # Check if already linked
        existing_pe = frappe.db.get_value(
            "Payment Entry Reference",
            {"reference_doctype": "Sales Order", "reference_name": doc.name},
            "parent"
        )
        if existing_pe:
            frappe.msgprint(f"Payment Entry {existing_pe} already linked.")
            return existing_pe

        # Create new Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = doc.customer
        pe.company = doc.company
        pe.posting_date = today()
        pe.mode_of_payment = doc.custom_mode_of_payment or "Cash"
        pe.reference_no = doc.name
        pe.reference_date = today()
        pe.paid_amount = advance_amount
        pe.received_amount = advance_amount

        # Accounts
        pe.paid_from = frappe.db.get_value(
            "Account", {"account_type": "Receivable", "company": doc.company}
        )
        mop_acc = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": pe.mode_of_payment, "company": doc.company},
            "default_account",
        )
        if not mop_acc:
            frappe.throw(f"No default account found for mode of payment {pe.mode_of_payment}")
        pe.paid_to = mop_acc

        # Add reference to Sales Order
        pe.append("references", {
            "reference_doctype": "Sales Order",
            "reference_name": doc.name,
            "allocated_amount": advance_amount,
        })

        pe.insert(ignore_permissions=True)
        pe.submit()

        update_sales_order_payment_status(doc, pe, advance_amount)

        frappe.msgprint(f"💰 Payment Entry {pe.name} created and linked for advance AED {advance_amount}")
        return pe.name

    except Exception:
        frappe.log_error(frappe.get_traceback(), "SalesOrder: Auto Payment Entry Creation Failed")
        frappe.throw("Failed to create Payment Entry on Sales Order submission.")


# --------------------------------------------------------------------------
# UPDATE PAYMENT STATUS & OUTSTANDING
# --------------------------------------------------------------------------
def update_sales_order_payment_status(sales_order, payment_entry, payment_amount):
    """Updates Sales Order payment details and outstanding after Payment Entry."""
    try:
        so = sales_order if isinstance(sales_order, frappe.model.document.Document) else frappe.get_doc("Sales Order", sales_order)

        # Update totals
        so.db_set("custom_payment_entry", payment_entry.name)
        so.db_set("advance_paid", flt(so.advance_paid) + flt(payment_amount))

        outstanding = max(0, flt(so.grand_total) - flt(so.advance_paid))
        so.db_set("custom_outstanding_amount", outstanding)

        # Payment status (custom)
        custom_status = (
            "Fully Paid" if outstanding <= 0
            else "Partially Paid" if flt(so.advance_paid) > 0
            else "Pending"
        )
        so.db_set("custom_payment_status", custom_status)

        # Sync with ERPNext native payment_status
        native_status = "Paid" if custom_status == "Fully Paid" else "Partly Paid" if custom_status == "Partially Paid" else "Unpaid"
        so.db_set("payment_status", native_status)

        frappe.db.commit()
        return True

    except Exception:
        frappe.log_error(frappe.get_traceback(), "SalesOrder: update_sales_order_payment_status failed")


# --------------------------------------------------------------------------
# CANCEL PAYMENT ENTRY
# --------------------------------------------------------------------------
def cancel_payment_entry(sales_order, payment_entry):
    """Cancel linked Payment Entry and update Sales Order outstanding accordingly."""
    try:
        pe = frappe.get_doc("Payment Entry", payment_entry)
        if pe.docstatus == 1:
            pe.cancel()

        so = frappe.get_doc("Sales Order", sales_order)
        paid_amount = next(
            (ref.allocated_amount for ref in pe.references
             if ref.reference_doctype == "Sales Order" and ref.reference_name == sales_order),
            0,
        )

        so.db_set("advance_paid", flt(so.advance_paid) - flt(paid_amount))
        outstanding = max(0, flt(so.grand_total) - flt(so.advance_paid))
        so.db_set("custom_outstanding_amount", outstanding)
        custom_status = "Pending" if so.advance_paid <= 0 else "Partially Paid"
        so.db_set("custom_payment_status", custom_status)
        so.db_set("payment_status", "Unpaid" if so.advance_paid <= 0 else "Partly Paid")

        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "SalesOrder: cancel_payment_entry failed")


# --------------------------------------------------------------------------
# DYNAMIC CALCULATORS
# --------------------------------------------------------------------------
def calculate_outstanding_amount(doc):
    """Recalculate outstanding & payment status for live updates."""
    if hasattr(doc, "grand_total") and hasattr(doc, "advance_paid"):
        outstanding = max(0, flt(doc.grand_total) - flt(doc.advance_paid))
        if hasattr(doc, "custom_outstanding_amount"):
            doc.custom_outstanding_amount = outstanding

        custom_status = (
            "Fully Paid" if outstanding <= 0
            else "Partially Paid" if flt(doc.advance_paid) > 0
            else "Pending"
        )
        if hasattr(doc, "custom_payment_status"):
            doc.custom_payment_status = custom_status

        # Sync native field
        if hasattr(doc, "payment_status"):
            doc.payment_status = (
                "Paid" if custom_status == "Fully Paid"
                else "Partly Paid" if custom_status == "Partially Paid"
                else "Unpaid"
            )


def sales_order_before_save(doc, method):
    calculate_outstanding_amount(doc)


def sales_order_on_update_after_submit(doc, method):
    calculate_outstanding_amount(doc)
