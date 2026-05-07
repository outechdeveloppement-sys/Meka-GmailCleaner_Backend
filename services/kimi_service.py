import os
import httpx
import json
from typing import List, Dict, Any
from models import KimiSuggestion

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_API_URL = os.getenv("KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions")

async def get_kimi_suggestions(mailbox_stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Appelle Kimi API pour obtenir un nombre illimité de suggestions de règles intelligentes."""
    
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(KIMI_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Nettoyage du contenu si Kimi ajoute des backticks markdown
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            suggestions = json.loads(content)
            return suggestions
            
    except Exception as e:
        print(f"Erreur Kimi API: {e}")
        # Suggestions par dfaut en cas d'erreur
        return [
            {
                "name": "Anciennes newsletters",
                "description": "Supprime les emails de plus de 6 mois",
                "conditions": {
                    "operator": "AND",
                    "filters": [{"field": "older_than", "value": "6m"}]
                }
            }
        ]
