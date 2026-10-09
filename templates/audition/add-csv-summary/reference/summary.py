import csv
import io
import math


def summarize(csv_text):
    rows = [row for row in csv.reader(io.StringIO(csv_text)) if row]
    result = {"row_count": 0, "numeric": {}, "non_numeric": []}
    if not rows:
        return result
    header, *data = rows
    result["row_count"] = len(data)
    for index, name in enumerate(header):
        try:
            values = [float(row[index].strip()) for row in data]
        except ValueError:
            values = []
        if not values or not all(math.isfinite(value) for value in values):
            result["non_numeric"].append(name)
        else:
            result["numeric"][name] = {
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "mean": round(sum(values) / len(values), 2),
            }
    return result
