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
def create_sales_order_from_job_registration(job_registration):
    """
    Create a Sales Order from a Job Registration document.
    Directly applies the UAE VAT 5% tax template and sets advance_paid from Job Registration.
    Handles both referral discount (custom_discount_amount) and company discount (custom_company_discount).
    """
    # Retrieve the Job Registration document
    jr = frappe.get_doc("Job Registration", job_registration)
    if not jr:
        frappe.throw("Job Registration not found.")
    
    # Ensure the Job Registration has a customer defined
    if not jr.customer:
        frappe.throw("Customer is not specified in the Job Registration.")

    # Calculate total discount amount (handling both referral and company discounts)
    total_discount_amount = 0
    
    # Debug information
    # frappe.msgprint(f"DEBUG - Document attributes: {dir(jr)}")
    
    # Try different possible field names for company discount
    company_discount_field_names = [
        'custom_company_discount', 
        'company_discount',
        'company_discount_amount'
    ]
    
    referral_discount_field_names = [
        'custom_discount_amount',
        'discount_amount',
        'referral_discount'
    ]
    
    # Process referral discount
    referral_discount = 0
    for field_name in referral_discount_field_names:
        try:
            if hasattr(jr, field_name) and getattr(jr, field_name):
                value = getattr(jr, field_name)
                frappe.msgprint(f"DEBUG - Found referral discount field '{field_name}' with value: {value}")
                
                if isinstance(value, str) and value.strip():
                    referral_discount = float(value)
                elif isinstance(value, (int, float)):
                    referral_discount = float(value)
                
                frappe.msgprint(f"Applied referral discount of {referral_discount} from field '{field_name}'")
                total_discount_amount += referral_discount
                break
        except Exception as e:
            frappe.msgprint(f"Warning: Error processing field '{field_name}': {str(e)}")
    
    # Process company discount
    company_discount = 0
    for field_name in company_discount_field_names:
        try:
            if hasattr(jr, field_name) and getattr(jr, field_name):
                value = getattr(jr, field_name)
                frappe.msgprint(f"DEBUG - Found company discount field '{field_name}' with value: {value}")
                
                if isinstance(value, str) and value.strip():
                    company_discount = float(value)
                elif isinstance(value, (int, float)):
                    company_discount = float(value)
                
                frappe.msgprint(f"Applied company discount of {company_discount} from field '{field_name}'")
                total_discount_amount += company_discount
                break
        except Exception as e:
            frappe.msgprint(f"Warning: Error processing field '{field_name}': {str(e)}")
    
    # Try to access directly using get method which might work better with custom fields
    if company_discount == 0:
        try:
            for field_name in company_discount_field_names:
                value = jr.get(field_name)
                if value:
                    frappe.msgprint(f"DEBUG - Found company discount using get() for '{field_name}': {value}")
                    if isinstance(value, str) and value.strip():
                        company_discount = float(value)
                    elif isinstance(value, (int, float)):
                        company_discount = float(value)
                    
                    frappe.msgprint(f"Applied company discount of {company_discount} from get('{field_name}')")
                    total_discount_amount += company_discount
                    break
        except Exception as e:
            frappe.msgprint(f"Warning: Error using get() method for company discount: {str(e)}")
    
    frappe.msgprint(f"DEBUG - Final total discount amount: {total_discount_amount}")
    
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
    
    # # Directly set the UAE VAT 5% tax template
    # so.taxes_and_charges = "UAE VAT 5% - AH"
    
    # # Apply total discount directly to the sales order
    # if total_discount_amount > 0:
    #     so.apply_discount_on = "Grand Total"
    #     so.discount_amount = total_discount_amount
    #     frappe.msgprint(f"Applying total discount of {total_discount_amount}")
    
    # # Set advance_paid if it's a valid field in Sales Order
    # if frappe.get_meta("Sales Order").has_field("advance_paid"):
    #     so.advance_paid = advance_payment
    #     frappe.msgprint(f"Setting advance paid amount: {advance_payment}")
    # elif advance_payment > 0:
    #     frappe.msgprint(f"Note: Advance payment of {advance_payment} exists but could not be set in Sales Order (field not found)")
    
    # # Save the sales order
    # so.insert(ignore_permissions=True)
    
    # # Now fetch the saved document to apply taxes from template
    # so = frappe.get_doc("Sales Order", so.name)
    
    # # Load the taxes - manual approach since append_taxes_from_template() isn't available
    # if so.taxes_and_charges:
    #     # Get tax template
    #     tax_template = frappe.get_doc("Sales Taxes and Charges Template", so.taxes_and_charges)
        
    #     # Clear existing taxes if any
    #     so.taxes = []
        
    #     # Add taxes from template
    #     for tax in tax_template.taxes:
    #         so.append("taxes", {
    #             "charge_type": tax.charge_type,
    #             "account_head": tax.account_head,
    #             "description": tax.description,
    #             "rate": tax.rate,
    #             "included_in_print_rate": tax.included_in_print_rate
    #         })
    
    # # Calculate taxes and totals
    # so.calculate_taxes_and_totals()
    # Add debug logging before tax calculation
    so.insert(ignore_permissions=True)
    frappe.logger().info(f"Before calculate_taxes_and_totals:")
    for item in so.items:
        frappe.logger().info(f"Item: {item.item_code}, Tax Template: {item.item_tax_template}, Tax Rate: {item.item_tax_rate}")
    
    so.calculate_taxes_and_totals()

    # Add debug logging after tax calculation  
    frappe.logger().info(f"After calculate_taxes_and_totals:")
    for item in so.items:
        frappe.logger().info(f"Item: {item.item_code}, Tax Rate: {item.tax_rate}, Tax Amount: {item.tax_amount}")

    
    so.save()
    
    frappe.msgprint(f"Sales Order {so.name} created successfully with UAE VAT 5% tax template applied.")
    
    return so.name
    
