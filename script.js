const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const userIdInput = document.getElementById('userId');

const attachBtn = document.getElementById('attachBtn');
const imageInput = document.getElementById('imageInput');
const imagePreviewContainer = document.getElementById('imagePreviewContainer');
const imagePreview = document.getElementById('imagePreview');
const imageName = document.getElementById('imageName');
const removeImageBtn = document.getElementById('removeImageBtn');

let currentConversationId = null;
let selectedImageData = null;

// 🚀 Servidor Backend en Producción (Render):
// const API_URL = "https://rob-6t96.onrender.com/chat";

// 💻 Servidor Backend Local (para pruebas locales con uvicorn main:app --reload):
const API_URL = "https://rob-6t96.onrender.com/chat";

// Manejo de carga de archivos (Imágenes)
attachBtn.addEventListener('click', () => imageInput.click());

imageInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            selectedImageData = event.target.result;
            imagePreview.src = selectedImageData;
            imageName.textContent = file.name;
            imagePreviewContainer.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }
});

removeImageBtn.addEventListener('click', clearSelectedImage);

function clearSelectedImage() {
    selectedImageData = null;
    imageInput.value = '';
    imagePreview.src = '';
    imageName.textContent = '';
    imagePreviewContainer.style.display = 'none';
}

function addMessage(text, sender, imageData = null) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    if (sender === 'user') {
        messageDiv.classList.add('user-message');
    } else {
        messageDiv.classList.add('bot-message');
    }

    if (imageData) {
        const img = document.createElement('img');
        img.src = imageData;
        img.classList.add('message-img');
        messageDiv.appendChild(img);
    }

    if (text) {
        const textSpan = document.createElement('div');
        textSpan.textContent = text;
        messageDiv.appendChild(textSpan);
    }

    chatMessages.appendChild(messageDiv);

    // Auto-scroll hacia abajo
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const text = userInput.value.trim();
    const userId = userIdInput.value.trim() || "default_user";
    const currentImageData = selectedImageData;

    if (text === "" && !currentImageData) return;

    // Mostrar mensaje del usuario en pantalla
    addMessage(text, 'user', currentImageData);

    // Limpiar entrada e imagen
    userInput.value = "";
    clearSelectedImage();
    userInput.focus();

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                conversation_id: currentConversationId,
                mensaje: text,
                image_data: currentImageData
            })
        });

        if (response.ok) {
            const data = await response.json();
            currentConversationId = data.conversation_id;
            addMessage(data.rob_response, 'bot');
        } else {
            addMessage("Error: El servidor respondió con un fallo.", 'bot');
        }
    } catch (error) {
        console.error("Error de conexión:", error);
        addMessage("Error: No se pudo conectar con el servidor de R.O.B.", 'bot');
    }
}

// Eventos para enviar con el botón o con la tecla Enter
sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});