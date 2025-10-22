# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import getdate
from frappe.utils import flt, today
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
import json




class JobRegistration(Document):

    def autoname(self):
        """Auto-generate Job Registration name:
        Format: JOB-{BranchCode}-{YY}-{######}
        Example: JOB-ALNDXB-25-000001
        """
        try:
            # ✅ Get Branch Code
            branch_code = None
            if getattr(self, "custom_branch", None):
                branch_code = frappe.db.get_value(
                    "Branch",
                    self.custom_branch,
                    "custom_branch_code"
                )

            if not branch_code:
                branch_code = "GEN"  # fallback if branch missing

            # ✅ Two-digit year
            year = str(getdate().year)[-2:]

            # ✅ Generate name
            self.name = make_autoname(f"JOB-{branch_code}-{year}-.######")

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "JobRegistration autoname failed")
            self.name = make_autoname("JOB-GEN-.######")


    def validate(self):
        """Control workflow transitions automatically"""
        # Default initial state
        if not self.custom_workflow_status:
            self.custom_workflow_status = "Draft"

        # Draft ↔ Pending logic
        # self.check_child_table_entries()

        # Validate allowed actions
        self.validate_role_access()

    def check_child_table_entries(self):
        """If documents exist → Pending; if none → Draft"""
        if self.docstatus:
            return

        has_documents = bool(getattr(self, "table_tujy", []))
        if has_documents and self.custom_workflow_status == "Draft":
            self.custom_workflow_status = "Pending"
        elif not has_documents and self.custom_workflow_status == "Pending":
            self.custom_workflow_status = "Draft"

    def validate_role_access(self):
        """Ensure only correct roles can act depending on workflow status"""
        user = frappe.session.user
        roles = frappe.get_roles(user)

        if user == "Administrator":
            return

        state = self.custom_workflow_status or "Draft"

        if state == "Draft" and "Receptionist" not in roles:
            frappe.throw("Only Receptionist can create or edit Draft Job Registrations.")

        elif state == "Pending" and not any(r in roles for r in ["Receptionist", "Typist", "Verifier"]):
            frappe.throw("Only Typist, Receptionist, or Verifier can work on Pending Job Registrations.")

        elif state == "Verified" and "Verifier" not in roles:
            frappe.throw("Only Verifier can modify or submit Verified Job Registrations.")

    def before_submit(self):
        """Allow only Verifier to submit Verified records"""
        user = frappe.session.user
        roles = frappe.get_roles(user)
        if self.custom_workflow_status != "Verified":
            frappe.throw(_("You can only submit after verification."))
        if "Verifier" not in roles and user != "Administrator":
            frappe.throw(_("Only Verifier can submit this document."))


# -----------------------------------------------------------------
# Action triggered by Verifier button to Verify + create Sales Order
# -----------------------------------------------------------------

