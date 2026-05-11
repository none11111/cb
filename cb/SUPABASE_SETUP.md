# Supabase 多设备数据互通配置指南

## 已完成的配置

1. ✅ `config.py` - 添加了 Supabase 配置
2. ✅ `requirements.txt` - 添加了 supabase 依赖
3. ✅ `app.py` - 添加了 Supabase 客户端初始化
4. ✅ `supabase_init.sql` - 创建了数据库初始化脚本

## 下一步：在 Supabase Dashboard 创建表

### 步骤 1: 登录 Supabase

1. 访问 https://supabase.com/dashboard
2. 打开你的项目

### 步骤 2: 创建数据库表

1. 在左侧菜单点击 **SQL Editor**
2. 点击 **New Query**
3. 复制 `supabase_init.sql` 文件中的内容
4. 粘贴并执行（点击 Run）

### 步骤 3: 获取正确的 API Key

从你提供的密钥格式来看，我使用了占位符。请在 Supabase Dashboard 中获取正确的密钥：

1. 点击左侧 **Project Settings**（项目设置）
2. 点击 **API**
3. 复制：
   - **Project URL**: `https://your-project-ref.supabase.co`
   - **anon public** 密钥
   - **service_role** 密钥（用于管理操作）

### 步骤 4: 更新 config.py

请在 `config.py` 中替换以下内容：

```python
SUPABASE_CONFIG = {
    "url": "你的 Project URL",
    "anon_key": "你的 anon public 密钥",
    "service_role_key": "你的 service_role 密钥"
}
```

## API 端点

### 健康检查
```
GET /api/health
```
检查 Supabase 和 SQLite 连接状态

### Supabase 状态
```
GET /api/supabase/status
```

### 同步数据（需管理员登录）
```
POST /api/supabase/sync
Authorization: Bearer <admin_token>
```
将本地 SQLite 数据同步到 Supabase

## 多设备访问

配置完成后，你可以通过以下方式访问：

1. **局域网访问**: 在同一网络下的其他设备，访问 `http://<你的IP>:5000`
2. **公网访问**: 需要配置端口映射或使用 Ngrok
3. **部署到云服务器**: 将项目部署到 Vercel、Railway、Render 等平台

## 注意事项

1. **首次使用**: 需要在 Supabase Dashboard 执行 `supabase_init.sql` 创建表
2. **数据同步**: 初始数据需要手动同步一次
3. **备份**: 建议保留本地 SQLite 数据作为备份
