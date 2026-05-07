import os
import httpx
import json
from typing import List, Dict, Any
from models import KimiSuggestion

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_API_URL = os.getenv("KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions")

async def get_kimi_suggestions(mailbox_stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Appelle Kimi API pour obtenir un nombre illimité de suggestions de règles intelligentes."""
    
    print(f"DEBUG: Préparation du prompt pour {mailbox_stats.get('email')}")
    prompt_system = (
        "Tu es l'agent IA 'Meka', un expert mondial en productivité et gestion d'emails. "
        "Ton rôle est d'analyser les statistiques approfondies d'une boîte mail (basées sur l'analyse de milliers de messages) "
        "et de suggérer TOUTES les règles de nettoyage qui te semblent pertinentes. "
        "Il n'y a PAS de limite au nombre de règles. Propose autant de règles que nécessaire pour optimiser parfaitement la boîte. "
        "IMPORTANT: Tu dois rédiger le 'name' et la 'description' EXCLUSIVEMENT en FRANÇAIS. "
        "Sois précis, malin et catégorise bien les types de mails (newsletters, notifications, vieux messages, gros fichiers, etc.). "
        "Réponds UNIQUEMENT en JSON valide avec ce format : "
        "[{'name': string, 'description': string, 'conditions': {'operator': 'AND'|'OR', 'filters': [{'field': 'from'|'older_than'|'size'|'category'|'has', 'value': string}]}}]"
    )
    
    # Préparation des stats détaillées pour le prompt
    top_senders_str = ", ".join([f"{s} ({c} mails)" for s, c in mailbox_stats.get('top_senders', {}).items()])
    stats_summary = (
        f"Stats de la boîte :\n"
        f"- Total messages : {mailbox_stats.get('total_messages')}\n"
        f"- Messages analysés pour cette session : {mailbox_stats.get('total_analyzed')}\n"
        f"- Top expéditeurs détectés : {top_senders_str}\n"
    )
    
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": f"Voici les données d'imprégnation de ma boîte :\n{stats_summary}\nSuggère-moi toutes les règles possibles pour faire le ménage."}
        ],
        "temperature": 0.4
    }
    
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"DEBUG: Envoi de la requête à Kimi ({KIMI_API_URL})...")
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(KIMI_API_URL, json=payload, headers=headers)
            
            if response.status_code != 200:
                print(f"ERROR: Kimi API a répondu {response.status_code}: {response.text}")
                response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            print(f"DEBUG: Réponse brute de Kimi : {content[:200]}...")
            
            # Nettoyage et extraction robuste du JSON
            import re
            # On cherche le premier '[' et le dernier ']'
            json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
            if json_match:
                clean_content = json_match.group(0)
                print("DEBUG: JSON extrait avec succès via regex.")
            else:
                # Fallback nettoyage classique
                clean_content = content.replace("```json", "").replace("```", "").strip()
                print("DEBUG: Pas de match regex, utilisation du nettoyage classique.")
            
            suggestions = json.loads(clean_content)
            print(f"DEBUG: {len(suggestions)} suggestions parsées avec succès.")
            return suggestions
            
    except Exception as e:
        print(f"ERROR Kimi API: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Suggestions par défaut en cas d'erreur
        return [
            {
                "name": "Anciennes newsletters (Fallback)",
                "description": "Supprime les emails de plus de 6 mois (Règle de secours suite à erreur IA)",
                "conditions": {
                    "operator": "AND",
                    "filters": [{"field": "older_than", "value": "6m"}]
                }
            }
        ]
