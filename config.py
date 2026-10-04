"""
API配置文件
修改此文件以配置您的API密钥和端点
"""

# 多模态模型配置 (用于图片分析和拍照指导)
MULTIMODAL_CONFIG = {
    "api_key": "",  # 替换为您的API密钥
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4v-flash",
    "timeout": 30
}

# 文案生成模型配置
TEXT_MODEL_CONFIG = {
    "api_key": "",  # 替换为您的API密钥
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
    "timeout": 60
}

# 上传配置
UPLOAD_CONFIG = {
    "max_file_size": 100 * 1024 * 1024,  # 100MB
    "allowed_extensions": {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.webm'},
    "upload_folder": "uploads"
}

# Flask配置
FLASK_CONFIG = {
    "secret_key": "resale-ai-secret-key-change-in-production",
    "debug": True
}

# Supabase 云数据库配置（用于多设备数据互通）
SUPABASE_CONFIG = {
    "url": "",  # 替换为您的 Supabase 项目 URL
    "anon_key": "",  # 替换为您的 Supabase anon key
    "service_role_key": ""  # 替换为您的 Supabase service role key
}
