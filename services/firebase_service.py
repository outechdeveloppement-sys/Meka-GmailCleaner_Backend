import os
import json
import base64
from datetime import datetime
from typing import Optional, List, Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore, auth
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

DEFAULT_RULES = [
    {
        "id": "r1",
        "name": "Ancienneté des emails",
        "description": "Supprime les emails plus anciens qu'un seuil défini.",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "older_than", "value": "12m", "label": "Supprimer si plus vieux que"},
        "category": "Nettoyage de base"
    },
    {
        "id": "r2",
        "name": "Nettoyage Promotions",
        "description": "Supprime les emails de l'onglet Promotions (publicités, offres).",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "category", "value": "promotions", "label": "Catégorie Gmail"},
        "category": "Nettoyage de base"
    },
    {
        "id": "r3",
        "name": "Newsletters non lues",
        "description": "Newsletters jamais ouvertes. Validation requise avant suppression.",
        "behavior": "confirmation",
        "enabled": True,
        "config": {"field": "unread_for", "value": "30d", "label": "Non lu depuis"},
        "category": "Newsletters"
    },
    {
        "id": "r4",
        "name": "Expéditeurs bloqués",
        "description": "Supprime automatiquement les emails d'une liste noire.",
        "behavior": "automatic",
        "enabled": False,
        "config": {"field": "blocked_list", "value": [], "label": "Expéditeurs bloqués"},
        "category": "Sécurité"
    },
    {
        "id": "r5",
        "name": "Pièces jointes volumineuses",
        "description": "Repère les emails avec des pièces jointes lourdes.",
        "behavior": "confirmation",
        "enabled": True,
        "config": {"field": "size_gt", "value": "5M", "label": "Taille minimale PJ"},
        "category": "Espace"
    },
    {
        "id": "r6",
        "name": "Notifications automatiques",
        "description": "Supprime les emails d'alerte (noreply, notifications).",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "noreply_types", "value": ["noreply", "no-reply", "alert"], "label": "Expéditeurs type"},
        "category": "Nettoyage de base"
    },
    {
        "id": "r7",
        "name": "Doublons d'emails",
        "description": "Détecte et supprime les copies identiques d'un même email.",
        "behavior": "intelligent",
        "enabled": False,
        "config": {"field": "similarity", "value": "100%", "label": "Tolérance similarité"},
        "category": "IA"
    },
    {
        "id": "r8",
        "name": "Confirmations de commande",
        "description": "Cible les reçus et achats après conservation.",
        "behavior": "confirmation",
        "enabled": True,
        "config": {"field": "keep_for", "value": "6m", "label": "Conserver pendant"},
        "category": "Archives"
    },
    {
        "id": "r9",
        "name": "Fils de discussion terminés",
        "description": "Analyse les fils de conversation inactifs.",
        "behavior": "intelligent",
        "enabled": False,
        "config": {"field": "inactive_for", "value": "90d", "label": "Inactif depuis"},
        "category": "IA"
    },
    {
        "id": "r10",
        "name": "Dossier spam & indésirables",
        "description": "Vide périodiquement les dossiers Spam et Corbeille.",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "frequency", "value": "always", "label": "Fréquence"},
        "category": "Espace"
    },
    {
        "id": "r11",
        "name": "Emails sans label ni étoile",
        "description": "Supprime les emails sans aucune organisation.",
        "behavior": "intelligent",
        "enabled": False,
        "config": {"field": "unorganized_since", "value": "6m", "label": "Non organisés depuis"},
        "category": "IA"
    },
    {
        "id": "r12",
        "name": "Protection des contacts importants",
        "description": "Liste blanche PRIORITAIRE à ne jamais supprimer.",
        "behavior": "confirmation",
        "enabled": True,
        "config": {"field": "whitelist", "value": [], "label": "Contacts protégés"},
        "category": "Sécurité",
        "is_priority": True
    },
    {
        "id": "r13",
        "name": "Nettoyage Réseaux Sociaux",
        "description": "Supprime les notifications de Facebook, LinkedIn, Twitter, etc.",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "category", "value": "social", "label": "Catégorie Gmail"},
        "category": "Nettoyage de base"
    },
    {
        "id": "r14",
        "name": "Nettoyage Notifications",
        "description": "Supprime les alertes et notifications de l'onglet Mises à jour.",
        "behavior": "automatic",
        "enabled": True,
        "config": {"field": "category", "value": "updates", "label": "Catégorie Gmail"},
        "category": "Nettoyage de base"
    }
]
from dotenv import load_dotenv

