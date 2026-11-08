"""
scripts/generate_api_inventory.py
---------------------------------
Inspects all FastAPI endpoints and builds the complete API inventory,
cross-referencing with frontend API client definitions.
"""

import json
import os
import sys
import re

sys.path.insert(0, os.path.abspath("."))
from backend.main import app

def main():
    openapi = app.openapi()
    paths = openapi.get("paths", {})
    
    # Read frontend API client files to match routes
    api_dir = os.path.join("frontend", "src", "api")
    client_calls = {}
    if os.path.exists(api_dir):
        for fname in os.listdir(api_dir):
            if fname.endswith(".ts"):
                fpath = os.path.join(api_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                # Find URL patterns like '/rooms', '/buildings', etc.
                matches = re.findall(r"['\"`](/(?:api/)?([a-zA-Z0-9_\-\/\{\}\$]+))['\"`]", content)
                for full_m, sub_m in matches:
                    clean_path = "/" + sub_m.replace("${", "{").replace("}", "}")
                    client_calls.setdefault(clean_path, []).append(fname)

    inventory = []
    for path, methods in sorted(paths.items()):
        for method, details in sorted(methods.items()):
            operation_id = details.get("operationId", "")
            tags = details.get("tags", [])
            summary = details.get("summary", "")
            security = details.get("security", [])
            params = [p.get("name") for p in details.get("parameters", [])]
            req_body = details.get("requestBody", {})
            responses = list(details.get("responses", {}).keys())

            # Find matching frontend clients
            matched_clients = []
            for c_path, fnames in client_calls.items():
                if path.startswith(c_path) or c_path.startswith(path.split("{")[0]):
                    matched_clients.extend(fnames)
            matched_clients = list(set(matched_clients))

            inventory.append({
                "path": path,
                "method": method.upper(),
                "operation_id": operation_id,
                "tags": tags,
                "summary": summary,
                "is_authenticated": bool(security),
                "parameters": params,
                "has_body": bool(req_body),
                "responses": responses,
                "frontend_clients": matched_clients,
            })

    output_path = os.path.join("reports", "api_inventory_raw.json")
    os.makedirs("reports", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    print(f"Generated raw API inventory: {len(inventory)} operations across {len(paths)} paths.")
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    main()
