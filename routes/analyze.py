from fastapi import APIRouter, Request, HTTPException, Header
from services.firebase_service import verify_firebase_token, get_user_tokens
from services.gmail_service import get_mailbox_stats
from services.kimi_service import get_kimi_suggestions
from typing import Optional

router = APIRouter(prefix="/analyze", tags=["analyze"])

@router.post("")
async def analyze_mailbox(authorization: Optional[str] = Header(None)):
    """Analyse la boîte mail et suggère des règles via Kimi AI."""
    print("Début de l'analyse...")
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token manquant")
        
        id_token = authorization.split(" ")[1]
        user_info = verify_firebase_token(id_token)
        if not user_info:
            raise HTTPException(status_code=401, detail="Token invalide")
        
        uid = user_info['uid']
        print(f"Analyse demandée pour UID: {uid}")
        
        # Récupération des tokens Gmail
        tokens = await get_user_tokens(uid)
        if not tokens:
            raise HTTPException(status_code=400, detail="Gmail non connecté")
        
        # Récupération des stats réelles
        print("Récupération des statistiques Gmail...")
        stats = await get_mailbox_stats(tokens)
        
        # Suggestions IA
        print("Appel à Kimi AI pour les suggestions...")
        suggestions = await get_kimi_suggestions(stats)
        
        print("Analyse terminée avec succès.")
        return {"suggestions": suggestions}

    except Exception as e:
        print(f"CRASH ANALYZE: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
