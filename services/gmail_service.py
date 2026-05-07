import os
import firebase_admin
from firebase_admin import firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from services.firebase_service import save_user_tokens
from services.rule_engine import build_gmail_query, apply_whitelist

def get_gmail_service(access_token: str, refresh_token: str = None, expiry: datetime = None):
    """Initialise le client Gmail API."""
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
    )
    # Si on a un refresh token, on peut forcer un rafraîchissement si nécessaire,
    # mais on va laisser le client gérer pour éviter les crashs de date.
    return build('gmail', 'v1', credentials=creds)

async def clean_mailbox(uid: str, tokens: Dict, rules: List[Dict]) -> Dict[str, Any]:
    """
    Applique les règles selon leur comportement (Auto/Confirm/IA) 
    et respecte la priorité de la règle de protection (r12).
    """
    service = get_gmail_service(
        tokens['access_token'], 
        tokens.get('refresh_token'),
        tokens.get('token_expiry')
    )
    
    total_deleted = 0
    total_size_bytes = 0
    rules_applied = []
    
    # 1. Identifier la Whitelist (Priorité absolue)
    whitelist_ids = set()
    whitelist_rule = next((r for r in rules if r.get('id') == 'r12' and r.get('enabled')), None)
    if whitelist_rule:
        query = build_gmail_query(whitelist_rule)
        if query:
            res = service.users().messages().list(userId='me', q=query, maxResults=1000).execute()
            whitelist_ids = {m['id'] for m in res.get('messages', [])}

    # 2. Traiter les autres règles
    to_delete_auto = set()
    to_confirm = {} # rule_id -> list of msg_ids

    for rule in rules:
        if not rule.get('enabled') or rule.get('id') == 'r12':
            continue
            
        query = build_gmail_query(rule)
        if not query: continue
        
        try:
            results = service.users().messages().list(userId='me', q=query, maxResults=500).execute()
            messages = results.get('messages', [])
            if not messages: continue
            
            msg_ids = {m['id'] for m in messages}
            
            # Appliquer l'exclusion Whitelist immédiatement
            filtered_ids = apply_whitelist(msg_ids, whitelist_ids)
            if not filtered_ids: continue

            behavior = rule.get('behavior', 'automatic')
            if behavior == 'automatic':
                to_delete_auto.update(filtered_ids)
                rules_applied.append(rule['name'])
            elif behavior == 'confirmation':
                to_confirm[rule['id']] = list(filtered_ids)
            elif behavior == 'intelligent':
                # Logique simplifiée pour la démo, on traite comme auto pour l'instant
                # mais on pourrait ajouter du filtrage de doublons ici
                to_delete_auto.update(filtered_ids)
                rules_applied.append(rule['name'])

        except Exception as e:
            print(f"Erreur sur la règle {rule['name']}: {e}")

    # 3. Exécuter la suppression automatique avec calcul de taille réelle
    if to_delete_auto:
        batch_ids = list(to_delete_auto)
        
        # Récupération de la taille réelle (sizeEstimate) pour les 500 premiers (pour garder une bonne performance)
        # On fait une boucle pour sommer les tailles réelles
        for msg_id in batch_ids:
            try:
                # Format 'minimal' ne récupère que l'ID et la taille estimée (très rapide)
                m_info = service.users().messages().get(userId='me', id=msg_id, format='minimal').execute()
                total_size_bytes += m_info.get('sizeEstimate', 0)
            except:
                total_size_bytes += 102400 # Fallback 100KB si erreur
        
        # Suppression effective
        for i in range(0, len(batch_ids), 1000):
            chunk = batch_ids[i:i+1000]
            service.users().messages().batchDelete(userId='me', body={'ids': chunk}).execute()
        
        total_deleted = len(batch_ids)

    return {
        "emails_deleted": total_deleted,
        "space_saved_mb": round(total_size_bytes / (1024 * 1024), 2),
        "rules_applied": rules_applied,
        "pending_confirmation": to_confirm
    }

async def get_mailbox_stats(tokens: Dict) -> Dict[str, Any]:
    """Récupère les statistiques réelles de la boîte mail (Analyse étendue à 4000+ mails)."""
    service = get_gmail_service(tokens['access_token'], tokens.get('refresh_token'))
    
    # 1. Infos globales du profil
    profile = service.users().getProfile(userId='me').execute()
    total_messages = profile.get('messagesTotal', 0)
    email_address = profile.get('emailAddress')
    
    # 2. Récupération massive d'IDs (jusqu'à 4000)
    all_messages = []
    next_page_token = None
    target_count = 4000
    
    print(f"Début de la récupération des IDs (Cible: {target_count})...")
    while len(all_messages) < target_count:
        results = service.users().messages().list(
            userId='me', 
            maxResults=min(500, target_count - len(all_messages)),
            pageToken=next_page_token
        ).execute()
        
        messages = results.get('messages', [])
        all_messages.extend(messages)
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break
            
    print(f"{len(all_messages)} messages trouvés.")
    
    # 3. Analyse par batch pour les expéditeurs (on analyse un échantillon large de 500 pour les stats d'expéditeurs)
    top_senders = {}
    sample_size = min(len(all_messages), 500) 
    sample_messages = all_messages[:sample_size]
    
    def batch_callback(request_id, response, exception):
        if exception is None:
            headers = response.get('payload', {}).get('headers', [])
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Inconnu')
            if '<' in sender:
                sender = sender.split('<')[1].split('>')[0]
            top_senders[sender] = top_senders.get(sender, 0) + 1

    print(f"Analyse de l'échantillon de {sample_size} messages...")
    batch = service.new_batch_http_request(callback=batch_callback)
    for m in sample_messages:
        batch.add(service.users().messages().get(userId='me', id=m['id'], format='metadata', metadataHeaders=['From']))
    
    batch.execute()

    return {
        "total_messages": total_messages,
        "email": email_address,
        "top_senders": dict(sorted(top_senders.items(), key=lambda x: x[1], reverse=True)[:50]), # Top 50 senders
        "total_analyzed": len(all_messages),
        "sample_size": sample_size
    }
