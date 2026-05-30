// script.js

// ── State ─────────────────────────────────────────────────────────────
let sessionId = null;
let isUploading = false;

// ── DOM Elements ──────────────────────────────────────────────────────
const uploadSection = document.getElementById('uploadSection');
const chatSection = document.getElementById('chatSection');
const uploadBtn = document.getElementById('uploadBtn');
const sendBtn = document.getElementById('sendBtn');
const chatInput = document.getElementById('chatInput');
const pdfInput = document.getElementById('pdfInput');
const uploadStatus = document.getElementById('uploadStatus');
const chatWindow = document.getElementById('chatWindow');
const toggleUploadBtn = document.getElementById('toggleUpload');
const dropzone = document.getElementById('dropzone');
const noMessages = document.getElementById('noMessages');
const sessionInfo = document.getElementById('sessionInfo');

// ── Auth guard ────────────────────────────────────────────────────────
// auth.js is loaded before this file so getToken() and getUser() exist

function authHeaders() {
    // Returns headers object with Authorization token
    return {
        'Authorization': 'Bearer ' + getToken()
    };
}

function handleUnauthorized(response) {
    // If API returns 401, token is expired or invalid → send to login
    if (response.status === 401) {
        clearAuth();
        redirectToLogin();
        return true;
    }
    return false;
}

function handleLogout() {
    clearAuth();
    redirectToLogin();
}

// ── Initialize app ────────────────────────────────────────────────────
function init() {
    // Auth check — if no token, go to login page immediately
    if (!getToken()) {
        redirectToLogin();
        return;
    }

    // Show user info in header
    const user = getUser();
    if (user) {
        const headerUser = document.getElementById('headerUser');
        const headerUserName = document.getElementById('headerUserName');
        const headerUserRole = document.getElementById('headerUserRole');
        if (headerUser) headerUser.style.display = 'flex';
        if (headerUserName) headerUserName.textContent = user.name;
        if (headerUserRole) headerUserRole.textContent = user.role;
    }

    // Event listeners — same as before
    uploadBtn.onclick = function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!pdfInput.files.length) {
            updateUploadStatus('Please select a PDF file.', 'error');
            return;
        }
        handleUpload();
    };

    sendBtn.addEventListener('click', handleSendMessage);
    pdfInput.addEventListener('change', handleFileSelected);
    chatInput.addEventListener('keydown', handleEnterKey);
    toggleUploadBtn.addEventListener('click', toggleUploadSection);

    setupDragAndDrop();
}

// ── Drag and drop — unchanged from original ───────────────────────────
function setupDragAndDrop() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, unhighlight, false);
    });

    dropzone.addEventListener('drop', handleDrop, false);

    dropzone.addEventListener('click', function (e) {
        if (e.target === pdfInput) return;
        e.preventDefault();
        e.stopPropagation();
        pdfInput.click();
    });
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function highlight() {
    dropzone.classList.add('dragover');
}

function unhighlight() {
    dropzone.classList.remove('dragover');
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length && files[0].type === 'application/pdf') {
        pdfInput.files = files;
        handleFileSelected();
    } else {
        updateUploadStatus('Please select a PDF file.', 'error');
    }
}

// ── File selection — unchanged from original ──────────────────────────
function handleFileSelected() {
    const file = pdfInput.files[0];
    if (file) {
        uploadBtn.disabled = false;
        updateUploadStatus(`File selected: ${file.name}`, 'normal');
        dropzone.classList.add('has-file');
        const fileName = document.createElement('div');
        fileName.className = 'selected-file';
        fileName.textContent = file.name;
        const existingFileName = dropzone.querySelector('.selected-file');
        if (existingFileName) existingFileName.remove();
        dropzone.appendChild(fileName);
    } else {
        uploadBtn.disabled = true;
        updateUploadStatus('', 'normal');
    }
}

function toggleUploadSection() {
    const isMinimized = uploadSection.classList.toggle('minimized');
    if (isMinimized) {
        toggleUploadBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round"
                stroke-linejoin="round" width="18" height="18">
                <polyline points="6 9 12 15 18 9"></polyline>
            </svg>`;
    } else {
        toggleUploadBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round"
                stroke-linejoin="round" width="18" height="18">
                <polyline points="18 15 12 9 6 15"></polyline>
            </svg>`;
    }
}

