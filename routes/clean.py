from fastapi import APIRouter, Request, HTTPException, Header
from services.firebase_service import verify_firebase_token, get_user_tokens, get_user_rules, log_history
from services.gmail_service import clean_mailbox
from typing import Optional

router = APIRouter(prefix="/clean", tags=["clean"])

@router.post("")
async def execute_clean(authorization: Optional[str] = Header(None)):
    """Lance le nettoyage bas sur les rgles actives de l'utilisateur."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    
    id_token = authorization.split(" ")[1]
    user_info = verify_firebase_token(id_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    uid = user_info['uid']
    
    # 1. Rcuprer les tokens
    tokens = await get_user_tokens(uid)
    if not tokens:
        raise HTTPException(status_code=400, detail="Gmail non connect")
    
    # 2. Rcuprer les rgles actives
    rules = await get_user_rules(uid)
    if not rules:
        return {"status": "no_rules_active", "emails_deleted": 0}
    
    # 3. Excuter le nettoyage
    result = await clean_mailbox(uid, tokens, rules)
    
    # 4. Enregistrer dans l'historique
    await log_history(uid, result)
    
    return result