@frappe.whitelist()
def verify_and_create_proforma(job_registration):
    """Verifier action: mark Verified, submit, and create linked Sales Order"""
    jr = frappe.get_doc("Job Registration", job_registration)
    user = frappe.session.user
    roles = frappe.get_roles(user)

    if "Verifier" not in roles and user != "Administrator":
        frappe.throw("Only Verifier can perform this action.")

    jr.custom_workflow_status = "Verified"
    jr.flags.ignore_validate = True
    jr.save(ignore_permissions=True)

    try:
        jr.submit()
        frappe.msgprint("✅ Job Registration verified and submitted successfully.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "JobRegistration Auto-Submit Failed")
        frappe.throw(f"Error while submitting Job Registration: {str(e)}")

    # ✅ Always use unified function
    so_name = create_sales_order_from_job_registration(job_registration)
    frappe.msgprint(f"📄 Proforma (Sales Order) <b>{so_name}</b> created successfully.", title="Verification Complete", wide=True)
    return so_name




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



@frappe.whitelist()
def create_sales_order_from_job_registration(job_registration: str):
    

    jr = frappe.get_doc("Job Registration", job_registration)
    company = getattr(jr, "company", None) or frappe.defaults.get_defaults().company
    if not company:
        frappe.throw("Company is required to create Sales Order")

    # ✅ Prevent duplicates
    existing_so = frappe.db.get_value(
        "Sales Order",
        {"custom_job_registration": job_registration, "docstatus": ["!=", 2]},
        "name",
    )
    if existing_so:
        frappe.msgprint(f"📄 Proforma Invoice <b>{existing_so}</b> already exists.")
        return existing_so

    currency = frappe.get_cached_value("Company", company, "default_currency")

    try:
        # ---- Create Sales Order ----
        so = frappe.new_doc("Sales Order")
        so.update({
            "customer": jr.customer,
            "company": company,
            "transaction_date": today(),
            "delivery_date": today(),
            "selling_price_list": "Standard Selling",
            "currency": currency,
            "custom_job_registration": jr.name,
            "custom_candidate": getattr(jr, "custom_candidate", None),
            "custom_branch": getattr(jr, "custom_branch", None),
            "custom_advance_payment_amount":  flt(jr.advance_payment or 0)

        })

        # ---- Add Items ----
        for row in getattr(jr, "service_package", []):
            if not row.service_package_item:
                continue
            item_doc = frappe.get_doc("Item", row.service_package_item)
            item_row = so.append("items", {
                "item_code": row.service_package_item,
                "qty": 1,
                "rate": flt(row.amount or 0),
                "warehouse": "Stores - AH",
            })
            # Apply Item Tax Template if available
            if getattr(item_doc, "taxes", []):
                item_row.item_tax_template = item_doc.taxes[0].item_tax_template

        if not so.items:
            frappe.throw("No valid service items found in Job Registration")

        # ---- Taxes and Charges ----
        default_tax_template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {"company": company, "is_default": 1},
            "name"
        )
        if default_tax_template:
            so.taxes_and_charges = default_tax_template

        # Compute totals & taxes
        so.run_method("set_missing_values")
        so.run_method("calculate_taxes_and_totals")

        # Fallback: if still no tax rows
        if not so.get("taxes") and default_tax_template:
            tpl_rows = get_taxes_and_charges(
                master_doctype="Sales Taxes and Charges Template",
                master_name=default_tax_template,
            )
            for t in tpl_rows:
                so.append("taxes", t)
            calculate_taxes_and_totals(so)

        # ---- Save as Draft (no submit) ----
        so.insert(ignore_permissions=True)
        frappe.msgprint(f"📄 Draft Sales Order <b>{so.name}</b> created successfully.")
        # pe_name = create_payment_entry_from_job_registration(job_registration)
        # frappe.msgprint(f"Payment Entry {pe_name} created and pending link.")
        return so.name

    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        existing = frappe.db.get_value(
            "Sales Order", {"custom_job_registration": job_registration}, "name"
        )
        if existing:
            frappe.msgprint(f"📄 Proforma Invoice <b>{existing}</b> already exists.")
            return existing
        else:
            frappe.throw("Duplicate Sales Order naming conflict occurred. Please retry.")

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Sales Order Creation Failed")
        frappe.throw(f"❌ Failed to create Sales Order: {str(e)}")



@frappe.whitelist()
def create_payment_entry_from_job_registration(job_registration):
    jr = frappe.get_doc("Job Registration", job_registration)

    if not jr.customer or not jr.advance_payment or jr.advance_payment <= 0:
        frappe.msgprint("No advance payment to create Payment Entry.")
        return

    # Check if already created
    existing = frappe.get_all(
        "Payment Entry",
        filters={"reference_no": jr.name, "docstatus": ["!=", 2]},
        pluck="name"
    )
    if existing:
        return existing[0]

    # Create Payment Entry
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = jr.customer
    pe.company = frappe.defaults.get_defaults().company
    pe.posting_date = frappe.utils.nowdate()
    pe.paid_amount = jr.advance_payment
    pe.received_amount = jr.advance_payment
    pe.mode_of_payment = jr.custom_mode_of_payment or "Cash"
    pe.reference_no = jr.name
    pe.reference_date = frappe.utils.nowdate()

    # Add account details
    default_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": pe.mode_of_payment, "company": pe.company},
        "default_account"
    )
    if not default_account:
        frappe.throw(f"No account found for mode of payment {pe.mode_of_payment}")

    pe.paid_to = default_account
    pe.save(ignore_permissions=True)
    # pe.submit()  # optional — submit immediately

    frappe.msgprint(f"💰 Payment Entry {pe.name} created for advance {jr.advance_payment}")
    return pe.name









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


