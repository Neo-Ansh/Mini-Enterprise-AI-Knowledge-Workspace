// auth.js
// Handles login, register, token storage, logout

// ── Token helpers ─────────────────────────────────────────────────────

function saveAuth(data) {
    localStorage.setItem('token', data.access_token);
    if (data.user) {
        localStorage.setItem('user', JSON.stringify(data.user));
    }
}

function getToken() {
    return localStorage.getItem('token');
}

function getUser() {
    const user = localStorage.getItem('user');
    if (!user || user === 'undefined' || user === 'null') return null;
    try {
        return JSON.parse(user);
    } catch (e) {
        localStorage.removeItem('user');
        return null;
    }
}

function clearAuth() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
}

function redirectToLogin() {
    window.location.href = '/login.html';
}

function redirectToApp() {
    window.location.href = '/index.html';
}

// ── Tab switching ─────────────────────────────────────────────────────

function switchTab(tab) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const loginTab = document.getElementById('loginTab');
    const registerTab = document.getElementById('registerTab');

    if (tab === 'login') {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
        loginTab.classList.add('active');
        registerTab.classList.remove('active');
        clearError('loginError');
    } else {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
        loginTab.classList.remove('active');
        registerTab.classList.add('active');
        clearError('registerError');
    }
}

// ── Error display ─────────────────────────────────────────────────────

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message;
        el.style.display = 'block';
    }
}

function clearError(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = '';
        el.style.display = 'none';
    }
}

function setButtonLoading(btnId, loading, defaultText) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = loading ? 'Please wait...' : defaultText;
}

// ── Login ─────────────────────────────────────────────────────────────

async function handleLogin() {
    clearError('loginError');

    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;

    if (!email || !password) {
        showError('loginError', 'Please fill in all fields.');
        return;
    }

    setButtonLoading('loginBtn', true, 'Login');

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            saveAuth(data);
            redirectToApp();
        } else {
            showError('loginError', data.detail || 'Login failed.');
        }
    } catch (err) {
        showError('loginError', 'Network error. Is the server running?');
    } finally {
        setButtonLoading('loginBtn', false, 'Login');
    }
}

// ── Register ──────────────────────────────────────────────────────────

async function handleRegister() {
    clearError('registerError');

    const name = document.getElementById('registerName').value.trim();
    const email = document.getElementById('registerEmail').value.trim();
    const password = document.getElementById('registerPassword').value;

    if (!name || !email || !password) {
        showError('registerError', 'Please fill in all fields.');
        return;
    }

    if (password.length < 6) {
        showError('registerError', 'Password must be at least 6 characters.');
        return;
    }

    setButtonLoading('registerBtn', true, 'Create Account');

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password })
        });

        const data = await response.json();

        if (response.ok) {
            // ── Key fix: check if token exists in response ────────────
            // Admin → gets access_token → redirect to app
            // Worker → gets pending message → stay on login page
            if (data.access_token) {
                saveAuth(data);
                redirectToApp();
            } else {
                // Show pending approval message in green
                const el = document.getElementById('registerError');
                if (el) {
                    el.textContent = data.message || 'Registration submitted. Awaiting admin approval.';
                    el.style.color = '#10b981';
                    el.style.display = 'block';
                }
                // Clear form fields
                document.getElementById('registerName').value = '';
                document.getElementById('registerEmail').value = '';
                document.getElementById('registerPassword').value = '';
            }
        } else {
            showError('registerError', data.detail || 'Registration failed.');
        }
    } catch (err) {
        showError('registerError', 'Network error. Is the server running?');
    } finally {
        setButtonLoading('registerBtn', false, 'Create Account');
    }
}

// ── Enter key support ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
    // If already logged in, go straight to app
    if (getToken()) {
        redirectToApp();
        return;
    }

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        const loginForm = document.getElementById('loginForm');
        const registerForm = document.getElementById('registerForm');
        if (loginForm && loginForm.style.display !== 'none') {
            handleLogin();
        } else if (registerForm && registerForm.style.display !== 'none') {
            handleRegister();
        }
    });
});