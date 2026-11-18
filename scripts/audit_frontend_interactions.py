#!/usr/bin/env python3
"""
scripts/audit_frontend_interactions.py
--------------------------------------
Discovers and audits all routes, pages, components, buttons, forms, modals,
and API integrations in the RIO-MJP frontend codebase.
"""

import os
import re
import json
from pathlib import Path

PAGES_DIR = Path("frontend/src/pages")
COMPONENTS_DIR = Path("frontend/src/components")
LAYOUTS_DIR = Path("frontend/src/layouts")
ROUTES_FILE = Path("frontend/src/routes/AppRoutes.tsx")
API_DIR = Path("frontend/src/api")

def analyze_file(filepath: Path):
    text = filepath.read_text(encoding="utf-8")
    
    # Buttons
    button_matches = re.findall(r'<button\b([^>]*)>(.*?)</button>', text, re.DOTALL)
    icon_button_matches = re.findall(r'<IconButton\b([^>]*)/?>', text)
    refresh_button_matches = re.findall(r'<RefreshButton\b([^>]*)/?>', text)
    custom_button_matches = re.findall(r'<[A-Z][a-zA-Z0-9]*Button\b([^>]*)/?>', text)
    
    # Links
    link_matches = re.findall(r'<(?:Link|NavLink)\b([^>]*)(?:>(.*?)</(?:Link|NavLink)>|/>)', text, re.DOTALL)
    
    # Forms
    form_matches = re.findall(r'<form\b([^>]*)>(.*?)</form>', text, re.DOTALL)
    
    # Modals / Dialogs
    modal_matches = re.findall(r'<(?:FormModal|ConfirmDialog|SignOutConfirmDialog|[A-Za-z0-9]*Modal|[A-Za-z0-9]*Dialog)\b([^>]*)/?>', text)
    
    # onClicks
    onclick_matches = re.findall(r'onClick=\{([^}]+)\}', text)
    
    # API calls / React Query hooks
    use_query_matches = re.findall(r'useQuery\(\{([^}]+)\}\)', text, re.DOTALL)
    use_mutation_matches = re.findall(r'useMutation\(\{([^}]+)\}\)', text, re.DOTALL)
    
    # Find all api client imports
    api_imports = re.findall(r'import\s+\{([^}]+)\}\s+from\s+[\'"]@/api/[^\'"]+[\'"]', text)
    api_fns = []
    for imp in api_imports:
        for fn in imp.split(','):
            fn = fn.strip()
            if fn and not fn.startswith('type '):
                api_fns.append(fn)

    return {
        "file": str(filepath).replace("\\", "/"),
        "buttons_count": len(button_matches) + len(icon_button_matches) + len(refresh_button_matches),
        "button_details": [
            {
                "props": b[0].strip().replace('\n', ' '),
                "content": re.sub(r'<[^>]+>', '', b[1]).strip()[:60]
            }
            for b in button_matches[:10]
        ],
        "links_count": len(link_matches),
        "forms_count": len(form_matches),
        "modals_count": len(modal_matches),
        "onclick_count": len(onclick_matches),
        "use_query_count": len(use_query_matches),
        "use_mutation_count": len(use_mutation_matches),
        "api_functions": list(set(api_fns))
    }

def main():
    pages_audit = {}
    for p in sorted(PAGES_DIR.glob("**/*.tsx")):
        rel = str(p.relative_to(PAGES_DIR)).replace("\\", "/")
        pages_audit[rel] = analyze_file(p)

    components_audit = {}
    for c in sorted(COMPONENTS_DIR.glob("**/*.tsx")):
        rel = str(c.relative_to(COMPONENTS_DIR)).replace("\\", "/")
        components_audit[rel] = analyze_file(c)

    layouts_audit = {}
    for l in sorted(LAYOUTS_DIR.glob("**/*.tsx")):
        rel = str(l.relative_to(LAYOUTS_DIR)).replace("\\", "/")
        layouts_audit[rel] = analyze_file(l)

    summary = {
        "total_pages": len(pages_audit),
        "total_components": len(components_audit),
        "total_layouts": len(layouts_audit),
        "total_page_buttons": sum(p["buttons_count"] for p in pages_audit.values()),
        "total_component_buttons": sum(c["buttons_count"] for c in components_audit.values()),
        "total_page_forms": sum(p["forms_count"] for p in pages_audit.values()),
        "total_page_modals": sum(p["modals_count"] for p in pages_audit.values()),
        "total_page_queries": sum(p["use_query_count"] for p in pages_audit.values()),
        "total_page_mutations": sum(p["use_mutation_count"] for p in pages_audit.values()),
    }

    result = {
        "summary": summary,
        "pages": pages_audit,
        "components": components_audit,
        "layouts": layouts_audit
    }

    out_file = Path("reports/discovered_frontend_interactions.json")
    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
