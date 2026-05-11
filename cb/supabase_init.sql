-- Supabase 数据库初始化脚本
-- 请在 Supabase Dashboard -> SQL Editor 中执行此脚本

-- 1. 创建用户表
CREATE TABLE IF NOT EXISTS users (
    uid TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login TEXT,
    avatar TEXT DEFAULT '😊',
    bio TEXT DEFAULT '',
    is_admin INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0
);

-- 2. 创建管理员表
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login TEXT,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT,
    password_changed_at TEXT
);

-- 3. 创建登录尝试记录表
CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    success INTEGER DEFAULT 0,
    user_agent TEXT
);

-- 4. 创建登录历史表
CREATE TABLE IF NOT EXISTS login_history (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    login_at TEXT NOT NULL,
    user_agent TEXT
);

-- 5. 创建用户会话表
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    uid TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- 6. 创建关注表
CREATE TABLE IF NOT EXISTS follows (
    id SERIAL PRIMARY KEY,
    follower_uid TEXT NOT NULL,
    following_uid TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(follower_uid, following_uid)
);

-- 7. 创建拉黑表
CREATE TABLE IF NOT EXISTS blocks (
    id SERIAL PRIMARY KEY,
    blocker_uid TEXT NOT NULL,
    blocked_uid TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(blocker_uid, blocked_uid)
);

-- 8. 创建商品表
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    uid TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    original_price REAL,
    description TEXT,
    images TEXT,
    video TEXT,
    video_thumb TEXT,
    category TEXT DEFAULT '其他',
    condition TEXT DEFAULT '9成新',
    status TEXT DEFAULT 'selling',
    views INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- 9. 创建默认管理员账户
-- 密码: admin123 (bcrypt哈希)
INSERT INTO admins (username, password_hash, created_at)
VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.TWi/KJNRcWgCYS', NOW()::text)
ON CONFLICT (username) DO NOTHING;

-- 10. 启用 Row Level Security (RLS) - 可选
-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE products ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- 11. 创建公开访问策略（开发环境）
-- CREATE POLICY "Allow all" ON users FOR ALL USING (true);
-- CREATE POLICY "Allow all" ON products FOR ALL USING (true);
