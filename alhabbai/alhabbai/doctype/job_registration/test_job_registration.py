# Copyright (c) 2025, Nipun and Contributors
# See license.txt

import frappe
import unittest

class TestJobRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test dependencies"""
        try:
            # Clean up existing test data
            cls.cleanup_test_data()
            
            company = frappe.defaults.get_defaults().company
            
            # Create/Get root account
            if not frappe.db.exists("Account", {"account_name": "Bank Accounts - AH", "company": company}):
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": "Bank Accounts - AH",
                    "parent_account": "Assets - AH",  # Make sure this exists in your CoA
                    "account_type": "Bank",
                    "is_group": 1,
                    "company": company
                }).insert()

            bank_account = frappe.db.get_value("Account", 
                {"account_name": "Bank Accounts - AH", "company": company}, "name")

            # Create prepaid cards group
            if not frappe.db.exists("Account", {"account_name": "100 - Prepaid Cards", "company": company}):
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": "100 - Prepaid Cards",
                    "parent_account": bank_account,
                    "account_type": "Bank",
                    "is_group": 1,
                    "company": company
                }).insert()

            prepaid_group = frappe.db.get_value("Account", 
                {"account_name": "100 - Prepaid Cards", "company": company}, "name")

            # Create test prepaid card account
            if not frappe.db.exists("Account", {"account_name": "_Test Prepaid Card", "company": company}):
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": "_Test Prepaid Card",
                    "parent_account": prepaid_group,
                    "account_type": "Bank",
                    "company": company,
                    "is_group": 0
                }).insert()

            test_account = frappe.db.get_value("Account", 
                {"account_name": "_Test Prepaid Card", "company": company}, "name")

            # Create test customer
            if not frappe.db.exists("Customer", "_Test Customer"):
                frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": "_Test Customer",
                    "customer_type": "Company"
                }).insert()
                
            # Create test branch
            if not frappe.db.exists("Branch", "_Test Branch"):
                frappe.get_doc({
                    "doctype": "Branch",
                    "branch_name": "_Test Branch",  # Changed from branch to branch_name
                    "company": company
                }).insert()

            # Create test item
            if not frappe.db.exists("Item", "_Test Service Item"):
                frappe.get_doc({
                    "doctype": "Item",
                    "item_code": "_Test Service Item",
                    "item_name": "_Test Service Item",
                    "item_group": "Services",
                    "is_stock_item": 0,
                    "standard_rate": 100
                }).insert()

            # Create test prepaid card
            if not frappe.db.exists("Prepaid Card", {"card_name": "_Test Card"}):
                frappe.get_doc({
                    "doctype": "Prepaid Card",
                    "card_name": "_Test Card",
                    "user": "Administrator",
                    "bank_account": test_account,
                    "is_active": 1
                }).insert()

            frappe.db.commit()

        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Error in setup: {str(e)}")
            raise e

    @classmethod
    def cleanup_test_data(cls):
        """Clean up any existing test data"""
        try:
            frappe.db.sql("delete from `tabPrepaid Card` where card_name='_Test Card'")
            frappe.db.sql("delete from `tabAccount` where account_name='_Test Prepaid Card'")
            frappe.db.sql("delete from `tabAccount` where account_name='100 - Prepaid Cards'")
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Error in cleanup: {str(e)}")
            raise e

    def create_test_job_registration(self):
        """Helper to create a test job registration"""
        jr = frappe.get_doc({
            "doctype": "Job Registration",
            "customer": "_Test Customer",
            "custom_branch": "_Test Branch",  # Add the branch field
            "service_package": [{
                "service_package_item": "_Test Service Item",
                "amount": 100
            }]
        })
        jr.insert()
        return jr

    def test_create_sales_order(self):
        """Test creation of sales order from job registration"""
        jr = self.create_test_job_registration()

        # Create sales order
        so_name = frappe.get_doc("Job Registration", jr.name).create_sales_order_from_job_registration()
        
        # Verify sales order was created
        self.assertTrue(frappe.db.exists("Sales Order", so_name))
        
        # Check sales order details
        so = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(so.customer, "_Test Customer")
        self.assertEqual(len(so.items), 1)
        self.assertEqual(so.items[0].item_code, "_Test Service Item")
        self.assertEqual(so.items[0].amount, 100)
        self.assertEqual(so.grand_total, 100)
        self.assertEqual(so.job_registration, jr.name)

    def test_prepaid_card_association(self):
        """Test prepaid card bank account assignment"""
        jr = self.create_test_job_registration()
        
        # Get bank account for current user
        bank_account = frappe.get_doc("Job Registration", jr.name).get_user_bank_account("Administrator")
        
        self.assertEqual(bank_account, "_Test Prepaid Card - AH")

    def test_workflow_transitions(self):
        """Test workflow status transitions"""
        jr = self.create_test_job_registration()
        
        # Initial state should be Draft
        self.assertEqual(jr.custom_workflow_status, "Draft")
        
        # Add document to trigger Pending state
        jr.append("table_tujy", {
            "document_type": "Test Doc"
        })
        jr.save()
        
        self.assertEqual(jr.custom_workflow_status, "Pending")
        
        # Submit should set status to Verified
        jr.submit()
        self.assertEqual(jr.custom_workflow_status, "Verified")

    def tearDown(self):
        """Clean up test data"""
        frappe.set_user("Administrator")
