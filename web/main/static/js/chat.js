// --- DOM Elements ---
const chatContainer = document.getElementById('chat-container');
const queryInput = document.getElementById('query-input');
const chatForm = document.getElementById('chat-form');
const sendButton = document.getElementById('send-button');
// --- Expert Panel JavaScript ---
const openPanelBtn = document.getElementById('open-expert-panel');
const closePanelBtn = document.getElementById('close-expert-panel');
const expertSidebar = document.getElementById('expert-sidebar');
const tempSlider = document.getElementById('temp-slider');
const tempValue = document.getElementById('temp-value');
const toppSlider = document.getElementById('topp-slider');
const toppValue = document.getElementById('topp-value');
const agentCheckboxesDiv = document.getElementById('agent-checkboxes');
const saveSettingsBtn = document.getElementById('save-settings-btn');

const isNewChat = conversationId === '';
let typingIndicatorElement = null; // NEW: A global reference to the indicator element
// --- Initial State ---
window.onload = () => {
    chatContainer.scrollTop = chatContainer.scrollHeight;
    queryInput.focus();
};
// --- Core Functions ---
function enableInput() {
    queryInput.disabled = false;
    sendButton.disabled = false;
    queryInput.focus();
}
function appendMessage(text, role, agentName = '', messageId = null) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${role}-message`);
    if (messageId) {
        messageDiv.dataset.messageId = messageId;
    }

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');

    if (role === 'agent') {
        const nameSpan = document.createElement('div');
        nameSpan.classList.add('agent-name');
        nameSpan.textContent = agentName;
        bubble.appendChild(nameSpan);
    }

    const textContainer = document.createElement('div');
    textContainer.classList.add('text');

    // Handle <think> tags by creating a collapsible section
    const thinkRegex = /<think>([\s\S]*?)<\/think>/g;
    let lastIndex = 0;
    let match;
    while ((match = thinkRegex.exec(text)) !== null) {
        // Text before <think>
        const beforeText = text.slice(lastIndex, match.index);
        if (beforeText) {
            const beforeNode = document.createElement('div');
            // Render any HTML in the response
            beforeNode.innerHTML = DOMPurify.sanitize(beforeText);
            textContainer.appendChild(beforeNode);
        }

        // Create accordion (details) for the thought content
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'Show Thought';
        details.appendChild(summary);

        const thoughtDiv = document.createElement('div');
        thoughtDiv.innerHTML = DOMPurify.sanitize(match[1]);
        details.appendChild(thoughtDiv);

        textContainer.appendChild(details);
        lastIndex = match.index + match[0].length;
    }

    // Remaining text after last </think>
    const remaining = text.slice(lastIndex);
    if (remaining) {
        const afterNode = document.createElement('div');
        // Render any HTML in the response
        afterNode.innerHTML = DOMPurify.sanitize(remaining);
        textContainer.appendChild(afterNode);
    }

    bubble.appendChild(textContainer);

    if (role === 'agent' && messageId) {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.classList.add('feedback-buttons');
        feedbackDiv.innerHTML = `
            <button class="feedback-btn thumbs-up">👍</button>
            <button class="feedback-btn thumbs-down">👎</button>
        `;
        bubble.appendChild(feedbackDiv);
    }

    messageDiv.appendChild(bubble);
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    // Also return HTML string of the message
    return messageDiv.outerHTML;
}

function showTypingIndicator() {
    // If an indicator is already showing, do nothing.
    if (typingIndicatorElement) return;
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', 'agent-message');
    
    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    
    const indicator = document.createElement('div');
    indicator.classList.add('typing-indicator');
    indicator.innerHTML = '<span></span><span></span><span></span>';
    
    bubble.appendChild(indicator);
    messageDiv.appendChild(bubble);
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    // Store the reference so we can remove it later
    typingIndicatorElement = messageDiv;
}
function hideTypingIndicator() {
    if (typingIndicatorElement) {
        typingIndicatorElement.remove();
        typingIndicatorElement = null;
    }
}
// --- Event Handlers ---
chatForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;
    appendMessage(query, 'user');
    queryInput.value = '';
    queryInput.disabled = true;
    sendButton.disabled = true;
    showTypingIndicator();
    const eventSource = new EventSource(`/chat/process/${conversationId}/?query=${encodeURIComponent(query)}`);
    let connectionClosedCleanly = false;
    let agentMessageDiv = null;
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        hideTypingIndicator()
        
        if (data.type === 'done') {
            connectionClosedCleanly = true;
            eventSource.close();
            enableInput();
            return; // Stop processing
        }
        if (data.type === 'final_answer') {
            if (agentMessageDiv) {
                // This case is unlikely with current backend but good for robustness
                agentMessageDiv.querySelector('.text').innerText = data.content;
            } else {
                agentMessageDiv = appendMessage(data.content, 'agent', data.agent_name, data.id);
            }
        } else if (data.type === 'log') {
            // We're not displaying logs on the frontend anymore, but you could add a log div here
            console.log('Log:', data.content);
        } else if (data.type === 'error') {
            appendMessage(`Error: ${data.content}`, 'agent', 'System');
            connectionClosedCleanly = true;
            eventSource.close();
            enableInput();
        }
    };
    eventSource.onerror = function(err) {
        if (!connectionClosedCleanly) {
            console.error("EventSource failed:", err);
            appendMessage('Connection to agent lost. Please try again.', 'agent', 'System');
        }
        eventSource.close();
        enableInput();
    };
    // The SSE connection closes from the server side, but we also enable input on error.
    // We'll also re-enable it on a normal close event.
    eventSource.addEventListener('close', () => {
         enableInput();
    });
});
chatContainer.addEventListener('click', function(e) {
    if (e.target.classList.contains('feedback-btn')) {
        const button = e.target;
        const messageDiv = button.closest('.agent-message');
        if (!messageDiv) return;
        const messageId = messageDiv.dataset.messageId;
        const isThumbsUp = button.classList.contains('thumbs-up');
        
        let feedbackType = isThumbsUp ? 'up' : 'down';
        if (button.classList.contains('selected')) {
            feedbackType = 'none';
        }
        fetch(feedbackurl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ message_id: messageId, feedback: feedbackType })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok') {
                const buttons = messageDiv.querySelectorAll('.feedback-btn');
                buttons.forEach(btn => btn.classList.remove('selected'));
                if (feedbackType !== 'none') {
                    button.classList.add('selected');
                }
            } else {
                console.error('Feedback submission failed:', data.message);
            }
        })
        .catch(err => console.error('Feedback fetch error:', err));
    }
});
queryInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && e.ctrlKey) {
        chatForm.dispatchEvent(new Event('submit'));
    }
});
sendButton.addEventListener('click', function(e) {
    chatForm.dispatchEvent(new Event('submit'));
});

function populateAgentCheckboxes(settings) {
    agentCheckboxesDiv.innerHTML = '';
    const enabledAgents = settings.enabled_agents || userPermittedAgents;
    userPermittedAgents.forEach(agentName => {
        const isChecked = enabledAgents.includes(agentName);
        const item = document.createElement('div');
        item.classList.add('checkbox-item');
        item.innerHTML = `
        <div class="enabledagentsdiv">
            <input type="checkbox" id="agent-${agentName}" value="${agentName}" ${isChecked ? 'checked' : ''}>
            <label for="agent-${agentName}">${agentName.charAt(0).toUpperCase() + agentName.slice(1)}</label>
        </div>
        `;
        agentCheckboxesDiv.appendChild(item);
    });
}
function loadSettings() {
    // In a real app, you might fetch this from the server on page load
    // For now, we'll use defaults or localStorage
    const settings = JSON.parse(localStorage.getItem('expertSettings')) || {
        model_selection: 'local_system',
        temperature: 0.7,
        top_p: 0.9,
        enabled_agents: userPermittedAgents // Default to all permitted agents enabled
    };
    modelSelect.value = settings.model_selection;
    if (modelSelect.value !== settings.model_selection) {
        settings.model_selection = 'local_system';
    };
    tempSlider.value = settings.temperature;
    tempValue.textContent = settings.temperature;
    toppSlider.value = settings.top_p;
    toppValue.textContent = settings.top_p;
    toggleLocalAgentSettings();
    populateAgentCheckboxes(settings);
}
openPanelBtn.addEventListener('click', () => expertSidebar.classList.replace('closed', 'open'));
closePanelBtn.addEventListener('click', () => expertSidebar.classList.replace('open', 'closed'));
tempSlider.addEventListener('input', (e) => tempValue.textContent = e.target.value);
toppSlider.addEventListener('input', (e) => toppValue.textContent = e.target.value);
const modelSelect = document.getElementById('model-select');
const localAgentSettingsDiv = document.getElementById('local-agent-settings');

function toggleLocalAgentSettings() {
    if (modelSelect.value === 'local_system') {
        localAgentSettingsDiv.style.display = 'block';
    } else {
        localAgentSettingsDiv.style.display = 'none';
    }
}
modelSelect.addEventListener('change', toggleLocalAgentSettings);
saveSettingsBtn.addEventListener('click', () => {
    const enabledAgents = Array.from(agentCheckboxesDiv.querySelectorAll('input:checked')).map(cb => cb.value);
    const settings = {
        model_selection: modelSelect.value,
        enabled_agents: enabledAgents,
        temperature: parseFloat(tempSlider.value),
        top_p: parseFloat(toppSlider.value),
    };
    console.log(modelSelect.value);
    // Save to server session
    fetch(urlexpertsettings, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            // Save to localStorage for UI persistence on refresh
            localStorage.setItem('expertSettings', JSON.stringify(settings));
            alert('Settings saved!');
            expertSidebar.classList.remove('open');
            expertSidebar.classList.add('closed');
        } else {
            alert('Error saving settings.');
        }
    });
});
// Load settings when the page loads
loadSettings();