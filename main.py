from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from groq import Groq

import os
from dotenv import load_dotenv

# Carga el archivo local solo si existe (para desarrollo en tu PC)
if os.path.exists("atlas-credentials.env"):
    load_dotenv("atlas-credentials.env")
elif os.path.exists(".env"):
    load_dotenv(".env")

app = FastAPI(title="API de R.O.B.", version="1.0")

# --- CONFIGURACIÓN DE CORS (Vital para que el frontend se comunique) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite peticiones desde cualquier origen (tu HTML local)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN DE CREDENCIALES ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGODB_URI")

# Validación rápida para saber si faltan credenciales
if not GROQ_API_KEY or not MONGO_URI:
    print("⚠️ ADVERTENCIA: Faltan las variables de entorno GROQ_API_KEY o MONGODB_URI.")

groq_client = Groq(api_key=GROQ_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["rob_database"]
memoria_col = db["user_memory"]

class MensajeUsuario(BaseModel):
    user_id: str
    mensaje: str

# --- RUTA PRINCIPAL ---
@app.get("/")
def leer_raiz():
    return {"mensaje": "¡Hola! R.O.B. está en línea y listo para operar."}

# --- RUTA DEL CHAT ---
@app.post("/chat")
def chatear_con_rob(datos: MensajeUsuario):
    try:
        perfil_usuario = memoria_col.find_one({"user_id": datos.user_id})
        contexto_memoria = perfil_usuario.get("preferencias", "No hay datos previos.") if perfil_usuario else "Es un usuario nuevo."

        system_prompt = (
            "Eres R.O.B., una inteligencia artificial avanzada, amigable y servicial alojada en la nube. "
            f"Información que ya conoces sobre este usuario: {contexto_memoria}. "
            "Si el usuario te dice algo importante sobre él (su nombre, gustos, profesión), "
            "añade al final de tu respuesta la etiqueta [RECORDAR: lo que debo recordar]."
        )

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": datos.mensaje}
            ],
            temperature=0.7
        )
        
        respuesta_rob = completion.choices[0].message.content

        if "[RECORDAR:" in respuesta_rob:
            partes = respuesta_rob.split("[RECORDAR:")
            respuesta_limpia = partes[0].strip()
            nuevo_dato = partes[1].replace("]", "").strip()
            
            memoria_col.update_one(
                {"user_id": datos.user_id},
                {"$set": {"preferencias": f"{contexto_memoria}; {nuevo_dato}"}},
                upsert=True
            )
            respuesta_rob = respuesta_limpia
        else:
            respuesta_rob = respuesta_rob.strip()

        return {"rob_response": respuesta_rob}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

