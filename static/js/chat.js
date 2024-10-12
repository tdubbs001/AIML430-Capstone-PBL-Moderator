let currentThreadId = null;
let selectedRole = null;

function startNewConversation() {
    fetch('/start')
        .then(response => response.json())
        .then(data => {
            currentThreadId = data.thread_id;
            document.getElementById('chat-messages').innerHTML = '';
        })
        .catch(error => console.error('Error:', error));
}

function sendMessage(message) {
    if (!currentThreadId) {
        console.error('No active conversation');
        return;
    }

    if (!selectedRole) {
        alert('Please select a role before sending a message.');
        return;
    }

    // Display user message immediately
    displayMessage(message, 'user');

    showLoading(true);

    fetch('/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            thread_id: currentThreadId,
            message: message,
            role: selectedRole
        }),
    })
    .then(response => response.json())
    .then(data => {
        displayMessage(data.response, 'assistant');
        showLoading(false);
    })
    .catch(error => {
        console.error('Error:', error);
        showLoading(false);
    });
}

function formatRole(role) {
    return role.split('_')
              .map(word => word.charAt(0).toUpperCase() + word.slice(1))
              .join(' ');
}

function displayMessage(message, sender) {
    const chatMessages = document.getElementById('chat-messages');
    const messageContainer = document.createElement('div');
    messageContainer.classList.add('message-container');
    
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${sender}-message`);
    
    const messageHeader = document.createElement('div');
    messageHeader.classList.add('message-header');
    messageHeader.textContent = sender === 'user' ? formatRole(selectedRole) : 'AI Assistant';
    
    const messageContent = document.createElement('div');
    messageContent.classList.add('message-content');
    
    if (sender === 'assistant') {
        messageContent.innerHTML = marked.parse(message);
    } else {
        messageContent.textContent = message;
    }
    
    messageElement.appendChild(messageHeader);
    messageElement.appendChild(messageContent);
    messageContainer.appendChild(messageElement);
    chatMessages.appendChild(messageContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showLoading(show) {
    const loadingElement = document.querySelector('.loading');
    if (show) {
        loadingElement.classList.remove('d-none');
    } else {
        loadingElement.classList.add('d-none');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const questionForm = document.getElementById('question-form');
    const questionInput = document.getElementById('question-input');
    const roleDropdown = document.getElementById('role-dropdown');

    questionForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = questionInput.value.trim();
        if (message) {
            sendMessage(message);
            questionInput.value = '';
        }
    });

    roleDropdown.addEventListener('change', (e) => {
        selectedRole = e.target.value;
        if (selectedRole && !currentThreadId) {
            startNewConversation();
        }
    });

    // Start a new conversation when the page loads
    startNewConversation();
});
