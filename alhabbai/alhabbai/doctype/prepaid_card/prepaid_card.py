# Copyright (c) 2025, Nipun and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PrepaidCard(Document):
    def validate(self):
        self.validate_single_active_card()
        if not self.created_account:
            self.create_bank_account()
    
    def validate_single_active_card(self):
        """Ensure only one active card per user"""
        if self.is_active:
            existing = frappe.db.exists("Prepaid Card", {
                "user": self.user,
                "is_active": 1,
                "name": ["!=", self.name]
            })
            if existing:
                frappe.throw(f"User {self.user} already has an active prepaid card")
    
    def create_bank_account(self):
        """Create a bank account under Prepaid Cards group"""
        company = frappe.defaults.get_defaults().company
        account_name = f"{self.card_name} - {self.user}"
        
        # Create bank account
        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": account_name,
            "parent_account": "100 - Prepaid Cards - AH",
            "account_type": "Bank",
            "company": company,
            "is_group": 0
        })
        
        account.insert(ignore_permissions=True)
        
        # Update card with bank account
        self.bank_account = account.name
        self.created_account = 1
        
        frappe.msgprint(f"Bank account '{account_name}' created successfully")