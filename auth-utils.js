// 共享认证工具函数

// 获取 token，优先从 localStorage，备选从 cookie
function getAuthToken() {
    const token = localStorage.getItem('auth_token');
    if (token) return token;
    
    // 从 cookie 获取
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'token') return value;
    }
    return null;
}

// 带认证的 fetch 请求
async function authFetch(url, options = {}) {
    const token = getAuthToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    return fetch(url, {
        ...options,
        headers,
        credentials: 'include'  // 包含 cookie
    });
}

// 检查是否已登录
async function checkLoggedIn() {
    const token = getAuthToken();
    if (!token) return false;
    
    try {
        const res = await authFetch('/api/auth/me');
        const data = await res.json();
        return data.success === true;
    } catch (e) {
        return false;
    }
}
