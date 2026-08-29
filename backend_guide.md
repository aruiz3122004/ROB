# 🐍 Guía de Integración Backend para R.O.B. (Python + FastAPI + MongoDB Atlas)

Esta guía especifica el código exacto y la arquitectura NoSQL para tu servicio backend en **Render** conectado a **MongoDB Atlas**.

---

## 1. Estructura de Colecciones NoSQL (MongoDB Atlas)

Tu base de datos `rob_database` en MongoDB Atlas organizará la información en **4 colecciones**:

### 1. Colección `users`
Almacena las cuentas de usuario registradas desde el botón **"💾 Guardar en Base de Datos"**.
```json
{
  "_id": ObjectId("..."),
  "username": "andres",
  "password_hash": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
  "created_at": "2026-08-28T10:56:00.000Z"
}
```

### 2. Colección `conversations`
Almacena las sesiones e hilos de conversación creados por cada usuario.
```json
{
  "_id": ObjectId("..."),
  "conversation_id": "chat_1787932619",
  "user_id": "andres",
  "title": "Hola R.O.B., mi color favorito es...",
  "created_at": "2026-08-28T10:56:00.000Z",
  "updated_at": "2026-08-28T10:56:05.000Z"
}
```

### 3. Colección `messages`
Guarda el historial de mensajes enviados por el usuario y las respuestas de R.O.B.
```json
{
  "_id": ObjectId("..."),
  "conversation_id": "chat_1787932619",
  "user_id": "andres",
  "sender": "user",
  "content": "Hola R.O.B., mi color favorito es el azul.",
  "image_data": null,
  "created_at": "2026-08-28T10:56:00.000Z"
}
```

### 4. Colección `user_memory`
Almacena la memoria a largo plazo y reglas descubiertas por R.O.B. para cada usuario.
```json
{
  "_id": ObjectId("..."),
  "user_id": "andres",
  "preferencias": "Su color favorito es el azul; Le apasiona la programación"
}
```

---

## 2. Código Python Completo para `main.py` en FastAPI

El código de `main.py` de tu repositorio local ya se encuentra actualizado con este contenido:

```python
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

# Cargar variables de entorno en desarrollo local
if os.path.exists("atlas-credentials.env"):
    load_dotenv("atlas-credentials.env")
elif os.path.exists(".env"):
    load_dotenv(".env")

app = FastAPI(title="API de R.O.B.", version="1.0")

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGODB_URI")

groq_client = Groq(api_key=GROQ_API_KEY)
mongo_client = MongoClient(MONGO_URI)

# Colecciones de MongoDB Atlas
db = mongo_client["rob_database"]
users_col = db["users"]
conversations_col = db["conversations"]
messages_col = db["messages"]
memoria_col = db["user_memory"]

# Modelos Pydantic
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

# Endpoints

@app.get("/")
def leer_raiz():
    return {"mensaje": "¡Hola! R.O.B. está en línea y conectado a MongoDB Atlas."}

@app.post("/register")
def register_user(user: UserRegister):
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Usuario y contraseña son requeridos")

    username_clean = user.username.strip()
    if users_col.find_one({"username": username_clean}):
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está registrado en la base de datos")

    pwd_hash = hashlib.sha256(user.password.encode('utf-8')).hexdigest()

    user_doc = {
        "username": username_clean,
        "password_hash": pwd_hash,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    users_col.insert_one(user_doc)

    return {"status": "success", "message": f"Usuario {username_clean} registrado con éxito en MongoDB Atlas"}

@app.post("/login")
def login_user(user: UserLogin):
    username_clean = user.username.strip()
    db_user = users_col.find_one({"username": username_clean})
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en la base de datos")

    if user.password:
        pwd_hash = hashlib.sha256(user.password.encode('utf-8')).hexdigest()
        if db_user.get("password_hash") != pwd_hash:
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    return {"status": "success", "username": username_clean, "message": f"Usuario {username_clean} autenticado correctamente"}

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

        # 7. Ejecutar modelo de visión en Groq
        model_to_use = os.getenv("MODEL_NAME", "llama-3.2-11b-vision-preview")
        
        completion = groq_client.chat.completions.create(
            model=model_to_use,
            messages=messages_payload,
            temperature=0.1,
            max_tokens=400
        )

        respuesta_rob = completion.choices[0].message.content.strip()

        # Procesar etiqueta de memoria
        if "[RECORDAR:" in respuesta_rob:
            partes = respuesta_rob.split("[RECORDAR:")
            respuesta_limpia = partes[0].strip()
            nuevo_dato = partes[1].replace("]", "").strip()
            memoria_col.update_one(
                {"user_id": datos.user_id},
                {"$set": {"preferencias": f"{contexto}; {nuevo_dato}"}},
                upsert=True
            )
            respuesta_rob = respuesta_limpia
        else:
            respuesta_rob = respuesta_rob.strip()

        # 8. Guardar respuesta del bot
        messages_col.insert_one({
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "bot",
            "content": respuesta_rob,
            "created_at": datetime.datetime.utcnow().isoformat()
        })

        return ChatResponse(rob_response=respuesta_rob, conversation_id=conv_id)

        # Guardar respuesta de R.O.B.
        messages_col.insert_one({
            "conversation_id": conv_id,
            "user_id": datos.user_id,
            "sender": "bot",
            "content": respuesta_rob,
            "created_at": datetime.datetime.utcnow().isoformat()
        })

        return ChatResponse(rob_response=respuesta_rob, conversation_id=conv_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_id}")
def get_user_history(user_id: str):
    try:
        conversations = list(conversations_col.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1))
        for conv in conversations:
            msgs = list(messages_col.find({"conversation_id": conv["conversation_id"]}, {"_id": 0}).sort("created_at", 1))
            conv["messages"] = msgs

        return {"user_id": user_id, "conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 3. Variables de Entorno en Render

Asegúrate de configurar en **Render -> Environment Settings**:
- `MONGODB_URI`: `mongodb+srv://andreselgameroscuro_db_user:bBeiTGngybJkEU6h@cluster.jqad6we.mongodb.net`
- `GROQ_API_KEY`: `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`

