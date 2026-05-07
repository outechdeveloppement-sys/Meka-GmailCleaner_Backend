from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
import requests
from services.firebase_service import save_user_tokens, verify_firebase_token, auth as firebase_auth
from services.firebase_service import db
import os
import json
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["auth"])

# Configuration OAuth Google
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
REDIRECT_URI = f"{frontend_url}/auth/callback"

print(f"DEBUG: Frontend URL configurée: {frontend_url}")
print(f"DEBUG: Redirect URI configurée: {REDIRECT_URI}")

GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [REDIRECT_URI],
        "project_id": os.getenv("FIREBASE_PROJECT_ID")
    }
}

SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid',
    'https://mail.google.com/'
]

@router.get("/google-login")
async def google_login():
    """Gnre l'URL d'autorisation Google."""
    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=GOOGLE_CLIENT_CONFIG["web"]["redirect_uris"][0]
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return {"url": authorization_url}

@router.post("/callback")
async def auth_callback(request: Request):
    """Gère le retour de Google OAuth, lie Gmail et connecte à Firebase."""
    data = await request.json()
    code = data.get("code")
    
    # Échange le code contre des tokens Google
    try:
        print(f"DEBUG: Tentative d'échange du code: {code[:10]}...")
        flow = Flow.from_client_config(
            GOOGLE_CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        print("DEBUG: Échange de token réussi !")
    except Exception as e:
        print(f"DEBUG: ÉCHEC ÉCHANGE TOKEN: {type(e).__name__}: {str(e)}")
        # Si on a une erreur redirect_uri_mismatch, c'est que l'URL dans Google Console ne correspond pas
        raise HTTPException(status_code=401, detail=f"Erreur Google: {str(e)}")
    
    # RÉCUPÉRATION DIRECTE (Décision drastique : ignore l'horloge système)
    try:
        userinfo_res = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"}
        )
        user_info = userinfo_res.json()
        
        email = user_info.get("email")
        display_name = user_info.get("name")
        photo_url = user_info.get("picture")
        
        if not email:
            raise Exception("Email non trouvé dans la réponse Google")
            
        print(f"DEBUG: Connexion réussie pour {email}")
    except Exception as e:
        print(f"DEBUG: Erreur lors de la récupération UserInfo: {e}")
        raise HTTPException(status_code=401, detail=f"Erreur d'identité Google: {str(e)}")
    
    if not email:
        raise HTTPException(status_code=400, detail="Impossible de récupérer l'email Google")

    # 1. Créer ou récupérer l'utilisateur dans Firebase Auth (côté serveur)
    try:
        user = firebase_auth.get_user_by_email(email)
        # Mettre à jour l'avatar si nécessaire
        firebase_auth.update_user(user.uid, display_name=display_name, photo_url=photo_url)
    except Exception:
        user = firebase_auth.create_user(
            email=email, 
            display_name=display_name,
            photo_url=photo_url
        )

    uid = user.uid

    # 2. Sauvegarder les tokens Gmail
    await save_user_tokens(
        uid, 
        creds.token, 
        creds.refresh_token, 
        creds.expiry
    )
    
    # 3. Générer un Token Firebase Personnalisé pour le Frontend
    custom_token = firebase_auth.create_custom_token(uid)
    
    return {
        "status": "success", 
        "firebase_token": custom_token.decode('utf-8') if isinstance(custom_token, bytes) else custom_token,
        "email": email,
        "displayName": display_name,
        "photoURL": photo_url
    }

@router.post("/init-rules")
async def init_rules(request: Request):
    """Initialise les règles par défaut si elles sont manquantes."""
    data = await request.json()
    firebase_token = data.get("id_token")
    
    user_info = verify_firebase_token(firebase_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Utilisateur non authentifié")
    
    uid = user_info['uid']
    
    # Réutiliser la logique d'initialisation de firebase_service
    from services.firebase_service import DEFAULT_RULES, firestore
    # Ajouter ou mettre à jour les règles manquantes individuellement
    rules_ref = db.collection('users').document(uid).collection('rules')
    batch = db.batch()
    added_count = 0
    
    for rule in DEFAULT_RULES:
        rule_ref = rules_ref.document(rule['id'])
        # On ne vérifie pas si elle existe déjà pour forcer la mise à jour/ajout des nouvelles par ID
        batch.set(rule_ref, {
            **rule,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "emailsDeleted": 0,
            "lastRun": None
        }, merge=True)
        added_count += 1
        
    batch.commit()
    return {"status": "success", "count": added_count}
