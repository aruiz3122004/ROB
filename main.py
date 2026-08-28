from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient
from groq import Groq

import os
import datetime
import hashlib
from dotenv import load_dotenv

# Carga el archivo local solo si existe (para desarrollo en tu PC)
if os.path.exists("atlas-credentials.env"):
    load_dotenv("atlas-credentials.env")
elif os.path.exists(".env"):
    load_dotenv(".env")

app = FastAPI(title="API de R.O.B.", version="1.0")

# --- CONFIGURACIÓN DE CORS (Vital para que el frontend de Vercel/Local se comunique) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite peticiones desde cualquier origen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN DE CREDENCIALES ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGODB_URI")

# Validación de credenciales
if not GROQ_API_KEY or not MONGO_URI:
    print("⚠️ ADVERTENCIA: Faltan las variables de entorno GROQ_API_KEY o MONGODB_URI.")

groq_client = Groq(api_key=GROQ_API_KEY)
mongo_client = MongoClient(MONGO_URI)

# Selección de Base de Datos y Colecciones en MongoDB Atlas
db = mongo_client["rob_database"]
users_col = db["users"]
conversations_col = db["conversations"]
messages_col = db["messages"]
memoria_col = db["user_memory"]

# ------------------------------------------------------------------
# Modelos de Datos (Pydantic)
# ------------------------------------------------------------------

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: Optional[str] = None

class ChatRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    mensaje: str
    image_data: Optional[str] = None

class ChatResponse(BaseModel):
    rob_response: str
    conversation_id: str

# ------------------------------------------------------------------
# Endpoints Requeridos
# ------------------------------------------------------------------

@app.get("/")
def leer_raiz():
    return {"mensaje": "¡Hola! R.O.B. está en línea y conectado a MongoDB Atlas."}

@app.post("/register")
def register_user(user: UserRegister):
    """
    Crea un usuario en la colección 'users' de MongoDB Atlas.
    """
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Usuario y contraseña son requeridos")

    username_clean = user.username.strip()
    
    # Verificar si el usuario ya existe
    if users_col.find_one({"username": username_clean}):
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está registrado en la base de datos")

    # Hashear contraseña para almacenamiento seguro
    pwd_hash = hashlib.sha256(user.password.encode('utf-8')).hexdigest()

    user_doc = {
        "username": username_clean,
        "password_hash": pwd_hash,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    users_col.insert_one(user_doc)

    return {
        "status": "success",
        "message": f"Usuario {username_clean} registrado con éxito en MongoDB Atlas"
    }

@app.post("/login")
def login_user(user: UserLogin):
    """
    Valida credenciales de un usuario existente.
    """
    username_clean = user.username.strip()
    db_user = users_col.find_one({"username": username_clean})
    
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en la base de datos")

    if user.password:
        pwd_hash = hashlib.sha256(user.password.encode('utf-8')).hexdigest()
        if db_user.get("password_hash") != pwd_hash:
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    return {
        "status": "success",
        "username": username_clean,
        "message": f"Usuario {username_clean} autenticado correctamente"
    }

@app.post("/chat", response_model=ChatResponse)
def chatear_con_rob(datos: ChatRequest):
    """
    Recibe mensaje, almacena en MongoDB Atlas, consulta la IA R.O.B. y guarda el historial.
    """
    try:
        conv_id = datos.conversation_id or f"chat_{int(datetime.datetime.now().timestamp())}"
        now_iso = datetime.datetime.utcnow().isoformat()

        # 1. Guardar mensaje del usuario en MongoDB ('messages')
        user_msg_doc = {
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "user",
            "content": datos.mensaje,
            "image_data": datos.image_data,
            "created_at": now_iso
        }
        messages_col.insert_one(user_msg_doc)

        # 2. Crear o actualizar la conversación en MongoDB ('conversations')
        conversations_col.update_one(
            {"conversation_id": conv_id},
            {
                "$set": {
                    "user_id": datos.user_id,
                    "updated_at": now_iso
                },
                "$setOnInsert": {
                    "conversation_id": conv_id,
                    "title": datos.mensaje[:35] + ("..." if len(datos.mensaje) > 35 else ""),
                    "created_at": now_iso
                }
            },
            upsert=True
        )

        # 3. Consultar memoria a largo plazo del usuario ('user_memory')
        perfil_usuario = memoria_col.find_one({"user_id": datos.user_id})
        contexto_memoria = perfil_usuario.get("preferencias", "No hay datos previos.") if perfil_usuario else "Es un usuario nuevo."

        system_prompt = (
            "Eres R.O.B., una inteligencia artificial avanzada, amigable y servicial alojada en la nube. "
            f"Información que ya conoces sobre este usuario: {contexto_memoria}. "
            "Si el usuario te dice algo importante sobre él (su nombre, gustos, profesión), "
            "añade al final de tu respuesta la etiqueta [RECORDAR: lo que debo recordar]."
        )

        messages_payload = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": datos.mensaje}
        ]

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages_payload,
            temperature=0.7
        )

        respuesta_rob = completion.choices[0].message.content

        # 4. Actualizar memoria si R.O.B. genera una etiqueta [RECORDAR: ...]
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

        # 5. Guardar respuesta del bot en MongoDB ('messages')
        bot_msg_doc = {
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "bot",
            "content": respuesta_rob,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        messages_col.insert_one(bot_msg_doc)

        return ChatResponse(
            rob_response=respuesta_rob,
            conversation_id=conv_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_id}")
def get_user_history(user_id: str):
    """
    Retorna todas las conversaciones e historial de mensajes de MongoDB Atlas para un usuario.
    """
    try:
        conversations = list(conversations_col.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1))
        
        for conv in conversations:
            msgs = list(messages_col.find({"conversation_id": conv["conversation_id"]}, {"_id": 0}).sort("created_at", 1))
            conv["messages"] = msgs

        return {
            "user_id": user_id,
            "conversations": conversations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


