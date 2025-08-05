import frappe

ALLOWED_ORIGINS = [
    "http://localhost:8002",  # Local development
    "http://127.0.0.1:8002",
    "http://192.168.0.12:8002",
    "https://app.checktrack.dev/api/user-api",
    "https://app.checktrack.dev/api/data-api",
    # "https://your-flutter-app.com"  # Production app URL
]

def validate_cors():
    """Set CORS headers for all requests."""

    print("CORS middleware executed")
    origin = frappe.get_request_header("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        frappe.local.response["headers"].update({
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Requested-With",
            "Access-Control-Allow-Credentials": "true",
        })

@frappe.whitelist(allow_guest=True)
def handle_preflight():
    """Handle preflight requests for CORS."""
    if frappe.request.method == "OPTIONS":
        frappe.local.response["headers"].update({
            "Access-Control-Allow-Origin": frappe.get_request_header("Origin"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Requested-With",
            "Access-Control-Allow-Credentials": "true",
        })
        frappe.local.response["type"] = "binary"
        frappe.local.response["status_code"] = 200
        return ""

def add_cors_headers(response):
    """Add CORS headers to the response."""
    print("CORS middleware executed")
    origin = frappe.get_request_header("Origin")
    allowed_origins = [
    "http://localhost:8002",  # Local development
    ]

    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Requested-With, Accept"
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response