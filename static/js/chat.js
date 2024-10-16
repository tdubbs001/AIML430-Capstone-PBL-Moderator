document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chat-messages');
    const questionForm = document.getElementById('question-form');
    const questionInput = document.getElementById('question-input');
    const roleDropdown = document.getElementById('role-dropdown');
    const loadingIndicator = document.querySelector('.loading');
    const themeToggle = document.getElementById('theme-toggle');
    const reviewSessionButton = document.getElementById('review-session');
    const sessionSummary = document.getElementById('session-summary');
    const summaryContent = document.getElementById('summary-content');

    let currentRole = '';
    let currentThreadId = '';

    roleDropdown.addEventListener('change', function() {
        currentRole = this.value;
        if (currentRole) {
            startConversation(currentRole);
        }
    });

    questionForm.addEventListener('submit', function(e) {
        e.preventDefault();
        if (currentRole && questionInput.value.trim() !== '') {
            sendMessage(questionInput.value.trim());
            questionInput.value = '';
        }
    });

    reviewSessionButton.addEventListener('click', function() {
        if (currentThreadId) {
            reviewSession();
        }
    });

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

    function startConversation(role) {
        fetch(`/start?role=${role}`)
            .then(response => response.json())
            .then(data => {
                currentThreadId = data.thread_id;
                chatMessages.innerHTML = '';
                addSystemMessage('Conversation started. You can now ask questions.');
            })
            .catch(error => console.error('Error:', error));
    }

    function sendMessage(message) {
        addUserMessage(message);
        loadingIndicator.classList.remove('d-none');

        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                role: currentRole,
                message: message
            }),
        })
        .then(response => response.json())
        .then(data => {
            loadingIndicator.classList.add('d-none');
            addAssistantMessage(data.response);
        })
        .catch((error) => {
            console.error('Error:', error);
            loadingIndicator.classList.add('d-none');
        });
    }

    function reviewSession() {
        loadingIndicator.classList.remove('d-none');

        fetch('/review_session', {
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
            loadingIndicator.classList.add('d-none');
            summaryContent.innerHTML = data.summary;
            sessionSummary.classList.remove('d-none');
        })
        .catch((error) => {
            console.error('Error:', error);
            loadingIndicator.classList.add('d-none');
        });
    }

    function addUserMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container user-container';
        messageElement.innerHTML = `
            <div class="message user-message">
                <div class="message-header">You (${currentRole})</div>
                <div class="message-content">${message}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addAssistantMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container assistant-container';
        messageElement.innerHTML = `
            <div class="message assistant-message">
                <div class="message-header">Assistant</div>
                <div class="message-content">${marked.parse(message)}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addSystemMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-container system-container';
        messageElement.innerHTML = `
            <div class="message system-message">
                <div class="message-content">${message}</div>
            </div>
        `;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function endCurrentSession() {
        if (currentThreadId) {
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
                currentThreadId = '';
                currentRole = '';
                roleDropdown.value = '';
                chatMessages.innerHTML = '';
                sessionSummary.classList.add('d-none');
            })
            .catch((error) => {
                console.error('Error ending session:', error);
            });
        }
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
