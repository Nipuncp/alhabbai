# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


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
        pi.custom_job_registration = job_registration  # Changed field name
        
        # Save and submit
        pi.insert(ignore_permissions=True)
        pi.submit()
        
        frappe.msgprint(f"Purchase Invoice created with amount {service_amount} from Standard Buying price list")
        return pi.name
        
    except Exception as e:
        frappe.log_error(f"Error in create_government_purchase_invoice: {str(e)}")
        raise
    

@frappe.whitelist()
def create_sales_order_from_job_registration(job_registration):
    """
    Create a Sales Order from a Job Registration document.
    Directly applies the UAE VAT 5% tax template and sets advance_paid from Job Registration.
    """
    # Retrieve the Job Registration document
    jr = frappe.get_doc("Job Registration", job_registration)
    if not jr:
        frappe.throw("Job Registration not found.")
    
    # Ensure the Job Registration has a customer defined
    if not jr.customer:
        frappe.throw("Customer is not specified in the Job Registration.")

    # Handle discount amount with extra safety
    try:
        discount_amount = 0
        if hasattr(jr, 'custom_discount_amount') and jr.custom_discount_amount:
            if isinstance(jr.custom_discount_amount, str) and jr.custom_discount_amount.strip():
                discount_amount = float(jr.custom_discount_amount)
            elif isinstance(jr.custom_discount_amount, (int, float)):
                discount_amount = float(jr.custom_discount_amount)
    except Exception as e:
        frappe.msgprint(f"Warning: Error processing discount amount: {str(e)}. Setting to 0.")
        discount_amount = 0
    
    # Get advance payment amount from Job Registration
    advance_payment = 0
    if hasattr(jr, 'advance_payment') and jr.advance_payment:
        try:
            if isinstance(jr.advance_payment, str) and jr.advance_payment.strip():
                advance_payment = float(jr.advance_payment)
            elif isinstance(jr.advance_payment, (int, float)):
                advance_payment = float(jr.advance_payment)
        except Exception as e:
            frappe.msgprint(f"Warning: Error processing advance payment: {str(e)}. Setting to 0.")
    
    # Create the Sales Order document
    so = frappe.new_doc("Sales Order")
    so.customer = jr.customer
    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.today()
    so.company = frappe.defaults.get_defaults().company
    
    # Set job_registration reference if you have a custom field for it
    if frappe.get_meta("Sales Order").has_field("job_registration"):
        so.job_registration = jr.name
    
    # Add items from the Job Registration
    for child in jr.service_package:
        so.append("items", {
            "item_code": child.service_package_item,
            "qty": 1,
            "rate": child.amount
        })
    
    # Directly set the UAE VAT 5% tax template
    so.taxes_and_charges = "UAE VAT 5% - AH"
    
    # Apply discount directly to the sales order
    if isinstance(discount_amount, (int, float)) and discount_amount > 0:
        so.apply_discount_on = "Grand Total"
        so.discount_amount = discount_amount
        frappe.msgprint(f"Applying discount of {discount_amount}")
    
    # Set advance_paid if it's a valid field in Sales Order
    if frappe.get_meta("Sales Order").has_field("advance_paid"):
        so.advance_paid = advance_payment
        frappe.msgprint(f"Setting advance paid amount: {advance_payment}")
    elif advance_payment > 0:
        frappe.msgprint(f"Note: Advance payment of {advance_payment} exists but could not be set in Sales Order (field not found)")
    
    # Save the sales order
    so.insert(ignore_permissions=True)
    
    # Now fetch the saved document to apply taxes from template
    so = frappe.get_doc("Sales Order", so.name)
    
    # Load the taxes - manual approach since append_taxes_from_template() isn't available
    if so.taxes_and_charges:
        # Get tax template
        tax_template = frappe.get_doc("Sales Taxes and Charges Template", so.taxes_and_charges)
        
        # Clear existing taxes if any
        so.taxes = []
        
        # Add taxes from template
        for tax in tax_template.taxes:
            so.append("taxes", {
                "charge_type": tax.charge_type,
                "account_head": tax.account_head,
                "description": tax.description,
                "rate": tax.rate,
                "included_in_print_rate": tax.included_in_print_rate
            })
    
    # Calculate taxes and totals
    so.calculate_taxes_and_totals()
    so.save()
    
    frappe.msgprint(f"Sales Order {so.name} created successfully with UAE VAT 5% tax template applied.")
    
    return so.name