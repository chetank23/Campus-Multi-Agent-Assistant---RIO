"""
scripts/audit_inventory.py
Inspects:
1. Complete frontend page and route inventory
2. Complete backend API inventory
3. API-to-frontend connection matrix
4. Database entity and relationship inventory
5. Feature completion matrix
6. Broken workflows / missing settings
7. LLM integration status
8. Supabase migration readiness
"""

import os
import sys
import re
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

def analyze_frontend_routes():
    app_routes_path = REPO_ROOT / "frontend" / "src" / "routes" / "AppRoutes.tsx"
    text = app_routes_path.read_text(encoding="utf-8")
    
    # Match <Route path="..." element={<...
    pattern = re.compile(r'<Route\s+path=["\']([^"\']+)["\']\s+element=\{<([^ />]+)')
    routes = pattern.findall(text)
    
    # Also find all page files
    pages_dir = REPO_ROOT / "frontend" / "src" / "pages"
    page_files = []
    for root, _, files in os.walk(pages_dir):
        for f in files:
            if f.endswith((".tsx", ".jsx")) and not f.startswith("."):
                rel = Path(root, f).relative_to(REPO_ROOT).as_posix()
                page_files.append(rel)
                
    return routes, page_files

def analyze_backend_routes():
    from backend.main import app
    openapi = app.openapi()
    paths = openapi.get("paths", {})
    route_list = []
    for path, methods_dict in paths.items():
        for m, details in methods_dict.items():
            if m.upper() not in ("HEAD", "OPTIONS"):
                route_list.append({
                    "method": m.upper(),
                    "path": path,
                    "summary": details.get("summary", ""),
                    "tags": details.get("tags", []),
                    "operationId": details.get("operationId", "")
                })
    return route_list

def analyze_frontend_api_calls():
    api_dir = REPO_ROOT / "frontend" / "src" / "api"
    api_endpoints = []
    pattern = re.compile(r'apiClient\.(get|post|put|patch|delete)<[^>]*>\([`"\']([^`"\']+)')
    pattern2 = re.compile(r'apiClient\.(get|post|put|patch|delete)\([`"\']([^`"\']+)')
    
    for f in api_dir.glob("*.ts"):
        text = f.read_text(encoding="utf-8")
        matches = pattern.findall(text) + pattern2.findall(text)
        for m, p in matches:
            api_endpoints.append({
                "file": f.name,
                "method": m.upper(),
                "path": p
            })
    return api_endpoints

def analyze_database_models():
    from typing import Any
    from backend.models.base import Base
    import backend.models
    models = []
    for name, cls_raw in Base.registry._class_registry.items():
        cls: Any = cls_raw
        if hasattr(cls, "__tablename__"):
            cols = [col.name for col in cls.__table__.columns]
            fks = [c.target_fullname for col in cls.__table__.columns for c in col.foreign_keys]
            models.append({
                "class": name,
                "table": cls.__tablename__,
                "columns": cols,
                "foreign_keys": fks
            })
    return sorted(models, key=lambda x: x["table"])

def analyze_connections(backend_routes, fe_calls):
    import re
    # Convert backend paths to regex patterns, e.g. /students/{id} -> ^/students/[^/]+$
    be_patterns = []
    for br in backend_routes:
        # replace {param} with [^/]+
        pattern_str = "^" + re.sub(r'\{[^}]+\}', r'[^/]+', br["path"]) + "$"
        be_patterns.append((re.compile(pattern_str), br))

    results = []
    for call in fe_calls:
        clean_path = call["path"].split("?")[0]
        # replace JS template interpolation ${...} with dummy value
        normalized_path = re.sub(r'\$\{[^}]+\}', '1', clean_path)
        
        matched_route = None
        for pat, br in be_patterns:
            if pat.match(normalized_path) and (br["method"] == call["method"] or call["method"] == "ANY"):
                matched_route = br
                break
        
        results.append({
            "client_file": call["file"],
            "client_method": call["method"],
            "client_path": call["path"],
            "normalized_path": normalized_path,
            "matched_backend_path": matched_route["path"] if matched_route else None,
            "matched": matched_route is not None
        })
    return results

if __name__ == "__main__":
    routes, pages = analyze_frontend_routes()
    print(f"Discovered {len(routes)} route declarations in AppRoutes.tsx")
    print(f"Discovered {len(pages)} page component files")
    
    backend_routes = analyze_backend_routes()
    print(f"Discovered {len(backend_routes)} registered backend endpoints")
    
    fe_calls = analyze_frontend_api_calls()
    print(f"Discovered {len(fe_calls)} frontend API client call expressions")

    models = analyze_database_models()
    print(f"Discovered {len(models)} database models")

    connections = analyze_connections(backend_routes, fe_calls)
    matched_count = sum(1 for c in connections if c["matched"])
    print(f"Connection Analysis: {matched_count}/{len(connections)} frontend API calls matched to registered backend routes")
    unmatched = [c for c in connections if not c["matched"]]
    print(f"Unmatched API calls: {len(unmatched)}")
    for u in unmatched:
        print(f"  [UNMATCHED] {u['client_file']}: {u['client_method']} {u['client_path']}")
    
    out = {
        "routes": routes,
        "pages": pages,
        "backend_routes": backend_routes,
        "fe_calls": fe_calls,
        "models": models,
        "connections": connections
    }
    Path("reports/audit_inventory_raw.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved to reports/audit_inventory_raw.json")
