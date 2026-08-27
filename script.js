const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const userIdInput = document.getElementById('userId');

// URL de tu backend en Render
const API_URL = "https://rob-6t96.onrender.com/chat";

function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    if (sender === 'user') {
        messageDiv.classList.add('user-message');
    } else {
        messageDiv.classList.add('bot-message');
    }
    messageDiv.textContent = text;
    chatMessages.appendChild(messageDiv);

    // Auto-scroll hacia abajo
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const text = userInput.value.trim();
    const userId = userIdInput.value.trim() || "default_user";

    if (text === "") return;

    // Mostrar mensaje del usuario en pantalla
    addMessage(text, 'user');
    userInput.value = "";
    userInput.focus();

    // Mensaje temporal de carga
    const loadingId = "Cargando...";

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                mensaje: text
            })
        });

        if (response.ok) {
            const data = await response.json();
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