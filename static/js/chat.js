document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.getElementById('chat-container');
    const chatMessages = document.getElementById('chat-messages');
    const questionForm = document.getElementById('question-form');
    const questionInput = document.getElementById('question-input');
    const roleDropdown = document.getElementById('role-dropdown');
    const loadingIndicator = document.querySelector('.loading');
    const themeToggle = document.getElementById('theme-toggle');

    let currentThreadId = null;
    let currentRole = null;

    if (roleDropdown) {
        roleDropdown.addEventListener('change', function() {
            currentRole = this.value;
            if (currentRole) {
                fetch(`/start?role=${currentRole}`)
                    .then(response => response.json())
                    .then(data => {
                        currentThreadId = data.thread_id;
                        chatMessages.innerHTML = '';
                        addSystemMessage('New conversation started. How can I assist you today?');
                    })
                    .catch(error => console.error('Error:', error));
            }
        });
    }

    if (questionForm) {
        questionForm.addEventListener('submit', function(e) {
            e.preventDefault();
            if (!currentRole) {
                alert('Please select a role before sending a message.');
                return;
            }
            const message = questionInput.value.trim();
            if (message) {
                addUserMessage(message);
                questionInput.value = '';
                sendMessage(message);
            }
        });
    }

    function sendMessage(message) {
        loadingIndicator.classList.remove('d-none');
        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                role: currentRole,
                thread_id: currentThreadId
            }),
        })
        .then(response => response.json())
        .then(data => {
            loadingIndicator.classList.add('d-none');
            addAssistantMessage(data.response);
        })
        .catch(error => {
            console.error('Error:', error);
            loadingIndicator.classList.add('d-none');
        });
    }

    function addUserMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container user-container';
        messageElement.innerHTML = `
            <div class="message user-message">
                <div class="message-header">You</div>
                <div class="message-content">${escapeHtml(message)}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function addAssistantMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container assistant-container';
        messageElement.innerHTML = `
            <div class="message assistant-message">
                <div class="message-header">Assistant</div>
                <div class="message-content">${marked.parse(escapeHtml(message))}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function addSystemMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container system-container';
        messageElement.innerHTML = `
            <div class="message system-message">
                <div class="message-content">${escapeHtml(message)}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function endCurrentSession() {
        if (currentThreadId && currentRole) {
            fetch('/end_session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    thread_id: currentThreadId,
                    role: currentRole
                }),
            })
            .then(response => response.json())
            .then(data => {
                console.log('Session ended:', data);
            })
            .catch(error => console.error('Error ending session:', error));
        }
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', function() {
            if (this.checked) {
                document.documentElement.setAttribute('data-bs-theme', 'dark');
                localStorage.setItem('theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-bs-theme', 'light');
                localStorage.setItem('theme', 'light');
            }
        });
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
