# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json
from frappe import _
from erpnext.stock.get_item_details import get_item_tax_map

class JobRegistration(Document):
    def validate(self):
        """
        Validate the document during save.
        Implement custom workflow state transitions.
        """
        # If submitting, ensure custom_workflow_status is "Verified"
        if self.flags.in_submit or (self.docstatus == 0 and self.__dict__.get('__submit', False)):
            self.custom_workflow_status = "Verified"
            return  # Skip other validations when submitting
        
        # Initialize custom_workflow_status if not set
        if not self.custom_workflow_status:
            self.custom_workflow_status = "Draft"
            
        # Check child table entries to determine if status should be Pending
        self.check_child_table_entries()
            
        # Validate workflow transitions
        self.validate_workflow_transitions()
    
    
    def check_child_table_entries(self):
        """
        Check if there are entries in Documents (table_tujy) and update workflow status accordingly.
        Only applies when document is in Draft state.
        """
        if self.custom_workflow_status == "Draft" and not self.docstatus:
            has_document_entries = bool(getattr(self, 'table_tujy', []))
            
            if has_document_entries:
                self.custom_workflow_status = "Pending"
                 # Remove PI creation from here since it's handled in JS
                frappe.msgprint("Status changed to Pending")


    def validate_role_access(self):
        current_user = frappe.session.user
        user_roles = frappe.get_roles(current_user)

        # Allow Administrator to do anything
        if "Administrator" in user_roles:
            return

        status = self.custom_workflow_status

        if status == "Draft":
            if "Receptionist" not in user_roles:
                frappe.throw("Only a Receptionist can work on a Job Registration in Draft status.")
        
        elif status == "Pending":
            if "Typist" not in user_roles and "Receptionist" not in user_roles:
                frappe.throw("Only a Typist or Receptionist can work on a Job Registration in Pending status.")

        elif status == "Verified":
            if "Verifier" not in user_roles:
                frappe.throw("Only a Verifier can work on a Job Registration in Verified status.")



    
    def validate_workflow_transitions(self):
        """
        Validate that workflow transitions are valid
        """
        # Only allow submit if document is in Verified state
        if self.docstatus == 1 and self.custom_workflow_status != "Verified":
            # If submitting through API, auto-set to Verified instead of throwing error
            self.custom_workflow_status = "Verified"
    
    # Remove creation from on_submit since it's now handled in check_child_table_entries
    def on_submit(self):
        """Handler for document submission"""
        pass


def get_user_bank_account(user):
    """Get the bank account assigned to user's prepaid card"""
    card = frappe.get_all(
        "Prepaid Card",
        filters={
            "user": user,
            "is_active": 1
        },
        fields=["bank_account"],
        limit=1
    )
    
    if not card:
        frappe.throw(f"No active prepaid card assigned to user {user}")
    
    return card[0].bank_account



# alhabbai/alhabbai/doctype/job_registration/job_registration.py