@frappe.whitelist()
def create_government_purchase_invoice(job_registration, amount=None):
    """Create a Purchase Invoice for government fees and make payment from prepaid card"""
    try:
        # Verify that the Job Registration exists
        if not frappe.db.exists("Job Registration", job_registration):
            frappe.msgprint(f"Job Registration {job_registration} not found")
            return "Error: Job Registration not found"
        
        # Check if PI already exists
        existing_pi = frappe.get_all(
            "Purchase Invoice",
            filters={
                "custom_job_registration": job_registration,
                "docstatus": ["!=", 2]
            }
        )
        
        frappe.logger().info(f"Found job registration: {job_registration}")
        if existing_pi:
            return existing_pi[0].name
            
        # Get the bank account for current user's prepaid card
        current_user = frappe.session.user
        bank_account = get_user_bank_account(current_user)
        
        if not bank_account:
            frappe.throw("No active prepaid card bank account assigned to current user")
            
        # Get job registration doc
        jr = frappe.get_doc("Job Registration", job_registration)
        
        # Fetch price from Standard Buying price list if amount is not provided
        if not amount or float(amount) <= 0:
            # Try to get the price from Standard Buying price list
            item_price = frappe.get_all(
                "Item Price",
                filters={
                    "item_code": "Government Fees",
                    "price_list": "Standard Buying",
                    "buying": 1
                },
                fields=["price_list_rate"],
                order_by="modified desc",
                limit=1
            )
            
            if item_price and item_price[0].price_list_rate:
                amount = item_price[0].price_list_rate
                frappe.logger().info(f"Found price in Standard Buying price list: {amount}")
            else:
                # Fallback to default amount if no price found
                amount = 100
                frappe.logger().info(f"No price found in price list, using default: {amount}")
        else:
            # Convert amount to float if it's provided as a string
            amount = float(amount)

        # Create Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = "Government"
        pi.posting_date = frappe.utils.today()
        pi.due_date = frappe.utils.today()
        pi.buying_price_list = "Standard Buying"
        pi.company = frappe.defaults.get_defaults().company
        pi.is_paid = 1
        pi.mode_of_payment = "Government Prepaid Card"
        pi.cash_bank_account = bank_account
        
        # Link to job registration using custom field
        pi.custom_job_registration = job_registration

        # Add item for Government Fees
        pi.append("items", {
            "item_code": "Government Fees",
            "qty": 1,
            "rate": amount,
            "amount": amount,
            "expense_account": "Government Charges - AH"
        })

        # Insert the invoice (which calculates totals, etc.)
        pi.insert(ignore_permissions=True)
        
        # Set payment details
        pi.paid_amount = pi.grand_total
        pi.outstanding_amount = 0
        
        # Save changes and submit
        pi.save()
        pi.submit()

        frappe.msgprint(f"Purchase Invoice {pi.name} created and marked as paid with amount {amount}")
        return pi.name

    except Exception as e:
        error_msg = f"Error in create_government_purchase_invoice: {str(e)}"
        frappe.log_error(error_msg)
        frappe.msgprint(error_msg)
        raise


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