@frappe.whitelist()
def create_government_purchase_invoice(job_registration, amount=None):
    """Create a Purchase Invoice for government fees"""
    try:
        # Check if PI already exists
        existing_pi = frappe.get_all(
            "Purchase Invoice",
            filters={
                "custom_job_registration": job_registration,  # Changed field name
                "docstatus": ["!=", 2]
            }
        )

        if existing_pi:
            return existing_pi[0].name

        # Get the bank account for current user's prepaid card
        current_user = frappe.session.user
        bank_account = get_user_bank_account(current_user)

        if not bank_account:
            frappe.throw("No active prepaid card bank account assigned to current user")

        # Get job registration doc
        jr = frappe.get_doc("Job Registration", job_registration)

        # Get price from Standard Buying price list
        government_fees_price = frappe.get_all(
            "Item Price",
            filters={
                "item_code": "Government Fees",
                "price_list": "Standard Buying",
                "buying": 1
            },
            fields=["price_list_rate"],
            order_by="valid_from desc",
            limit=1
        )

        if not government_fees_price:
            frappe.throw("No price found for Government Fees in Standard Buying price list")

        service_amount = government_fees_price[0].price_list_rate

        # Create Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.posting_date = frappe.utils.today()
        pi.supplier = "Government"
        pi.company = frappe.defaults.get_defaults().company
        pi.is_paid = 1
        pi.mode_of_payment = "Government Prepaid Card"
        pi.cash_bank_account = bank_account
        pi.price_list = "Standard Buying"

        # Add item with price from price list
        pi.append("items", {
            "item_code": "Government Fees",
            "qty": 1,
            "rate": service_amount,
            "amount": service_amount
        })

        # Set totals
        pi.total = service_amount
        pi.grand_total = service_amount
        pi.rounded_total = service_amount

        # Link to job registration using custom field
        pi.custom_job_registration = job_registration

        # Save and submit
        pi.insert(ignore_permissions=True)
        pi.submit()

        # frappe.msgprint(
        #     f"Purchase Invoice created with amount {service_amount} from Standard Buying price list"
        # )
        return pi.name

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "JobRegistration: create_government_purchase_invoice failed")
        frappe.throw(f"Error while creating Purchase Invoice: {str(e)}")


@frappe.whitelist()
def submit_job_registration(name):
    doc = frappe.get_doc("Job Registration", name)
    doc.submit()
    return doc.name


@frappe.whitelist()
def link_advance_payment_entry(doc, method):
    """On Sales Order Submit → Create and link Payment Entry for the advance."""
    try:
        if not getattr(doc, "custom_job_registration", None):
            return

        jr = frappe.get_doc("Job Registration", doc.custom_job_registration)
        advance_amount = flt(doc.custom_advance_payment_amount or 0)

        if advance_amount <= 0:
            frappe.msgprint("No advance amount found to create payment entry.")
            return

        # Check if already exists
        existing_pe = frappe.db.get_value(
            "Payment Entry Reference",
            {"reference_name": doc.name, "reference_doctype": "Sales Order"},
            "parent"
        )
        if existing_pe:
            frappe.msgprint(f"Payment Entry {existing_pe} already linked.")
            return

        # Create new Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.posting_date = frappe.utils.today()
        pe.company = doc.company
        pe.party_type = "Customer"
        pe.party = doc.customer
        pe.mode_of_payment = doc.custom_mode_of_payment or "Cash"
        pe.reference_no = doc.name
        pe.reference_date = frappe.utils.today()
        pe.paid_amount = advance_amount
        pe.received_amount = advance_amount

        # Accounts
        pe.paid_from = frappe.db.get_value("Account", {"account_type": "Receivable", "company": doc.company})
        pe.paid_to = frappe.db.get_value("Account", {"account_type": "Cash", "company": doc.company})

        # Reference
        pe.append("references", {
            "reference_doctype": "Sales Order",
            "reference_name": doc.name,
            "allocated_amount": advance_amount
        })

        # Insert and submit
        pe.insert(ignore_permissions=True)
        pe.submit()

        frappe.msgprint(f"💰 Payment Entry {pe.name} created and linked for Advance AED {advance_amount}")
        return pe.name

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "JobRegistration: link_advance_payment_entry failed")
        frappe.throw(f"Error while creating Payment Entry: {str(e)}")

 
