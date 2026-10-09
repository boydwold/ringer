def paginate(items, page, size):
    if type(page) is not int or type(size) is not int or page < 1 or size < 1:
        raise ValueError("page and size must be positive integers")
    start = (page - 1) * size
    return items[start:start + size]
