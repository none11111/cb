# ResaleAI - 二手物品交易平台

一个功能完善的二手物品交易平台，支持 AI 文案生成、拍照指导、社交互动和完整交易流程。

## 功能特性

### 🛒 商品交易
- 商品发布、编辑、删除
- 商品状态管理（在售 / 已售出）
- 商品搜索与筛选
- 图片上传与管理
- 历史价格对比

### 🤖 AI 智能助手
- **文案生成**：自动生成三种风格文案
  - 💻 技术控风格 - 强调参数、性能
  - 📖 故事风格 - 情感化叙事
  - ⚡ 极简风格 - 简洁明了
- **拍照指导**：摄像头实时 AI 分析，给出拍照建议
- **推广文案**：生成小红书、朋友圈、微信群适配文案

### 👥 社交功能
- 关注 / 粉丝系统
- 拉黑 / 取消拉黑
- 私信消息
- 用户主页

### 💳 交易功能
- 订单创建与管理（待付款 / 待发货 / 待收货 / 已完成）
- 钱包余额
- 提现功能
- 收货地址管理

### 📱 PWA 支持
- 离线缓存
- 可安装到桌面
- Service Worker 加速

### ☁️ 云同步
- Supabase 云数据库
- 多设备数据互通

### 🔐 管理后台
- 用户管理（封禁 / 解封 / 删除）
- 异常行为检测
- 批量操作
- 登录日志

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + JavaScript |
| 后端 | Python Flask |
| 数据库 | SQLite + Supabase 云同步 |
| AI 接口 | OpenAI 兼容 API（支持智谱 GLM-4V） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API

编辑 `config.py`，配置您的 AI API 密钥：

```python
MULTIMODAL_CONFIG = {
    "api_key": "您的API密钥",
    "base_url": "https://api.openai.com/v1",  # 或其他兼容API
    "model": "gpt-4o",  # 支持视觉的模型
}

TEXT_MODEL_CONFIG = {
    "api_key": "您的API密钥",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4",
}
```

### 3. 运行

```bash
python app.py
```

### 4. 访问

打开浏览器访问 http://localhost:5000

## 项目结构

```
d:/zhuomian/cb/
├── app.py              # Flask 后端主程序
├── config.py           # API 配置文件
├── index.html          # 首页（AI工具 + 商品列表）
├── detail.html         # 商品详情页
├── order.html          # 订单确认页
├── orders.html         # 我的订单页
├── message.html        # 消息详情页
├── messages.html       # 消息列表页
├── profile.html        # 个人资料页
├── admin.html          # 管理后台
├── admin-login.html    # 管理员登录
├── auth.html           # 用户登录/注册
├── user.html           # 其他用户主页
├── tools.html          # AI工具页
├── auth-utils.js       # 认证工具
├── requirements.txt    # Python 依赖
├── uploads/            # 图片上传目录
└── static/             # 静态资源（PWA图标、Service Worker）
```

## API 路由

### 认证
| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 获取当前用户 |
| PUT | `/api/auth/profile` | 更新资料 |
| PUT | `/api/auth/password` | 修改密码 |
| DELETE | `/api/auth/account` | 注销账号 |

### 商品
| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/products` | 商品列表 |
| GET | `/api/product/<id>` | 商品详情 |
| POST | `/api/product` | 发布商品 |
| PUT | `/api/product/<id>/status` | 更新状态 |
| PUT | `/api/my-products/edit/<id>` | 编辑商品 |
| DELETE | `/api/my-products/batch-delete` | 批量删除 |
| GET | `/api/compare/<id>` | 价格对比 |
| GET | `/api/search` | 搜索商品 |

### 订单
| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/orders` | 订单列表 |
| POST | `/api/orders` | 创建订单 |
| GET | `/api/orders/<id>` | 订单详情 |
| POST | `/api/orders/<id>/update` | 更新订单状态 |

### 社交
| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/user/<uid>` | 用户主页 |
| GET | `/api/user/relations` | 关注/粉丝列表 |
| POST | `/api/user/follow` | 关注 |
| DELETE | `/api/user/follow` | 取消关注 |
| POST | `/api/user/block` | 拉黑 |
| DELETE | `/api/user/block` | 取消拉黑 |
| GET | `/api/favorites` | 我的收藏 |
| POST | `/api/favorites` | 添加收藏 |
| DELETE | `/api/favorites/<id>` | 取消收藏 |

### 消息
| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/messages` | 消息列表 |
| POST | `/api/messages` | 发送消息 |
| GET | `/api/messages/conversations` | 会话列表 |

### 钱包与地址
| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/wallet` | 钱包余额 |
| POST | `/api/wallet/withdraw` | 提现申请 |
| GET | `/api/addresses` | 收货地址列表 |
| POST | `/api/addresses` | 添加地址 |
| PUT | `/api/addresses/<id>` | 编辑地址 |
| DELETE | `/api/addresses/<id>` | 删除地址 |

### 管理后台
| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/admin/login` | 管理员登录 |
| GET | `/api/admin/users` | 用户列表 |
| POST | `/api/admin/user/<uid>/ban` | 封禁用户 |
| POST | `/api/admin/user/<uid>/unban` | 解封用户 |
| POST | `/api/admin/users/batch-ban` | 批量封禁 |
| DELETE | `/api/admin/users/batch-delete` | 批量删除 |
| GET | `/api/admin/anomaly-detection` | 异常检测 |

## 部署指南

### 本地快速运行

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API
# 编辑 config.py 填入 API 密钥

# 运行
python app.py
```

### 生产环境（Nginx + Gunicorn）

```bash
pip install gunicorn eventlet
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
    }

    location /uploads {
        alias /path/to/cb/uploads;
    }
}
```

```bash
gunicorn -w 4 -k eventlet -b 0.0.0.0:5000 app:app
```

### Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn eventlet
COPY . .
RUN mkdir -p uploads
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-k", "eventlet", "-b", "0.0.0.0:5000", "app:app"]
```

```bash
docker build -t resaleai .
docker run -d -p 5000:5000 -v $(pwd)/uploads:/app/uploads resaleai
```

## 数据库

- **本地**：SQLite（`users.db`, `products.db`, `market.db`）
- **云端**：Supabase PostgreSQL（可选，用于多设备同步）

## 常见问题

**Q: 图片上传失败？**
A: 确保 `uploads` 目录存在且有写入权限。

**Q: API 请求失败？**
A: 检查 `config.py` 中的 API 配置，确保网络正常。

**Q: 如何成为管理员？**
A: 使用管理员账号登录 admin-login.html。（账户：admin 默认密码：admin123）

## License

MIT License
