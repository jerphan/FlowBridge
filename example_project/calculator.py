def calculate_discount(price, tier):
    if tier == 'gold':
        discount = price * 0.20
    elif tier == 'silver':
        discount = price * 0.10
    else:
        discount = 0.0
    return price - discount

def apply_tax(amount, tax_rate):
    tax = amount * tax_rate
    return amount + tax
