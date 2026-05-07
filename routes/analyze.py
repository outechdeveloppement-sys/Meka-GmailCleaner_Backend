from fastapi import APIRouter, Request, HTTPException, Header
from services.firebase_service import verify_firebase_token, get_user_tokens
from services.gmail_service import get_mailbox_stats
from services.kimi_service import get_kimi_suggestions
from typing import Optional

router = APIRouter(prefix="/analyze", tags=["analyze"])

@router.post("")
async def analyze_mailbox(authorization: Optional[str] = Header(None)):
    """Analyse la boîte mail et suggère des règles via Kimi AI."""
    print("--- DÉBUT DE L'ANALYSE ---")
    try:
        if not authorization or not authorization.startswith("Bearer "):
            print("ERROR: Authorization header manquant ou invalide")
            raise HTTPException(status_code=401, detail="Token manquant")
        
        id_token = authorization.split(" ")[1]
        print("DEBUG: Vérification du token Firebase...")
        user_info = verify_firebase_token(id_token)
        if not user_info:
            print("ERROR: Token Firebase invalide")
            raise HTTPException(status_code=401, detail="Token invalide")
        
        uid = user_info['uid']
        print(f"DEBUG: Analyse demandée pour UID: {uid} ({user_info.get('email', 'N/A')})")
        
        # Récupération des tokens Gmail
        print("DEBUG: Récupération des tokens Gmail depuis Firestore...")
        tokens = await get_user_tokens(uid)
        if not tokens:
            print("ERROR: Gmail non connecté pour cet utilisateur")
            raise HTTPException(status_code=400, detail="Gmail non connecté")
        
        # Récupération des stats réelles
        print("DEBUG: Récupération des statistiques Gmail (Batch metadata)...")
        stats = await get_mailbox_stats(tokens)
        print(f"DEBUG: Stats récupérées: {stats.get('total_analyzed')} messages analysés.")
        
        # Suggestions IA
        print("DEBUG: Envoi des stats à Kimi AI...")
        suggestions = await get_kimi_suggestions(stats)
        
        print(f"--- ANALYSE TERMINÉE AVEC SUCCÈS ({len(suggestions)} suggestions) ---")
        return {"suggestions": suggestions}

    except HTTPException as he:
        # On relance les exceptions HTTP pour que FastAPI les gère normalement
        print(f"HTTP ERROR: {he.detail}")
        raise he
    except Exception as e:
        print(f"CRITICAL CRASH ANALYZE: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de l'analyse: {str(e)}")
