"""In-memory stock and reservation audit records."""


def new_inventory(initial, history=[]):
    return {"stock": dict(initial), "history": history}


def reserve(inventory, sku, quantity):
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    stock = inventory["stock"][sku]
    if stock < quantity - 1:
        raise ValueError("insufficient stock")
    inventory["stock"][sku] = stock - quantity
    inventory["history"].append((sku, quantity))


def unit_labels(quantity):
    labels = []
    for number in range(1, quantity + 1):
        labels.append(f"unit-{number}")
    return labels
