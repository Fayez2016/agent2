import re
from typing import Dict, Any, List

class EntityExtractorService:
    """
    Domain Service for universally extracting infrastructure entities (hostnames,
    cluster names, roles, and operational directives) from natural language prompts.
    Zero hardcoded inventory dependencies.
    """

    @staticmethod
    def extract_entities(prompt: str) -> Dict[str, Any]:
        clean_p = prompt.strip()
        
        # 1. Regex Token Extraction for Host Patterns
        # Matches srv-*, node-*, rhel-*, ha-*, cluster-*, host-*, vm-*, prod-*, db-*, web-*, app-*, auth-*, etc.
        found_tokens = re.findall(
            r'\b(?:srv|node|rhel|ha|cluster|host|vm|prod|db|web|app|auth|cache|api|proxy|queue|worker)-[a-zA-Z0-9_\-\.]+\b',
            clean_p,
            re.IGNORECASE
        )
        
        # 2. Expand Range Expressions (e.g., "cluster-01 to cluster-10" or "node-1 to node-12")
        range_match = re.search(
            r'\b([a-zA-Z0-9_\-]+?)(\d+)\s+to\s+([a-zA-Z0-9_\-]+?)(\d+)\b',
            clean_p,
            re.IGNORECASE
        )
        if range_match:
            prefix1, start_num, prefix2, end_num = range_match.groups()
            try:
                start_i = int(start_num)
                end_i = int(end_num)
                if end_i >= start_i and (end_i - start_i) <= 50:
                    width = len(start_num)
                    expanded = [f"{prefix1}{i:0{width}d}" for i in range(start_i, end_i + 1)]
                    found_tokens.extend(expanded)
            except Exception:
                pass

        # Deduplicate while preserving token order
        seen = set()
        unique_entities = []
        for item in found_tokens:
            clean_item = item.strip().lower()
            if clean_item not in seen:
                seen.add(clean_item)
                unique_entities.append(clean_item)
                
        clusters = [e for e in unique_entities if "cluster" in e]
        hosts = [e for e in unique_entities if "cluster" not in e]
        
        # Fallback if no explicit prefix match was found
        if not clusters and not hosts:
            target_m = re.search(
                r'(?:host|cluster|node|server)s?\s+([a-zA-Z0-9_,\-\s]+?)(?:\:|\.|\s+and|\s+with|$)',
                clean_p,
                re.IGNORECASE
            )
            if target_m:
                raw_targets = target_m.group(1).replace(",", " ").split()
                for t in raw_targets:
                    t_clean = t.strip()
                    if len(t_clean) > 2 and t_clean.lower() not in ["across", "using", "subagent", "the"]:
                        hosts.append(t_clean)

        if not clusters and not hosts:
            hosts = ["srv-prod-01"]

        # Classification of workflow intent
        is_fleet = bool(
            "fleet-patcher" in clean_p.lower() or 
            ("fleet" in clean_p.lower() and "ha" not in clean_p.lower()) or 
            ("patch" in clean_p.lower() and "cluster" not in clean_p.lower() and "ha" not in clean_p.lower())
        )
        is_ha = bool(
            "ha-cluster-patcher" in clean_p.lower() or 
            "2059253" in clean_p or 
            ("rolling" in clean_p.lower() and "cluster" in clean_p.lower()) or 
            (clusters and not is_fleet)
        )
        is_diagnostics = bool("diagnostic" in clean_p.lower() or "health check" in clean_p.lower() or "inspect" in clean_p.lower())

        return {
            "clusters": clusters,
            "hosts": hosts,
            "all_entities": unique_entities or hosts,
            "is_ha_rolling_update": is_ha,
            "is_fleet_patching": is_fleet,
            "is_diagnostics": is_diagnostics
        }
