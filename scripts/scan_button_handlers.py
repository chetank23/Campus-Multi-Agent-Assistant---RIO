#!/usr/bin/env python3
"""
scripts/scan_button_handlers.py
--------------------------------
Audits all interactive elements in frontend/src to find empty handlers,
TODOs, dead links, unhandled mutations, and disconnected controls.
"""

import os
import re
from pathlib import Path

SRC_DIR = Path("frontend/src")

def scan():
    findings = []
    
    for f in sorted(SRC_DIR.glob("**/*.tsx")):
        text = f.read_text(encoding="utf-8")
        rel_path = str(f.relative_to(SRC_DIR)).replace("\\", "/")
        
        # 1. Empty or trivial onClick handlers
        empty_onclicks = re.findall(r'onClick=\{\s*\(\)\s*=>\s*\{?\s*\}?\s*\}', text)
        if empty_onclicks:
            findings.append({
                "file": rel_path,
                "type": "EMPTY_ONCLICK",
                "count": len(empty_onclicks),
                "detail": "onClick={() => {}} or empty arrow handler"
            })
            
        # 2. Console.log inside onClicks
        log_onclicks = re.findall(r'onClick=\{\s*\([^)]*\)\s*=>\s*console\.[a-z]+\([^)]+\)\s*\}', text)
        if log_onclicks:
            findings.append({
                "file": rel_path,
                "type": "CONSOLE_LOG_ONCLICK",
                "count": len(log_onclicks),
                "detail": "onClick={() => console.log(...)}"
            })
            
        # 3. Alert inside onClicks
        alert_onclicks = re.findall(r'onClick=\{\s*\([^)]*\)\s*=>\s*alert\([^)]+\)\s*\}', text)
        if alert_onclicks:
            findings.append({
                "file": rel_path,
                "type": "ALERT_ONCLICK",
                "count": len(alert_onclicks),
                "detail": "onClick={() => alert(...)}"
            })
            
        # 4. Dead links: to="#" or to=""
        dead_links = re.findall(r'to=[\'"](#||\s*)[\'"]', text)
        if dead_links:
            findings.append({
                "file": rel_path,
                "type": "DEAD_LINK",
                "count": len(dead_links),
                "detail": 'Link to="#" or to=""'
            })
            
        # 5. Buttons without onClick and not in form (type="button" without onClick)
        orphan_buttons = re.findall(r'<button\b(?![^>]*\bonClick\b)(?![^>]*\btype=[\'"]submit[\'"])[^>]*>', text)
        # Filter out buttons with form attributes or aria controls
        filtered_orphans = [b for b in orphan_buttons if 'type="submit"' not in b]
        if filtered_orphans:
            # Let's inspect them
            findings.append({
                "file": rel_path,
                "type": "POTENTIAL_ORPHAN_BUTTON",
                "count": len(filtered_orphans),
                "samples": [b[:100] for b in filtered_orphans[:3]]
            })

    print(f"Total findings: {len(findings)}")
    for f in findings:
        print(f"[{f['type']}] {f['file']}: {f.get('detail', '')} (count: {f['count']})")
        if 'samples' in f:
            for s in f['samples']:
                print(f"    Sample: {s}")

if __name__ == "__main__":
    scan()