@frappe.whitelist()
def create_sales_order_from_job_registration(job_registration: str):
    jr = frappe.get_doc("Job Registration", job_registration)
    if not jr:
        frappe.throw(_("Job Registration {0} not found").format(job_registration))
    if not jr.customer:
        frappe.throw(_("Customer is required on Job Registration"))

    company = frappe.defaults.get_defaults().company
    currency = frappe.get_cached_value("Company", company, "default_currency")

    # --- Initialize Sales Order
    so = frappe.new_doc("Sales Order")
    so.customer = jr.customer
    so.company = company
    # Copy candidate or other custom fields from Job Registration
    if frappe.get_meta("Sales Order").has_field("custom_candidate") and jr.get("custom_candidate"):
        so.custom_candidate = jr.custom_candidate
        so.custom_branch = jr.custom_branch

    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.today()
    so.taxes_and_charges = None  # we will compute our own taxes

    # optional link back
    if frappe.get_meta("Sales Order").has_field("job_registration"):
        so.job_registration = jr.name

    # set currencies and price list
    so.selling_price_list = "Standard Selling"
    so.currency = currency
    so.price_list_currency = currency
    so.conversion_rate = 1.0
    so.plc_conversion_rate = 1.0

    frappe.msgprint(f"[DEBUG] Creating SO from JR {jr.name} for {jr.customer}")

    added = 0
    for row in (jr.service_package or []):
        item_code = row.service_package_item
        rate = float(row.amount or 0)
        if not item_code:
            continue

        item_doc = frappe.get_doc("Item", item_code)
        tax_template, tax_rate_map = None, {}

        if getattr(item_doc, "taxes", None) and item_doc.taxes:
            tax_template = item_doc.taxes[0].item_tax_template
            if tax_template:
                raw = get_item_tax_map(company, tax_template)
                tax_rate_map = frappe.parse_json(raw) if isinstance(raw, str) else (raw or {})

        frappe.msgprint(f"[DEBUG] Item: {item_code} | Rate: {rate} | Template: {tax_template or '—'} | Map: {json.dumps(tax_rate_map)}")

        so.append("items", {
            "item_code": item_code,
            "item_name": item_doc.item_name or item_code,
            "description": item_doc.description or item_code,
            "uom": item_doc.stock_uom or "Nos",
            "stock_uom": item_doc.stock_uom or "Nos",
            "qty": 1,
            "rate": rate,
            "amount": rate,
            "item_tax_template": tax_template,
            "item_tax_rate": json.dumps(tax_rate_map),
            "tax_amount": 0.0,
            "cost_center": "Main - AH"
        })
        added += 1

    if not added:
        frappe.throw(_("No service items found on Job Registration {0}.").format(jr.name))

    # --- Calculate custom taxes
    tax_summary = {}
    for it in so.items:
        it.tax_amount = 0.0
        rate_map = frappe.parse_json(it.item_tax_rate) if it.item_tax_rate else {}

        for acc, r in rate_map.items():
            r = float(r or 0)
            if r <= 0:
                frappe.msgprint(f"[DEBUG] ⏭️ Skipping zero-rate: {it.item_code} → {acc} @ {r}%")
                continue

            amt = round(float(it.rate) * (r / 100.0), 2)
            it.tax_amount += amt
            tax_summary.setdefault(acc, 0.0)
            tax_summary[acc] += amt
            frappe.msgprint(f"[DEBUG] ✅ {it.item_code} → {acc} @ {r}% = {amt}")

    # --- Totals
    so.total = sum(float(it.amount or 0) for it in so.items)
    so.total_taxes_and_charges = sum(float(v) for v in tax_summary.values())
    so.grand_total = so.total + so.total_taxes_and_charges

    # --- Discounts and Advances
    jr_discount = float(jr.get("custom_discount_amount") or 0)
    if jr_discount:
        so.apply_discount_on = "Grand Total"
        so.discount_amount = jr_discount
        so.grand_total = max(0, so.grand_total - jr_discount)
        frappe.msgprint(f"[DEBUG] Applied JR discount: {jr_discount}")

    jr_advance = float(jr.get("advance_payment") or 0)
    if jr_advance:
        if frappe.get_meta("Sales Order").has_field("custom_advance_payment_amount"):
            so.custom_advance_payment_amount = jr_advance
        if frappe.get_meta("Sales Order").has_field("advance_paid"):
            so.advance_paid = jr_advance
        frappe.msgprint(f"[DEBUG] Carried forward advance payment: {jr_advance}")

    # --- Tax Table
    so.taxes = []
    for acc, amt in tax_summary.items():
        derived_rate = 0.0
        for it in so.items:
            rate_map = frappe.parse_json(it.item_tax_rate) if it.item_tax_rate else {}
            if acc in rate_map:
                derived_rate = float(rate_map[acc] or 0.0)
                break

        so.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": acc,
            "rate": derived_rate,
            "delivery_date": frappe.utils.nowdate(),
            "tax_amount": round(amt, 2),
            "description": f"{acc} @ {derived_rate}%",
            "cost_center": "Main - AH",
            "dont_recompute_tax": 1
        })

    # --- Save safely (prevent ERPNext override)
    so.flags.ignore_validate = True
    so.flags.ignore_mandatory = True
    so.flags.ignore_links = True
    so.flags.ignore_validate_update_after_save = True

    so.insert(ignore_permissions=True, ignore_links=True)

    # Freeze totals to prevent recalculation
    for tax in so.taxes:
        tax.db_set("dont_recompute_tax", 1)

    so.db_set("taxes_and_charges", None)
    so.db_set("total", round(so.total, 2))
    so.db_set("total_taxes_and_charges", round(so.total_taxes_and_charges, 2))
    so.db_set("grand_total", round(so.grand_total, 2))

    # --- Output summary
    summary = [
        f"[RESULT] SO: {so.name}",
        f"[RESULT] Subtotal: {frappe.utils.fmt_money(so.total, currency=currency)}",
        f"[RESULT] Taxes: {frappe.utils.fmt_money(so.total_taxes_and_charges, currency=currency)}",
        f"[RESULT] Discount: {frappe.utils.fmt_money(jr_discount, currency=currency)}",
        f"[RESULT] Grand Total: {frappe.utils.fmt_money(so.grand_total, currency=currency)}",
    ]
    if jr_advance:
        summary.append(f"[RESULT] Advance: {frappe.utils.fmt_money(jr_advance, currency=currency)}")

    frappe.msgprint("<br>".join(summary), title=_("Sales Order Created"), wide=True)
    return so.name







