from typing import Dict, Any, List

def build_gmail_query(rule: Dict[str, Any]) -> str:
    """
    Traduit une règle (statique ou dynamique de l'IA) en query Gmail.
    Supporte l'ancien format 'config' et le nouveau format 'conditions'.
    """
    query_parts = []
    
    # 1. Gestion du nouveau format 'conditions' (IA / Kimi)
    if 'conditions' in rule:
        conds = rule['conditions']
        operator = conds.get('operator', 'AND')
        filters = conds.get('filters', [])
        
        parts = []
        for f in filters:
            field = f.get('field')
            value = f.get('value')
            
            if field == 'from':
                parts.append(f'from:{value}')
            elif field == 'older_than':
                parts.append(f'older_than:{value}')
            elif field == 'size':
                parts.append(f'larger:{value}')
            elif field == 'category':
                parts.append(f'category:{value}')
            elif field == 'has':
                parts.append(f'has:{value}')
            elif field == 'subject':
                parts.append(f'subject:{value}')

        if parts:
            joiner = " " if operator == 'AND' else " OR "
            query_parts.append(f"({' '.join(parts)})" if operator == 'AND' else f"({' OR '.join(parts)})")

    # 2. Gestion de l'ancien format 'config' (Règles statiques par défaut)
    elif 'config' in rule:
        config = rule.get('config', {})
        field = config.get('field')
        value = config.get('value')
        
        if field == 'older_than':
            query_parts.append(f'older_than:{value}')
        elif field == 'category':
            query_parts.append(f'category:{value}')
        elif field == 'unread_for':
            query_parts.append(f'is:unread older_than:{value}')
        elif field == 'blocked_list' and value:
            emails = " OR ".join(value)
            query_parts.append(f'from:({emails})')
        elif field == 'size_gt':
            query_parts.append(f'larger:{value}')
        elif field == 'noreply_types':
            types = " OR ".join(value)
            query_parts.append(f'from:({types})')
        elif field == 'keep_for':
            query_parts.append(f'(subject:confirmation OR subject:commande OR subject:reçu OR subject:purchase) older_than:{value}')
        elif field == 'frequency' and value == 'always':
            query_parts.append('in:spam OR in:trash')
        elif field == 'unorganized_since':
            query_parts.append(f'-is:starred -has:userlabels older_than:{value}')
        elif field == 'whitelist' and value:
            emails = " OR ".join(value)
            query_parts.append(f'from:({emails})')

    # 3. Application des exclusions globales (Sécurité)
    base_exclude = "-is:starred -is:important"
    if not query_parts: return ""
    return f"{' '.join(query_parts)} {base_exclude}"

def apply_whitelist(message_ids: set, whitelist_ids: set) -> set:
    """
    Retire les messages protégés de la liste de suppression.
    """
    return message_ids - whitelist_ids
