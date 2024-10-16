let currentThreadId = null;
let selectedRole = null;

const roleNames = {
    'undp_head': 'UNDP - Head of Environment and Energy Section',
    'undp_water_project_manager': 'UNDP Water Project Manager (United Nations Volunteer)',
    'local_government_official': 'Local Government Official – District Water Engineer',
    'local_ngo_officer': 'Local NGO Programme Officer',
    'international_ngo_officer': 'International Implementing NGO Program Officer with Oxfam GB',
    'bilateral_aid_officer': 'Bilateral Aid Agency Programme Officer – Irish Aid',
    'eu_officer': 'European Union Programme Officer',
    'village_chief': 'Village Chief',
    'womens_group_rep': 'District Women\'s Group Representative for OPMT (The Popular Organisation of East Timorese Women)',
    'water_division_director': 'Director of the Water Division in the Ministry of Infrastructure'
};

function endCurrentSession() {
    if (currentThreadId) {
        fetch('/end_session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                thread_id: currentThreadId,
                role: selectedRole
            }),
        }).catch(error => console.error('Error ending session:', error));
    }
}

function startNewConversation() {
    if (!selectedRole) {
        console.error('No role selected');
        return;
    }
    fetch(`/start?role=${selectedRole}`)
        .then(response => response.json())
        .then(data => {
            currentThreadId = data.thread_id;
            document.getElementById('chat-messages').innerHTML = '';
            displaySystemMessage(`New conversation started as ${roleNames[selectedRole]}`);
        })
        .catch(error => console.error('Error:', error));
}

function sendMessage(message) {
    if (!currentThreadId) {
        console.error('No active conversation');
        alert('Please select a role to start a conversation.');
        return;
    }

    if (!selectedRole) {
        alert('Please select a role before sending a message.');
        return;
    }

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
        if (data.error) {
            console.error('Error:', data.error);
            alert(data.error);
        } else {
            displayMessage(data.response, 'assistant');
        }
        showLoading(false);
    })
    .catch(error => {
        console.error('Error:', error);
        showLoading(false);
    });
}

function formatRole(role) {
    return roleNames[role] || role;
}

function displaySystemMessage(message) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    const messageContainer = document.createElement('div');
    messageContainer.classList.add('message-container', 'system-container');
    
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', 'system-message');
    messageElement.textContent = message;
    
    messageContainer.appendChild(messageElement);
    chatMessages.appendChild(messageContainer);
    scrollToBottom();
}

function displayMessage(message, sender) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    const messageContainer = document.createElement('div');
    messageContainer.classList.add('message-container', `${sender}-container`);
    
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
    scrollToBottom();
}

function scrollToBottom() {
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

function showLoading(show) {
    const loadingElement = document.querySelector('.loading');
    if (loadingElement) {
        if (show) {
            loadingElement.classList.remove('d-none');
        } else {
            loadingElement.classList.add('d-none');
        }
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    html.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

document.addEventListener('DOMContentLoaded', () => {
    const questionForm = document.getElementById('question-form');
    const questionInput = document.getElementById('question-input');
    const roleDropdown = document.getElementById('role-dropdown');
    const themeToggle = document.getElementById('theme-toggle');

    if (questionForm) {
        questionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!currentThreadId) {
                alert('Please select a role to start a conversation.');
                return;
            }
            const message = questionInput.value.trim();
            if (message) {
                sendMessage(message);
                questionInput.value = '';
            }
        });
    }

    if (roleDropdown) {
        roleDropdown.addEventListener('change', (e) => {
            if (selectedRole) {
                endCurrentSession();
            }
            selectedRole = e.target.value;
            if (selectedRole) {
                startNewConversation();
            }
        });
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', toggleTheme);
    }

    // Set initial theme based on user preference or system setting
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        if (themeToggle) {
            themeToggle.checked = savedTheme === 'dark';
        }
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
        if (themeToggle) {
            themeToggle.checked = true;
        }
    }

    // Add beforeunload event listener
    window.addEventListener('beforeunload', (event) => {
        endCurrentSession();
    });
});
