import frappe

def update_customer_primary_address(doc, method):
    linked_customers = frappe.get_all(
        "Customer", filters={"customer_primary_address": doc.name}, fields=["name"]
    )
    address_parts = []

    if doc.address_line1:
        address_parts.append(doc.address_line1.strip())
    if doc.address_line2:
        address_parts.append(doc.address_line2.strip())
    if doc.city:
        address_parts.append(doc.city.strip())
    if doc.state:
        address_parts.append(doc.state.strip())
    if doc.pincode:
        address_parts.append(doc.pincode.strip())
    if doc.country:
        address_parts.append(doc.country.strip())

    full_address = ", ".join(address_parts)

    for customer in linked_customers:
        frappe.db.set_value("Customer", customer.name, "primary_address", full_address)