@frappe.whitelist()
def get_customer_discount_for_items(customer, service_items):
    """
    Get total customer discount for given service items based on their service package groups
    Args:
        customer: Customer name
        service_items: List of item codes or JSON string of service package items
    Returns:
        dict: Total discount amount and breakdown by item
    """
    import json
    
    if isinstance(service_items, str):
        try:
            service_items = json.loads(service_items)
        except:
            service_items = [service_items]
    
    if not customer or not service_items:
        return {"total_discount": 0, "item_discounts": []}
    
    # Get customer document with discount table
    customer_doc = frappe.get_doc("Customer", customer)
    
    if not hasattr(customer_doc, 'custom_discount_table') or not customer_doc.custom_discount_table:
        return {"total_discount": 0, "item_discounts": []}
    
    # Create discount lookup dictionary
    discount_lookup = {}
    for discount_row in customer_doc.custom_discount_table:
        if discount_row.service_package_group and discount_row.discount:
            discount_lookup[discount_row.service_package_group] = float(discount_row.discount)
    
    total_discount = 0
    item_discounts = []
    
    # Process each service item
    for item in service_items:
        item_code = item if isinstance(item, str) else item.get('service_package_item')
        
        if not item_code:
            continue
            
        # Get item's service package group (item_group)
        item_doc = frappe.get_doc("Item", item_code)
        service_package_group = item_doc.item_group
        
        # Look up discount for this service package group
        discount_amount = discount_lookup.get(service_package_group, 0)
        
        if discount_amount > 0:
            total_discount += discount_amount
            item_discounts.append({
                "item_code": item_code,
                "service_package_group": service_package_group,
                "discount": discount_amount
            })
    
    return {
        "total_discount": total_discount,
        "item_discounts": item_discounts
    }


@frappe.whitelist()
def get_service_package_group_discount(customer, service_package_group):
    """
    Get discount for a specific service package group for a customer
    """
    if not customer or not service_package_group:
        return 0
    
    customer_doc = frappe.get_doc("Customer", customer)
    
    if not hasattr(customer_doc, 'custom_discount_table') or not customer_doc.custom_discount_table:
        return 0
    
    # Find matching service package group
    for discount_row in customer_doc.custom_discount_table:
        if discount_row.service_package_group == service_package_group:
            return float(discount_row.discount) if discount_row.discount else 0
    
    return 0