"""Request dispatch after authentication and token validation."""


def handle(user, action, settings, audit):
    if action == "status":
        return {"enabled": settings["enabled"]}
    if action == "disable":
        settings["enabled"] = False
        audit.append((user["name"], "disable"))
        return {"ok": True}
    if action == "enable":
        if user["role"] != "admin":
            raise PermissionError("admin required")
        settings["enabled"] = True
        audit.append((user["name"], "enable"))
        return {"ok": True}
    raise ValueError("unknown action")
