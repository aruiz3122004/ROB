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
# --- CONFIGURACIÓN DE CORS EN PRODUCCIÓN ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rob-frontend-alpha.vercel.app",  # Frontend en Vercel
        "http://127.0.0.1:8000",                  # Backend Local
        "http://127.0.0.1:5500",                  # Live Server / HTML Local
        "http://localhost:3000"
    ],
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
    try:
        conv_id = datos.conversation_id or f"chat_{int(datetime.datetime.now().timestamp())}"
        now_iso = datetime.datetime.utcnow().isoformat()

        # 1. Cargar historial reciente
        past_msgs_cursor = messages_col.find({"conversation_id": conv_id}).sort("created_at", 1)
        past_msgs = list(past_msgs_cursor)
        recent_history = past_msgs[-8:] if len(past_msgs) > 8 else past_msgs

        # 2. Cargar perfil del usuario
        perfil = memoria_col.find_one({"user_id": datos.user_id})
        contexto_usuario = perfil.get("preferencias", "Sin datos.") if perfil else "Sin datos."

        # 3. System Prompt
        system_prompt = (
            "Eres R.O.B., un asistente enfocado en responder con precisión.\n"
            "REGLAS OBLIGATORIAS:\n"
            "1. Cuando el usuario pregunte '¿cómo lo conocen?', '¿quién es?' o use pronombres (él/ella/lo/esto), DEBES responder ÚNICAMENTE sobre la entidad o personaje de la imagen o del mensaje anterior.\n"
            "2. Sé extremadamente preciso con nombres culturales (ej: Tweety/Piolín, Yosemite Sam/Sam Bigotes).\n"
            "3. NO des explicaciones filosóficas sobre el idioma ni te desvíes a temas de IA o tecnología.\n"
            "Si el usuario te dice algo importante sobre él (su nombre, gustos, profesión), "
            "añade al final de tu respuesta la etiqueta [RECORDAR: lo que debo recordar].\n\n"
            f"<user_profile>\n{contexto_usuario}\n</user_profile>"
        )

        messages_payload = [{"role": "system", "content": system_prompt}]

        # 4. Reconstrucción FIEL del historial manteniendo estructura Multimodal (Imágenes)
        for msg in recent_history:
            role = "user" if msg.get("sender") == "user" else "assistant"
            content_txt = msg.get("content") or ""
            img_b64 = msg.get("image_data")

            if role == "user":
                if img_b64:
                    messages_payload.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": content_txt or "Analiza esta imagen."},
                            {"type": "image_url", "image_url": {"url": img_b64}}
                        ]
                    })
                else:
                    messages_payload.append({"role": "user", "content": content_txt})
            else:
                messages_payload.append({"role": "assistant", "content": content_txt})

        # 5. Guardar mensaje actual del usuario en MongoDB
        messages_col.insert_one({
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "user",
            "content": datos.mensaje,
            "image_data": datos.image_data,
            "created_at": now_iso
        })

        # Actualizar metadatos de la conversación
        conversations_col.update_one(
            {"conversation_id": conv_id},
            {
                "$set": {"user_id": datos.user_id, "updated_at": now_iso},
                "$setOnInsert": {
                    "conversation_id": conv_id,
                    "title": datos.mensaje[:35] + ("..." if len(datos.mensaje) > 35 else ""),
                    "created_at": now_iso
                }
            },
            upsert=True
        )

        # 6. Añadir mensaje actual al payload
        if datos.image_data:
            messages_payload.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": datos.mensaje or "Analiza esta imagen."},
                    {"type": "image_url", "image_url": {"url": datos.image_data}}
                ]
            })
        else:
            messages_payload.append({"role": "user", "content": datos.mensaje})

        # 7. Ejecutar modelo en Groq
        model_to_use = os.getenv("MODEL_NAME", "qwen/qwen3.8-27b")
        
        completion = groq_client.chat.completions.create(
            model=model_to_use,
            messages=messages_payload,
            temperature=0.1,
            max_tokens=800
        )

        respuesta_rob = completion.choices[0].message.content.strip()

        # Limpieza de razonamiento interno si aplica
        if "<think>" in respuesta_rob and "</think>" in respuesta_rob:
            import re
            respuesta_rob = re.sub(r'<think>.*?</think>', '', respuesta_rob, flags=re.DOTALL).strip()

        # Procesar memoria si R.O.B. detecta un dato relevante
        if "[RECORDAR:" in respuesta_rob:
            partes = respuesta_rob.split("[RECORDAR:")
            respuesta_limpia = partes[0].strip()
            nuevo_dato = partes[1].replace("]", "").strip()
            perfil_db = memoria_col.find_one({"user_id": datos.user_id})
            ctx_existente = perfil_db.get("preferencias", "") if perfil_db else ""
            ctx_nuevo = f"{ctx_existente}; {nuevo_dato}".strip("; ") if ctx_existente else nuevo_dato
            memoria_col.update_one(
                {"user_id": datos.user_id},
                {"$set": {"preferencias": ctx_nuevo}},
                upsert=True
            )
            respuesta_rob = respuesta_limpia
        else:
            respuesta_rob = respuesta_rob.strip()

        # 8. Guardar respuesta del bot en DB
        messages_col.insert_one({
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "bot",
            "content": respuesta_rob,
            "created_at": datetime.datetime.utcnow().isoformat()
        })

        return ChatResponse(rob_response=respuesta_rob, conversation_id=conv_id)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ ERROR EN /chat: {type(e).__name__}: {e}\n")
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


