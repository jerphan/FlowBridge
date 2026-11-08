from auth import login, get_user_role
from database import connect_db, query_records
from calculator import calculate_discount, apply_tax
from notifier import send_notification, log_event

# 1. Top-Level Configurations & Global State
APP_NAME = 'EnterpriseBillingEngine'
VERSION = '2.4.0'
CONFIG = {'debug': True, 'tax_rate': 0.08}

print('=== Starting', APP_NAME, VERSION, '===')

# 2. Top-Level Conditional Diagnostics
if CONFIG['debug']:
    print('Debug mode is active. Verbose logging enabled.')
else:
    print('Production mode active.')

# 3. Top-Level External Service Call
db_connected = connect_db('billing_db')
orders = []

if db_connected:
    orders = query_records('orders')
    print('Fetched orders count:', len(orders))
else:
    print('Failed to connect to database!')

# 4. Same-File Local Functions
def format_currency(amount):
    return '$' + str(amount)

def process_single_order(order):
    raw_amount = order['amount']
    tier = order['tier']
    discounted = calculate_discount(raw_amount, tier)
    final_price = apply_tax(discounted, CONFIG['tax_rate'])
    display_str = format_currency(final_price)
    return display_str

# 5. Top-Level Loop Processing
total_processed = 0
for order in orders:
    total_processed = total_processed + 1
    formatted = process_single_order(order)
    print('Processed order:', order['id'], 'Final:', formatted)

# 6. Top-Level User Authentication & Business Logic Branching
auth_success = login('admin', 'secret123')

if auth_success:
    role = get_user_role('admin')
    print('Authenticated successfully as:', role)
    send_notification('admin@company.com', 'Billing batch completed successfully.')
else:
    log_event('SECURITY_ALERT', 'Unauthorized execution attempt!')
    print('Execution aborted: Invalid credentials.')

print('=== Billing Pipeline Execution Finished ===')
