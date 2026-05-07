import os
from dotenv import load_dotenv
load_dotenv()

import platform

# Configuration de l'environnement (Sécurité pour le déploiement sur Render/Linux)
if platform.system() == "Windows" and os.getenv("SSL_CERT_FILE"):
    os.environ["SSL_CERT_FILE"] = os.getenv("SSL_CERT_FILE")
    os.environ["REQUESTS_CA_BUNDLE"] = os.getenv("SSL_CERT_FILE")

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
# Autoriser le HTTP pour le développement local (Google OAuth)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import des routes
from routes import auth, analyze, clean

app = FastAPI(title="GmailCleaner API")

# Configuration CORS ultra-flexible pour Vercel et Local
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://meka-gmail-cleaner-frontend-o3fd.vercel.app",
]

# Ajout dynamique de l'URL d'environnement
env_url = os.getenv("FRONTEND_URL")
if env_url:
    origins.append(env_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Autorise tous les domaines Vercel de ton projet (preview et prod)
    allow_origin_regex=r"https://meka-gmail-cleaner-frontend.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routers
app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(clean.router)

@app.get("/")
async def root():
    return {"message": "GmailCleaner API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
