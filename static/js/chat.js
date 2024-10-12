let currentThreadId = null;

function startNewConversation() {
    fetch('/start')
        .then(response => response.json())
        .then(data => {
            currentThreadId = data.thread_id;
            document.getElementById('chat-container').innerHTML = '';
        })
        .catch(error => console.error('Error:', error));
}

function sendMessage(message) {
    if (!currentThreadId) {
        console.error('No active conversation');
        return;
    }

    fetch('/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            thread_id: currentThreadId,
            message: message
        }),
    })
    .then(response => response.json())
    .then(data => {
        displayMessage(message, 'user');
        displayMessage(data.response, 'assistant');
    })
    .catch(error => console.error('Error:', error));
}

function displayMessage(message, sender) {
    const chatContainer = document.getElementById('chat-container');
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${sender}-message`);
    messageElement.textContent = message;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const newConversationBtn = document.getElementById('new-conversation');

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (message) {
            sendMessage(message);
            userInput.value = '';
        }
    });

    newConversationBtn.addEventListener('click', startNewConversation);

    // Start a new conversation when the page loads
    startNewConversation();
});