load_dotenv()

# Initialisation de Firebase Admin SDK
# Le service account JSON est stocké dans une variable d'environnement
cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if cred_json and "..." not in cred_json:
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
    except json.JSONDecodeError as e:
        print(f"CRITICAL ERROR: FIREBASE_SERVICE_ACCOUNT_JSON in .env is not a valid JSON string.")
        print(f"Details: {e}")
        print("Please make sure you copied the entire content of your service account JSON file on a single line.")
        cred_json = None # Force fallback
else:
    if cred_json and "..." in cred_json:
        print("WARNING: FIREBASE_SERVICE_ACCOUNT_JSON contains placeholder '...'. Please fill it in .env")

    # Fallback pour le dveloppement local si le fichier existe
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

db = firestore.client()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef") # 32 bytes hex

def encrypt_token(token: str) -> str:
    """Chiffre un token Gmail en AES-256-CBC."""
    key = bytes.fromhex(ENCRYPTION_KEY)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(token.encode()) + padder.finalize()
    
    encrypted_token = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(iv + encrypted_token).decode('utf-8')

def decrypt_token(encrypted_data: str) -> str:
    """Dchiffre un token Gmail."""
    key = bytes.fromhex(ENCRYPTION_KEY)
    raw_data = base64.b64decode(encrypted_data)
    iv = raw_data[:16]
    actual_encrypted = raw_data[16:]
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    
    decrypted_padded = decryptor.update(actual_encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    decrypted_data = unpadder.update(decrypted_padded) + unpadder.finalize()
    
    return decrypted_data.decode('utf-8')

async def get_user_tokens(uid: str) -> Optional[Dict]:
    """Rcupre les tokens OAuth Gmail d'un utilisateur."""
    doc = db.collection('users').document(uid).get()
    if doc.exists:
        data = doc.to_dict()
        if 'oauth_token_encrypted' in data:
            return {
                'access_token': decrypt_token(data['oauth_token_encrypted']),
                'refresh_token': data.get('oauth_refresh_token'),
                'token_expiry': data.get('token_expiry')
            }
    return None

async def save_user_tokens(uid: str, access_token: str, refresh_token: Optional[str], expiry: datetime):
    """Sauvegarde les tokens OAuth Gmail chiffrs."""
    data = {
        'oauth_token_encrypted': encrypt_token(access_token),
        'token_expiry': expiry,
        'gmailConnected': True
    }
    if refresh_token:
        data['oauth_refresh_token'] = refresh_token
        
    db.collection('users').document(uid).set(data, merge=True)
    
    # Initialiser les rgles par dfaut si elles n'existent pas
    rules_ref = db.collection('users').document(uid).collection('rules')
    existing_rules = rules_ref.limit(1).get()
    
    if len(existing_rules) == 0:
        batch = db.batch()
        for rule in DEFAULT_RULES:
            new_rule_ref = rules_ref.document(rule['id'])
            batch.set(new_rule_ref, {
                **rule,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "emailsDeleted": 0,
                "lastRun": None
            })
        batch.commit()

async def get_user_rules(uid: str) -> List[Dict]:
    """Rcupre la liste des rgles d'un utilisateur."""
    rules_ref = db.collection('users').document(uid).collection('rules')
    rules = []
    for doc in rules_ref.where('enabled', '==', True).stream():
        rule_data = doc.to_dict()
        rule_data['id'] = doc.id
        rules.append(rule_data)
    return rules

async def log_history(uid: str, job_data: Dict):
    """Enregistre une excution dans l'historique."""
    db.collection('users').document(uid).collection('history').add({
        'executedAt': firestore.SERVER_TIMESTAMP,
        **job_data
    })
    
    # Mettre à jour le compteur global de l'utilisateur
    user_ref = db.collection('users').document(uid)
    user_ref.update({
        'totalEmailsDeleted': firestore.Increment(job_data.get('emails_deleted', 0)),
        'totalSpaceSavedMB': firestore.Increment(job_data.get('space_saved_mb', 0))
    })

def verify_firebase_token(id_token: str):
    """Vrifie le Firebase ID Token envoy par le frontend."""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Erreur de dcodage du token: {e}")
        return None