// ── Upload — now sends JWT token ──────────────────────────────────────
async function handleUpload() {
    if (isUploading) return;

    const file = pdfInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

    isUploading = true;
    uploadBtn.disabled = true;
    updateUploadStatus('Uploading...', 'loading');

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            headers: authHeaders(),   // ← JWT token added here
            body: formData
        });

        // Token expired or invalid
        if (handleUnauthorized(response)) return;

        const data = await response.json();

        if (response.ok) {
            sessionId = data.session_id;
            updateUploadStatus('Upload successful!', 'success');

            uploadSection.classList.add('minimized');
            toggleUploadBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2" stroke-linecap="round"
                    stroke-linejoin="round" width="18" height="18">
                    <polyline points="6 9 12 15 18 9"></polyline>
                </svg>`;

            setTimeout(() => {
                chatSection.classList.add('active');
                chatInput.disabled = false;
                sendBtn.disabled = false;
                chatInput.focus();

                sessionInfo.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" stroke-width="2" stroke-linecap="round"
                        stroke-linejoin="round" width="14" height="14">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    ${file.name.substring(0, 20)}${file.name.length > 20 ? '...' : ''}
                `;
            }, 300);
        } else {
            updateUploadStatus(`Error: ${data.detail}`, 'error');
            uploadBtn.disabled = false;
        }
    } catch (error) {
        updateUploadStatus(`Error: ${error.message}`, 'error');
        uploadBtn.disabled = false;
    } finally {
        isUploading = false;
    }
}

// ── Upload status ─────────────────────────────────────────────────────
function updateUploadStatus(message, type = 'normal') {
    uploadStatus.textContent = '';
    uploadStatus.className = 'upload-status';

    if (type === 'loading') {
        uploadStatus.className += ' status-loading';
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        uploadStatus.appendChild(spinner);
        uploadStatus.appendChild(document.createTextNode(' ' + message));
    } else {
        uploadStatus.textContent = message;
        if (type === 'error') uploadStatus.className += ' status-error';
        if (type === 'success') uploadStatus.className += ' status-success';
    }
}

// ── Chat — now sends JWT token ────────────────────────────────────────
function handleEnterKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
    }
}

async function handleSendMessage() {
    const message = chatInput.value.trim();
    if (!message || !sessionId) return;

    chatInput.value = '';
    sendBtn.disabled = true;
    chatInput.disabled = true;

    if (noMessages.style.display !== 'none') {
        noMessages.style.display = 'none';
    }

    appendMessage('user', message);
    showTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...authHeaders()    // ← JWT token added here
            },
            body: JSON.stringify({ session_id: sessionId, question: message })
        });

        // Token expired or invalid
        if (handleUnauthorized(response)) return;

        const data = await response.json();
        hideTypingIndicator();

        if (response.ok) {
            appendMessage('bot', data.answer);
        } else {
            appendMessage('bot', `Error: ${data.detail}`);
        }
    } catch (error) {
        hideTypingIndicator();
        appendMessage('bot', `Error: ${error.message}`);
    } finally {
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// ── Typing indicator — unchanged ──────────────────────────────────────
function showTypingIndicator() {
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.id = 'typingIndicator';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.className = 'typing-dot';
        typingIndicator.appendChild(dot);
    }
    chatWindow.appendChild(typingIndicator);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) typingIndicator.remove();
}

// ── Message rendering — unchanged ─────────────────────────────────────
function appendMessage(sender, message) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', sender);

    if (sender === 'bot' && (message.match(/\d+\.\s/g) || []).length > 1) {
        const formattedContent = document.createElement('div');
        formattedContent.className = 'formatted-content';
        const parts = message.split(/(\d+\.\s)/g);

        if (parts.length > 1) {
            let currentPoint = document.createElement('div');
            currentPoint.className = 'point-item';

            for (let i = 0; i < parts.length; i++) {
                if (parts[i].match(/^\d+\.\s$/)) {
                    if (currentPoint.textContent.trim()) {
                        formattedContent.appendChild(currentPoint);
                        currentPoint = document.createElement('div');
                        currentPoint.className = 'point-item';
                    }
                    const pointNumber = document.createElement('strong');
                    pointNumber.textContent = parts[i];
                    currentPoint.appendChild(pointNumber);
                } else if (parts[i].trim()) {
                    currentPoint.appendChild(document.createTextNode(parts[i]));
                }
            }
            if (currentPoint.textContent.trim()) {
                formattedContent.appendChild(currentPoint);
            }
            messageDiv.appendChild(formattedContent);
        } else {
            messageDiv.textContent = message;
        }
    } else {
        messageDiv.textContent = message;
    }

    const timestamp = document.createElement('div');
    timestamp.className = 'message-time';
    timestamp.textContent = getCurrentTime();
    messageDiv.appendChild(timestamp);

    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function getCurrentTime() {
    const now = new Date();
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

// ── Start ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);