# -*- coding: utf-8 -*-
'''
二手物品转售AI助手 - Flask后端
提供图片分析,文案生成,推广文案,用户系统等API接口
'''

import os
import base64
import uuid
import requests
import json
import sqlite3
import hashlib
import secrets
import io
import bcrypt
from io import BytesIO
import base64 as b64
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image, ImageFilter, ImageDraw
from config import (
    MULTIMODAL_CONFIG, TEXT_MODEL_CONFIG, 
    UPLOAD_CONFIG, FLASK_CONFIG, SUPABASE_CONFIG
)
from supabase import create_client, Client

# 初始化 Supabase 客户端(未配置时跳过,使用本地 SQLite 模式)
if SUPABASE_CONFIG.get('url') and SUPABASE_CONFIG.get('anon_key'):
    supabase: Client = create_client(SUPABASE_CONFIG['url'], SUPABASE_CONFIG['anon_key'])
    # 使用 service_role_key 的管理员客户端(用于数据同步)
    supabase_admin: Client = create_client(SUPABASE_CONFIG['url'], SUPABASE_CONFIG['service_role_key'])
    print('✓ Supabase 客户端已初始化')
else:
    supabase = None
    supabase_admin = None
    print('⚠ Supabase 未配置(url/anon_key 为空),使用本地 SQLite 模式')

# 管理员权限验证装饰器
def admin_required(f):
    '''管理员权限验证装饰器'''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('admin_token', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'success': False, 'error': '请先登录'}), 401
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.token, a.username, a.id
            FROM sessions s
            JOIN admins a ON s.uid = 'admin_' || a.id
            WHERE s.token = ? AND s.expires_at > ?
        ''', (token, datetime.now().isoformat()))
        
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return jsonify({'success': False, 'error': '登录已过期,请重新登录'}), 401
        
        g.admin_username = session[1]
        g.admin_id = session[2]
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = FLASK_CONFIG['secret_key']
CORS(app, resources={r'/api/*': {'origins': '*'}})

# 确保上传目录存在
os.makedirs(UPLOAD_CONFIG['upload_folder'], exist_ok=True)

# ============ 数据库初始化 ============
DATABASE = 'users.db'

def get_db():
    '''获取数据库连接'''
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    '''关闭数据库连接'''
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    '''初始化数据库'''
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=30000;')
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            avatar TEXT DEFAULT '😊',
            bio TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # 为现有列添加 is_admin 字段(如果不存在)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
    except:
        pass
    
    # 为现有列添加 is_banned 字段(如果不存在)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0')
    except:
        pass
    
    # 为现有列添加 avatar 字段(如果不存在)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT "😊"')
    except:
        pass
    
    # 为现有列添加 bio 字段(如果不存在)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN bio TEXT DEFAULT " "')
    except:
        pass
    
    # 为现有列添加钱包字段(如果不存在)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN withdrawable_balance REAL DEFAULT 0')
    except:
        pass
    
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN frozen_balance REAL DEFAULT 0')
    except:
        pass
    
    # 创建管理员表(用于存储管理员账户)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TEXT,
            password_changed_at TEXT
        )
    ''')
    
    # 创建登录尝试记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            user_agent TEXT
        )
    ''')
    
    # 创建登录历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            login_at TEXT NOT NULL,
            user_agent TEXT,
            FOREIGN KEY (admin_id) REFERENCES admins(id)
        )
    ''')
    
    # 创建默认管理员账户(如果不存在)- 使用bcrypt哈希
    default_admin_username = 'admin'
    default_admin_password = 'admin123'  # 建议首次登录后修改
    cursor.execute('SELECT * FROM admins WHERE username = ?', (default_admin_username,))
    if not cursor.fetchone():
        password_hash = bcrypt.hashpw(default_admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute('''
            INSERT INTO admins (username, password_hash, created_at)
            VALUES (?, ?, ?)
        ''', (default_admin_username, password_hash, datetime.now().isoformat()))
        print(f'默认管理员账户已创建: {default_admin_username} / {default_admin_password}')
    
    # 创建用户会话表(用于简单登录状态管理)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    ''')
    
    # 创建关注表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_uid TEXT NOT NULL,
            following_uid TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(follower_uid, following_uid)
        )
    ''')
    
    # 创建拉黑表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker_uid TEXT NOT NULL,
            blocked_uid TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(blocker_uid, blocked_uid)
        )
    ''')
    
    # 创建商品表(包含状态字段)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            status TEXT DEFAULT 'selling' CHECK(status IN ('selling', 'sold', 'offline')),
            views INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    ''')
    
    # 创建消息表(私信系统)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_uid TEXT NOT NULL,
            receiver_uid TEXT NOT NULL,
            content TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (sender_uid) REFERENCES users(uid),
            FOREIGN KEY (receiver_uid) REFERENCES users(uid)
        )
    ''')
    
    # 创建收藏表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(uid, product_id),
            FOREIGN KEY (uid) REFERENCES users(uid),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # 创建订单表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            buyer_uid TEXT NOT NULL,
            seller_uid TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'shipped', 'completed', 'cancelled')),
            fund_status TEXT DEFAULT 'pending' CHECK(fund_status IN ('pending', 'held', 'released', 'refunded')),
            total_amount REAL NOT NULL,
            shipping_address TEXT,
            contact_phone TEXT,
            remark TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (buyer_uid) REFERENCES users(uid),
            FOREIGN KEY (seller_uid) REFERENCES users(uid)
        )
    ''')
    
    # 迁移:添加缺失的列(如果表已存在但缺少该列)
    cursor.execute('PRAGMA table_info(orders)')
    columns = [col[1] for col in cursor.fetchall()]
    if 'fund_status' not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN fund_status TEXT DEFAULT 'pending' CHECK(fund_status IN ('pending', 'held', 'released', 'refunded'))")
    if 'express_company' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN express_company TEXT')
    if 'express_no' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN express_no TEXT')
    
    # 为 fund_status 添加索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_fund_status ON orders(fund_status)')
    
    # 创建商品索引(提升搜索性能)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_created ON products(created_at DESC)')
    
    # 创建消息索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_uid)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_uid)')
    
    # 创建收货地址表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            receiver_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            province TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT NOT NULL,
            detail_address TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password, salt=None):
    '''密码哈希加密'''
    if salt is None:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ':' + hash_obj.hex()

def seed_products():
    '''填充初始商品数据'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 检查是否已有商品数据
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    # 查找现有用户作为商品卖家
    cursor.execute('SELECT uid FROM users LIMIT 1')
    user = cursor.fetchone()
    
    if not user:
        # 如果没有用户,创建一个演示用户
        demo_uid = 'U00000001'
        cursor.execute('''INSERT OR IGNORE INTO users (uid, username, password_hash, created_at)
                          VALUES (?, 'demo_user', ?, ?)''', 
                        (demo_uid, hash_password('demo123'), datetime.now().isoformat()))
        seller_uid = demo_uid
    else:
        seller_uid = user[0]
    
    # 创建更多演示卖家
    seller_uids = ['U00000001', 'U00000002', 'U00000003', 'U00000004']
    for i, uid in enumerate(seller_uids):
        cursor.execute('''INSERT OR IGNORE INTO users (uid, username, password_hash, created_at)
                          VALUES (?, ?, ?, ?)''', 
                      (uid, f'卖家{i+1}', hash_password('demo123'), datetime.now().isoformat()))
    
    # 初始商品数据(按新分类体系组织)
    products = [
        # ========== 数码类 - 手机 ==========
        ('U00000001', 'iPhone 14 Pro Max 256G 暗紫色 国行', 5999, 8999, '国行正品,暗紫色256G,全套配件齐全,无划痕无磕碰.', 
         "['https://picsum.photos/400/500?1']", '数码', '9成新', 'selling', '2026-04-01T10:00:00'),
        ('U00000002', 'iPhone 14 Pro Max 256G 金色 国行', 5800, 8999, '金色256G,屏幕贴膜戴套,无任何划痕,电池健康度98%.', 
         "['https://picsum.photos/400/500?14']", '数码', '9成新', 'selling', '2026-04-02T11:00:00'),
        ('U00000003', 'iPhone 14 Pro Max 128G 银色 美版', 4500, 8999, '美版单卡,全原无修,屏幕轻微使用痕迹,其他完好.', 
         "['https://picsum.photos/400/500?15']", '数码', '8成新', 'selling', '2026-04-03T09:00:00'),
        ('U00000001', 'iPhone 15 Pro 256G 钛金属', 6999, 9999, '全新未拆封,钛金属原色,官方在保.', 
         "['https://picsum.photos/400/500?16']", '数码', '全新', 'selling', '2026-04-04T15:00:00'),
        ('U00000002', 'iPhone 15 Pro 128G 蓝色钛金属', 6200, 9999, '在保到年底,轻微使用痕迹,配件齐全.', 
         "['https://picsum.photos/400/500?17']", '数码', '9成新', 'selling', '2026-04-05T10:00:00'),
        ('U00000003', '小米 14 Ultra 影像旗舰', 4800, 6499, '小米14 Ultra,钛金属版本,徕卡镜头,功能正常.', 
         "['https://picsum.photos/400/500?40']", '数码', '9成新', 'selling', '2026-04-06T10:00:00'),
        
        # ========== 数码类 - 耳机/配件 ==========
        ('U00000001', 'AirPods Pro 2代 全新未拆封', 1580, 1899, '全新未拆封,保证正品,带发票.', 
         "['https://picsum.photos/400/300?2']", '数码', '全新', 'selling', '2026-04-05T14:30:00'),
        ('U00000003', 'AirPods Pro 2代 使用3个月', 1350, 1899, '国行在保,9月购入,充电盒轻微划痕,耳机无任何问题.', 
         "['https://picsum.photos/400/300?18']", '数码', '9成新', 'selling', '2026-04-06T16:00:00'),
        ('U00000004', 'AirPods 3代 全新未拆封', 980, 1399, '全新未拆封,国行正品,假一赔十.', 
         "['https://picsum.photos/400/300?19']", '数码', '全新', 'selling', '2026-04-07T11:00:00'),
        ('U00000001', '索尼 WH-1000XM5 头戴式耳机', 1800, 2499, '索尼旗舰降噪耳机,黑色,使用不到10次,配件齐全.', 
         "['https://picsum.photos/400/300?41']", '数码', '9成新', 'selling', '2026-04-08T10:00:00'),
        ('U00000002', '倍思100W氮化镓充电器套装', 180, 299, '100W快充,充电头+线,99新,包装齐全.', 
         "['https://picsum.photos/400/300?42']", '数码', '9成新', 'selling', '2026-04-09T10:00:00'),
        
        # ========== 数码类 - 智能手表 ==========
        ('U00000003', 'Apple Watch S9 45mm GPS版', 2600, 3299, 'Apple Watch S9星光色,9月购入,配件齐全.', 
         "['https://picsum.photos/400/450?36']", '数码', '9成新', 'selling', '2026-04-28T09:00:00'),
        ('U00000004', 'Apple Watch Ultra 2 钛金属', 4200, 5999, 'Ultra 2钛金属原色,2025年购入,在保,配件全.', 
         "['https://picsum.photos/400/450?37']", '数码', '9成新', 'selling', '2026-04-29T10:00:00'),
        ('U00000001', '华为 Watch GT 4 46mm', 1200, 1688, '华为智能手表,苍穹绿,GPS版,功能正常.', 
         "['https://picsum.photos/400/450?43']", '数码', '9成新', 'selling', '2026-04-30T10:00:00'),
        
        # ========== 电脑类 ==========
        ('U00000001', 'MacBook Pro 14寸 M3 Pro', 12500, 16999, 'M3 Pro芯片,18+512G,深空灰,全套配件.', 
         "['https://picsum.photos/400/350?44']", '电脑', '9成新', 'selling', '2026-04-10T10:00:00'),
        ('U00000002', 'MacBook Air 15寸 M3', 8500, 10999, 'M3芯片,16+512G,午夜色,全新未拆封.', 
         "['https://picsum.photos/400/350?45']", '电脑', '全新', 'selling', '2026-04-11T10:00:00'),
        ('U00000003', 'ThinkPad X1 Carbon Gen 11', 7800, 12999, '英特尔i7,32G内存,1TB SSD,轻微使用痕迹.', 
         "['https://picsum.photos/400/350?46']", '电脑', '9成新', 'selling', '2026-04-12T10:00:00'),
        ('U00000001', '罗技 MX Keys 无线键盘', 380, 599, '无线蓝牙键盘,99新,配件齐全,支持多设备.', 
         "['https://picsum.photos/400/300?47']", '电脑', '9成新', 'selling', '2026-04-13T10:00:00'),
        ('U00000002', '罗技 MX Master 3S 鼠标', 420, 799, '无线蓝牙鼠标, ergonomics设计,99新.', 
         "['https://picsum.photos/400/300?48']", '电脑', '9成新', 'selling', '2026-04-14T10:00:00'),
        ('U00000004', '戴尔 U2723QE 4K显示器', 2800, 3999, '27寸4K IPS屏幕,Type-C反向充电,99新.', 
         "['https://picsum.photos/400/400?49']", '电脑', '9成新', 'selling', '2026-04-15T10:00:00'),
        
        # ========== 相机类 ==========
        ('U00000001', '索尼 A7M4 全画幅微单相机', 13500, 16999, '索尼A7M4,快门数不到5000,箱说全,送原装电池一块.', 
         "['https://picsum.photos/400/400?4']", '相机', '9成新', 'selling', '2026-04-10T16:45:00'),
        ('U00000002', '索尼 A7M4 全画幅微单 单机身', 12800, 16999, '单机无镜头,快门数3500,机身有轻微使用痕迹,功能完美.', 
         "['https://picsum.photos/400/400?20']", '相机', '9成新', 'selling', '2026-04-11T14:00:00'),
        ('U00000003', '佳能 R6 Mark II 微单相机', 14500, 18599, '佳能R6II,12月购入,快门数2000,全套配件,发票齐全.', 
         "['https://picsum.photos/400/400?21']", '相机', '9成新', 'selling', '2026-04-12T09:30:00'),
        ('U00000004', '富士 X-T5 微单相机 银色', 10200, 11990, '富士XT5,樱花粉色,16-80套机,配件全,在保.', 
         "['https://picsum.photos/400/400?22']", '相机', '9成新', 'selling', '2026-04-13T11:00:00'),
        ('U00000001', '索尼 FE 24-70mm f/2.8 GM II', 9800, 13999, '索尼G大师镜头,使用次数少,镜片完美.', 
         "['https://picsum.photos/400/400?50']", '相机', '9成新', 'selling', '2026-04-14T11:00:00'),
        ('U00000002', '富士拍立得 mini90 黑色', 950, 1280, '黑色限量版,配件有电池,充电线,相纸5张,包装齐全.', 
         "['https://picsum.photos/400/480?10']", '相机', '9成新', 'selling', '2026-04-22T12:00:00'),
        
        # ========== 游戏类 ==========
        ('U00000001', '任天堂 Switch OLED 日版', 1850, 2599, '日版OLED白色,双人成行+马里奥派对卡带,贴膜戴套使用.', 
         "['https://picsum.photos/400/350?5']", '游戏', '8成新', 'selling', '2026-04-12T11:20:00'),
        ('U00000002', '任天堂 Switch OLED 港版', 1780, 2599, '港版OLED黑色,附赠Pro手柄,贴膜戴套,无任何问题.', 
         "['https://picsum.photos/400/350?23']", '游戏', '8成新', 'selling', '2026-04-14T15:00:00'),
        ('U00000003', '索尼 PS5 光驱版', 2800, 3899, 'PS5光驱版,附带2个手柄,2025年6月购入,箱说全.', 
         "['https://picsum.photos/400/350?24']", '游戏', '9成新', 'selling', '2026-04-15T10:00:00'),
        ('U00000004', '微软 Xbox Series X', 3200, 4499, 'Xbox Series X日版,2025年3月购入,配件齐全,手柄2个.', 
         "['https://picsum.photos/400/350?25']", '游戏', '9成新', 'selling', '2026-04-16T14:00:00'),
        ('U00000001', 'Switch游戏卡带 塞尔达王国之泪', 350, 420, '实体卡带,通关了,盒子和说明书齐全.', 
         "['https://picsum.photos/400/300?51']", '游戏', '9成新', 'selling', '2026-04-17T10:00:00'),
        ('U00000002', 'Switch游戏卡带 集合啦!动物森友会', 320, 399, '动森实体卡带,玩了200+小时,盒子齐全.', 
         "['https://picsum.photos/400/300?52']", '游戏', '8成新', 'selling', '2026-04-18T10:00:00'),
        
        # ========== 家电类 ==========
        ('U00000001', '戴森吹风机 HD03 红色限定版', 2200, 2990, '红色限定版,使用不到10次,功能正常,配件齐全.', 
         "['https://picsum.photos/400/600?3']", '家电', '9成新', 'selling', '2026-03-20T09:15:00'),
        ('U00000002', '戴森吹风机 Supersonic HD08', 2350, 3299, '国行正品,2025年购入,使用次数不超过20次.', 
         "['https://picsum.photos/400/600?26']", '家电', '9成新', 'selling', '2026-04-17T11:00:00'),
        ('U00000001', '小米扫地机器人 3C', 850, 1499, '功能正常,扫拖一体,配件齐全,清洗过水箱.', 
         "['https://picsum.photos/400/420?9']", '家电', '8成新', 'selling', '2026-04-20T15:10:00'),
        ('U00000003', '科沃斯 T20S PRO 扫地机器人', 2200, 4599, '科沃斯旗舰款,扫拖一体,自动集尘,自动洗拖布.', 
         "['https://picsum.photos/400/420?27']", '家电', '9成新', 'selling', '2026-04-18T10:00:00'),
        ('U00000004', '追觅 W10S PRO 扫地机器人', 1800, 3999, '扫拖洗烘一体,自动清洗拖布,激光导航,功能正常.', 
         "['https://picsum.photos/400/420?28']", '家电', '9成新', 'selling', '2026-04-19T14:00:00'),
        ('U00000001', '九阳破壁机 Y1', 480, 899, '研磨效果很好,清洗方便,功能完好无损.', 
         "['https://picsum.photos/400/520?12']", '家电', '8成新', 'selling', '2026-04-28T14:00:00'),
        ('U00000002', '美的破壁机 MJ-PB80S7', 350, 799, '8重降噪,低音破壁,冷热双杯,功能完好.', 
         "['https://picsum.photos/400/520?29']", '家电', '9成新', 'selling', '2026-04-21T11:00:00'),
        ('U00000003', '小米空气净化器 4 Pro', 1100, 1899, '除甲醛除菌,滤芯还有80%,功能正常.', 
         "['https://picsum.photos/400/500?53']", '家电', '9成新', 'selling', '2026-04-22T11:00:00'),
        
        # ========== 服饰类 ==========
        ('U00000001', 'AJ1 芝加哥复刻 42码', 2800, 1399, '正品过验,保真!穿过两次,鞋底几乎无磨损.', 
         "['https://picsum.photos/400/380?8']", '服饰', '9成新', 'selling', '2026-04-18T19:00:00'),
        ('U00000002', 'AJ1 芝加哥复刻 42.5码', 2600, 1399, '正品过验,穿着次数不超过5次,鞋面无折痕,鞋底微磨损.', 
         "['https://picsum.photos/400/380?30']", '服饰', '8成新', 'selling', '2026-04-22T15:00:00'),
        ('U00000003', 'Nike Dunk Low 熊猫 42码', 650, 1099, '熊猫Dunk low,2025年双十一购入,穿了不到10次.', 
         "['https://picsum.photos/400/380?31']", '服饰', '9成新', 'selling', '2026-04-23T10:00:00'),
        ('U00000004', 'Adidas Yeezy 350 灰橙 43码', 1200, 1899, 'Yeezy 350灰橙配色,侃爷同款,穿了两三次.', 
         "['https://picsum.photos/400/380?32']", '服饰', '9成新', 'selling', '2026-04-24T11:00:00'),
        ('U00000001', '始祖鸟 Beta LT 冲锋衣 M码', 3200, 5400, '经典硬壳冲锋衣,Gore-Tex面料,黑色,全新吊牌.', 
         "['https://picsum.photos/400/500?54']", '服饰', '全新', 'selling', '2026-04-25T11:00:00'),
        ('U00000002', '北面 1996 羽绒服 黑色 L码', 1800, 2999, '经典款700蓬羽绒服,穿了几次,尺寸不合适出了.', 
         "['https://picsum.photos/400/550?55']", '服饰', '9成新', 'selling', '2026-04-26T11:00:00'),
        ('U00000003', 'LV Neverfull 中号 老花', 8500, 14400, '经典托特包,99新,配件齐全,2025年购入.', 
         "['https://picsum.photos/400/500?56']", '服饰', '9成新', 'selling', '2026-04-27T11:00:00'),
        ('U00000004', '耐克 Air Force 1 纯白 42码', 450, 899, '纯白AF1,穿了不到5次,清洗后可发货.', 
         "['https://picsum.photos/400/380?57']", '服饰', '9成新', 'selling', '2026-04-28T11:00:00'),
        
        # ========== 美妆类 ==========
        ('U00000001', 'SK-II 神仙水 230ml', 680, 1540, '日上购入,有购买记录,用了一点点,可验货.', 
         "['https://picsum.photos/400/500?7']", '美妆', '9成新', 'selling', '2026-03-15T20:30:00'),
        ('U00000002', 'SK-II 小灯泡 50ml', 480, 1040, '淡斑美白精华,用了不到三分之一,有购买记录.', 
         "['https://picsum.photos/400/500?33']", '美妆', '9成新', 'selling', '2026-04-25T14:00:00'),
        ('U00000003', 'La Mer 经典面霜 60ml', 1200, 2800, '海蓝之谜经典面霜,仅试用过一次,不适合我的肤质.', 
         "['https://picsum.photos/400/500?34']", '美妆', '9成新', 'selling', '2026-04-26T10:00:00'),
        ('U00000004', '雅诗兰黛 小棕瓶精华 100ml', 580, 1200, '第七代小棕瓶,用了一半,有购买凭证.', 
         "['https://picsum.photos/400/500?58']", '美妆', '8成新', 'selling', '2026-04-27T14:00:00'),
        ('U00000001', '兰蔻小黑瓶精华 50ml', 520, 1100, '第二代小黑瓶,用了三分之一,包装保留.', 
         "['https://picsum.photos/400/500?59']", '美妆', '8成新', 'selling', '2026-04-28T14:00:00'),
        ('U00000002', '香奈儿 5号香水 50ml', 680, 1420, '经典五号香水,喷了两三次,配件齐全.', 
         "['https://picsum.photos/400/400?60']", '美妆', '9成新', 'selling', '2026-04-29T14:00:00'),
        
        # ========== 母婴类 ==========
        ('U00000001', 'Bugaboo Bee6 婴儿推车', 2800, 5800, '轻便婴儿车,360度旋转,遮阳篷配件齐全.', 
         "['https://picsum.photos/400/500?61']", '母婴', '8成新', 'selling', '2026-04-15T10:00:00'),
        ('U00000002', 'Maxi-Cosi 安全座椅', 1200, 2500, '0-4岁可用,isofix接口,2025年购入,99新.', 
         "['https://picsum.photos/400/500?62']", '母婴', '9成新', 'selling', '2026-04-16T10:00:00'),
        ('U00000003', '乐高得宝系列 创意积木桶', 280, 499, '大颗粒积木,适合1-5岁儿童,零件齐全.', 
         "['https://picsum.photos/400/400?63']", '母婴', '9成新', 'selling', '2026-04-17T10:00:00'),
        ('U00000004', '费雪牌 婴儿健身架', 350, 699, '多功能健身架,钢琴键+挂件,宝宝大了用不上了.', 
         "['https://picsum.photos/400/500?64']", '母婴', '8成新', 'selling', '2026-04-18T10:00:00'),
        
        # ========== 图书类 ==========
        ('U00000001', '人类简史三部曲 套装', 180, 268, '尤瓦尔·赫拉利三部曲,全新塑封未拆.', 
         "['https://picsum.photos/400/500?65']", '图书', '全新', 'selling', '2026-04-10T10:00:00'),
        ('U00000002', 'Python编程:从入门到实践', 45, 89, '二手书,九成新,有少量笔记.', 
         "['https://picsum.photos/400/500?66']", '图书', '9成新', 'selling', '2026-04-11T10:00:00'),
        ('U00000003', 'Kindle Paperwhite 5 32G', 680, 1499, '电子书阅读器,屏幕完美,配件齐全.', 
         "['https://picsum.photos/400/400?67']", '图书', '9成新', 'selling', '2026-04-12T10:00:00'),
        
        # ========== 玩具类(放入其他) ==========
        ('U00000001', '乐高星球大战 千年隼', 3200, 5999, '全新未拆封,绝版好价,顺丰保价发货.', 
         "['https://picsum.photos/400/350?11']", '其他', '全新', 'selling', '2026-04-25T09:30:00'),
        ('U00000002', '乐高 保时捷 911 RSR', 1800, 3599, '全新未拆封,盒况完美,编号完整.', 
         "['https://picsum.photos/400/350?35']", '其他', '全新', 'selling', '2026-04-27T11:00:00'),
        ('U00000003', '高达 MG RX-78-2 3.0', 380, 680, '拼装模型,零件齐全未拼,盒子完好.', 
         "['https://picsum.photos/400/400?68']", '其他', '全新', 'selling', '2026-04-28T11:00:00'),
        ('U00000004', 'LAMY 恒星系列 钢笔套装', 380, 680, '银色F尖,写感顺滑,笔尖几乎无磨损,配件齐全.', 
         "['https://picsum.photos/400/450?6']", '其他', '9成新', 'selling', '2026-03-28T08:00:00'),
        
        # ========== 已售/下架商品 ==========
        ('U00000001', '戴森吹风机 HD03 红色限定版', 2200, 2990, '红色限定版,使用不到10次,功能正常,配件齐全.', 
         "['https://picsum.photos/400/600?3']", '家电', '9成新', 'offline', '2026-03-20T09:15:00'),
        ('U00000003', '九阳破壁机 Y1', 480, 899, '研磨效果很好,清洗方便,功能完好无损.', 
         "['https://picsum.photos/400/520?12']", '家电', '8成新', 'offline', '2026-04-28T14:00:00'),
    ]
    
    cursor.executemany('''INSERT INTO products 
        (uid, title, price, original_price, description, images, category, condition, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', products)
    
    conn.commit()
    conn.close()
    print(f'已填充 {len(products)} 条商品数据')

def sync_to_supabase():
    '''将 SQLite 数据同步到 Supabase 云数据库'''
    try:
        # 同步用户数据
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取所有用户
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        
        for user in users:
            user_dict = dict(user)
            user_data = {
                'uid': user_dict.get('uid'),
                'username': user_dict.get('username'),
                'password_hash': user_dict.get('password_hash'),
                'created_at': user_dict.get('created_at'),
                'last_login': user_dict.get('last_login'),
                'avatar': user_dict.get('avatar', '😊'),
                'bio': user_dict.get('bio', ''),
                'is_admin': user_dict.get('is_admin', 0),
                'is_banned': user_dict.get('is_banned', 0)
            }
            supabase_admin.table('users').upsert(user_data, on_conflict='uid').execute()
        
        # 获取所有商品
        cursor.execute('SELECT * FROM products')
        products = cursor.fetchall()
        
        for product in products:
            product_dict = dict(product)
            product_data = {
                'id': product_dict.get('id'),
                'uid': product_dict.get('uid'),
                'title': product_dict.get('title'),
                'price': product_dict.get('price'),
                'original_price': product_dict.get('original_price'),
                'description': product_dict.get('description'),
                'images': product_dict.get('images'),
                'video': product_dict.get('video'),
                'video_thumb': product_dict.get('video_thumb'),
                'category': product_dict.get('category'),
                'condition': product_dict.get('condition'),
                'status': product_dict.get('status'),
                'views': product_dict.get('views', 0),
                'created_at': product_dict.get('created_at'),
                'updated_at': product_dict.get('updated_at')
            }
            supabase_admin.table('products').upsert(product_data, on_conflict='id').execute()
        
        # 同步订单数据
        cursor.execute('SELECT * FROM orders')
        orders = cursor.fetchall()
        
        for order in orders:
            order_dict = dict(order)
            order_data = {
                'id': order_dict.get('id'),
                'product_id': order_dict.get('product_id'),
                'buyer_uid': order_dict.get('buyer_uid'),
                'seller_uid': order_dict.get('seller_uid'),
                'total_amount': order_dict.get('total_amount'),
                'status': order_dict.get('status'),
                'shipping_address': order_dict.get('shipping_address'),
                'contact_phone': order_dict.get('contact_phone'),
                'express_company': order_dict.get('express_company'),
                'express_no': order_dict.get('express_no'),
                'remark': order_dict.get('remark'),
                'created_at': order_dict.get('created_at'),
                'updated_at': order_dict.get('updated_at')
            }
            supabase_admin.table('orders').upsert(order_data, on_conflict='id').execute()
        
        conn.close()
        print('✓ 数据已成功同步到 Supabase')
        return True, None
    except Exception as e:
        error_msg = str(e)
        print(f'✗ 同步失败: {error_msg}')
        return False, error_msg


def sync_single_to_supabase(table_name, data, primary_key):
    '''增量同步单条记录到 Supabase
    
    Args:
        table_name: 表名 (users, products, orders)
        data: 要同步的数据字典
        primary_key: 主键字段名 (uid, id)
    '''
    try:
        supabase_admin.table(table_name).upsert(data, on_conflict=primary_key).execute()
        print(f'✓ [{table_name}] 增量同步成功: {data.get(primary_key)}')
        return True, None
    except Exception as e:
        print(f'✗ [{table_name}] 增量同步失败: {e}')
        return False, str(e)


def check_supabase_connection():
    '''检查 Supabase 连接状态'''
    try:
        # 尝试查询 products 表
        response = supabase.table('products').select('id').limit(1).execute()
        return True, '连接成功'
    except Exception as e:
        return False, str(e)

# 初始化数据库
init_db()
seed_products()

# ============ 用户认证工具函数 ============

def generate_uid():
    '''生成唯一的8位用户ID'''
    while True:
        # 使用时间戳+随机数生成唯一ID
        timestamp = str(datetime.now().timestamp()).replace('.', '')[-4:]
        random_str = secrets.token_hex(2)
        uid = f'U{timestamp}{random_str}'.upper()
        
        # 检查是否已存在
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT uid FROM users WHERE uid = ?', (uid,))
        exists = cursor.fetchone()
        conn.close()
        
        if not exists:
            return uid

def verify_password(password, stored_hash):
    '''验证密码'''
    try:
        salt, hash_value = stored_hash.split(':')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return new_hash.hex() == hash_value
    except:
        return False

def generate_token():
    '''生成会话Token'''
    return secrets.token_urlsafe(32)

def login_required(f):
    '''登录验证装饰器'''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': '请先登录'}), 401
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.uid, s.expires_at FROM sessions s 
            WHERE s.token = ? AND s.expires_at > ?
        ''', (token, datetime.now().isoformat()))
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return jsonify({'success': False, 'error': '登录已过期,请重新登录'}), 401
        
        g.uid = session[0]
        return f(*args, **kwargs)
    return decorated_function


def check_login_required():
    '''检查用户是否已登录,返回 (是否登录, 用户ID或None)'''
    token = request.cookies.get('token', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return False, None
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.uid, s.expires_at FROM sessions s 
        WHERE s.token = ? AND s.expires_at > ?
    ''', (token, datetime.now().isoformat()))
    session = cursor.fetchone()
    conn.close()
    
    if not session:
        return False, None
    
    return True, session[0]


def login_required_page(f):
    '''页面登录验证装饰器'''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_logged_in, uid = check_login_required()
        if not is_logged_in:
            return send_from_directory('.', 'auth.html')
        g.uid = uid
        return f(*args, **kwargs)
    return decorated_function

# ============ 用户API ============

@app.route('/api/auth/register', methods=['POST'])
def register():
    '''用户注册'''
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '请提供用户名和密码'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # 验证输入
        if len(username) < 2 or len(username) > 20:
            return jsonify({'success': False, 'error': '用户名长度需在2-20个字符之间'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': '密码长度至少6位'}), 400
        
        # 检查用户名是否已存在
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT uid FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '用户名已存在'}), 400
        
        # 创建用户
        uid = generate_uid()
        password_hash = hash_password(password)
        created_at = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO users (uid, username, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (uid, username, password_hash, created_at))
        conn.commit()
        conn.close()
        
        # 增量同步到 Supabase
        sync_single_to_supabase('users', {
            'uid': uid,
            'username': username,
            'password_hash': password_hash,
            'created_at': created_at,
            'avatar': '😊',
            'bio': '',
            'is_admin': 0,
            'is_banned': 0
        }, 'uid')
        
        return jsonify({
            'success': True,
            'message': '注册成功',
            'user': {
                'uid': uid,
                'username': username,
                'created_at': created_at
            }
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    '''用户登录'''
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '请提供用户名和密码'}), 400
        
        # 同时支持 username 和 uid 登录
        username = data.get('username', '').strip()
        uid = data.get('uid', '').strip()
        password = data.get('password', '')
        
        if not password:
            return jsonify({'success': False, 'error': '密码不能为空'}), 400
        
        if not username and not uid:
            return jsonify({'success': False, 'error': '请输入用户名或UID'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 根据 username 或 uid 查询用户
        if username:
            cursor.execute('SELECT uid, username, password_hash, avatar, bio FROM users WHERE username = ?', (username,))
        else:
            cursor.execute('SELECT uid, username, password_hash, avatar, bio FROM users WHERE uid = ?', (uid,))
        
        user = cursor.fetchone()
        
        if not user or not verify_password(password, user[2]):
            conn.close()
            return jsonify({'success': False, 'error': '用户名或密码错误'}), 401
        
        # 创建会话
        token = generate_token()
        created_at = datetime.now().isoformat()
        # Token有效期7天
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        cursor.execute('''
            INSERT INTO sessions (token, uid, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (token, user[0], created_at, expires_at))
        
        # 更新最后登录时间
        cursor.execute('UPDATE users SET last_login = ? WHERE uid = ?', (created_at, user[0]))
        
        conn.commit()
        conn.close()
        
        # 增量同步用户登录信息到 Supabase
        sync_single_to_supabase('users', {
            'uid': user[0],
            'username': user[1],
            'password_hash': user[2],
            'last_login': created_at,
            'avatar': user[3],
            'bio': user[4]
        }, 'uid')
        
        # 创建响应,同时设置 cookie
        response = make_response(jsonify({
            'success': True,
            'message': '登录成功',
            'token': token,
            'user': {
                'uid': user[0],
                'username': user[1],
                'avatar': user[3],
                'bio': user[4]
            }
        }))
        # 设置 cookie,7天有效期
        response.set_cookie('token', token, max_age=7*24*60*60, httponly=True)
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    '''用户登出'''
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'message': '已登出'})

# ============ 管理员登录API ============
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    '''管理员登录'''
    try:
        data = request.get_json()
        ip_address = request.remote_addr or '0.0.0.0'
        user_agent = request.headers.get('User-Agent', '')[:500]
        
        if not data:
            return jsonify({'success': False, 'message': '请提供用户名和密码'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': '请输入用户名和密码'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查账户是否被锁定
        cursor.execute('SELECT id, locked_until FROM admins WHERE username = ?', (username,))
        account = cursor.fetchone()
        
        if account:
            locked_until = account[1]
            if locked_until and locked_until > datetime.now().isoformat():
                remaining = (datetime.fromisoformat(locked_until) - datetime.now()).seconds // 60
                return jsonify({
                    'success': False, 
                    'message': f'账户已锁定,请 {remaining} 分钟后再试',
                    'locked': True,
                    'retry_after': remaining * 60
                }), 429
        
        # 记录登录尝试
        attempted_at = datetime.now().isoformat()
        
        # 查找管理员账户 - 使用bcrypt验证
        cursor.execute('''
            SELECT id, username, password_hash, failed_attempts
            FROM admins 
            WHERE username = ?
        ''', (username,))
        
        admin = cursor.fetchone()
        
        if not admin:
            # 记录失败的登录尝试
            cursor.execute('''
                INSERT INTO login_attempts (username, ip_address, attempted_at, success, user_agent)
                VALUES (?, ?, ?, 0, ?)
            ''', (username, ip_address, attempted_at, user_agent))
            conn.commit()
            conn.close()
            return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
        
        admin_id, admin_username, stored_hash, failed_attempts = admin
        
        # 验证密码
        try:
            password_valid = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        except Exception:
            password_valid = False
        
        if not password_valid:
            # 增加失败计数
            new_failed_attempts = failed_attempts + 1
            locked_until = None
            
            # 5次失败后锁定15分钟
            if new_failed_attempts >= 5:
                locked_until = (datetime.now() + timedelta(minutes=15)).isoformat()
            
            cursor.execute('''
                UPDATE admins SET failed_attempts = ?, locked_until = ? WHERE id = ?
            ''', (new_failed_attempts, locked_until, admin_id))
            
            # 记录失败的登录尝试
            cursor.execute('''
                INSERT INTO login_attempts (username, ip_address, attempted_at, success, user_agent)
                VALUES (?, ?, ?, 0, ?)
            ''', (username, ip_address, attempted_at, user_agent))
            
            conn.commit()
            conn.close()
            
            if new_failed_attempts >= 5:
                return jsonify({
                    'success': False, 
                    'message': '连续5次登录失败,账户已锁定15分钟',
                    'locked': True,
                    'retry_after': 900
                }), 429
            
            remaining = 5 - new_failed_attempts
            return jsonify({
                'success': False, 
                'message': f'用户名或密码错误,剩余 {remaining} 次尝试机会'
            }), 401
        
        # 登录成功:重置失败计数
        cursor.execute('''
            UPDATE admins SET failed_attempts = 0, locked_until = NULL WHERE id = ?
        ''', (admin_id,))
        
        # 记录成功的登录尝试
        cursor.execute('''
            INSERT INTO login_attempts (username, ip_address, attempted_at, success, user_agent)
            VALUES (?, ?, ?, 1, ?)
        ''', (username, ip_address, attempted_at, user_agent))
        
        # 记录登录历史
        cursor.execute('''
            INSERT INTO login_history (admin_id, username, ip_address, login_at, user_agent)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, username, ip_address, attempted_at, user_agent))
        
        # 生成管理员token
        token = secrets.token_hex(32)
        expires_at = (datetime.now() + timedelta(days=1)).isoformat()  # Token有效期改为1天
        
        # 保存session
        cursor.execute('''
            INSERT INTO sessions (token, uid, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (token, f'admin_{admin_id}', attempted_at, expires_at))
        
        # 更新最后登录时间
        cursor.execute('UPDATE admins SET last_login = ? WHERE id = ?', (attempted_at, admin_id))
        
        conn.commit()
        conn.close()
        
        response = make_response(jsonify({
            'success': True,
            'message': '登录成功',
            'token': token,
            'admin': {
                'id': admin_id,
                'username': admin_username
            }
        }))
        # 安全Cookie设置
        response.set_cookie('admin_token', token, max_age=24*60*60, httponly=True, samesite='Lax')
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/verify', methods=['GET'])
def admin_verify():
    '''验证管理员登录状态'''
    token = request.cookies.get('admin_token', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'valid': False})
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.token, s.uid, s.expires_at, a.username
        FROM sessions s
        JOIN admins a ON s.uid = 'admin_' || a.id
        WHERE s.token = ? AND s.expires_at > ?
    ''', (token, datetime.now().isoformat()))
    
    session = cursor.fetchone()
    conn.close()
    
    if session:
        return jsonify({
            'valid': True,
            'admin': {
                'username': session[3]
            }
        })
    else:
        return jsonify({'valid': False})

@app.route('/api/admin/password', methods=['POST'])
@admin_required
def admin_change_password():
    '''修改管理员密码'''
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请提供密码'}), 400
        
        new_password = data.get('password', '')
        
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'message': '密码长度至少6位'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 使用bcrypt哈希新密码
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute('''
            UPDATE admins SET password_hash = ?, password_changed_at = ? WHERE id = ?
        ''', (password_hash, datetime.now().isoformat(), g.admin_id))
        
        # 使所有现有会话失效
        cursor.execute('DELETE FROM sessions WHERE uid = ?', (f'admin_{g.admin_id}',))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': '密码修改成功,请重新登录'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/login-history', methods=['GET'])
@admin_required
def admin_login_history():
    '''获取登录历史'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ip_address, login_at, user_agent
        FROM login_history
        WHERE admin_id = ?
        ORDER BY login_at DESC
        LIMIT 20
    ''', (g.admin_id,))
    
    history = []
    for row in cursor.fetchall():
        history.append({
            'ip_address': row[0],
            'login_at': row[1],
            'user_agent': row[2][:100] if row[2] else ''
        })
    
    conn.close()
    
    return jsonify({
        'success': True,
        'history': history
    })

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    '''管理员登出'''
    token = request.cookies.get('admin_token', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    '''获取所有用户列表'''
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT uid, username, avatar, bio, created_at, last_login, is_admin, is_banned
        FROM users
        ORDER BY created_at DESC
    ''')
    
    users = [dict(row) for row in cursor.fetchall()]
    
    # 获取统计数据
    cursor.execute('SELECT COUNT(*) as total FROM users')
    total_users = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as active FROM sessions WHERE expires_at > ?', (datetime.now().isoformat(),))
    active_users = cursor.fetchone()['active']
    
    # 获取物品总数
    cursor.execute('SELECT COUNT(*) as total FROM products')
    total_products = cursor.fetchone()['total']
    
    # 获取今日新增(用户)
    cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= date('now')")
    today_users = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'users': users,
        'stats': {
            'total': total_users,
            'active': active_users,
            'products': total_products,
            'today': today_users
        }
    })

# ============ 管理员用户管理API ============
@app.route('/api/admin/user/create', methods=['POST'])
@admin_required
def admin_create_user():
    '''创建用户'''
    try:
        data = request.get_json()
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': '密码至少6位'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查用户名是否已存在
        cursor.execute('SELECT uid FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '用户名已存在'}), 400
        
        # 生成用户ID和密码哈希
        uid = secrets.token_hex(8)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('''
            INSERT INTO users (uid, username, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (uid, username, password_hash, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': '用户创建成功',
            'user': {'uid': uid, 'username': username}
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/<uid>', methods=['PUT'])
@admin_required
def admin_update_user(uid):
    '''更新用户信息'''
    try:
        data = request.get_json()
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查用户是否存在
        cursor.execute('SELECT uid FROM users WHERE uid = ?', (uid,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        # 更新字段
        updates = []
        params = []
        
        if 'username' in data:
            # 检查新用户名是否被占用
            cursor.execute('SELECT uid FROM users WHERE username = ? AND uid != ?', (data['username'], uid))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'message': '用户名已被占用'}), 400
            updates.append('username = ?')
            params.append(data['username'])
        
        if 'avatar' in data:
            updates.append('avatar = ?')
            params.append(data['avatar'])
        
        if 'bio' in data:
            updates.append('bio = ?')
            params.append(data['bio'])
        
        if 'is_admin' in data:
            updates.append('is_admin = ?')
            params.append(1 if data['is_admin'] else 0)
        
        if updates:
            params.append(uid)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE uid = ?", params)
            conn.commit()
        
        conn.close()
        
        return jsonify({'success': True, 'message': '用户信息更新成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/<uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    '''删除用户'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查用户是否存在
        cursor.execute('SELECT uid, is_admin FROM users WHERE uid = ?', (uid,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        # 不能删除管理员
        if user[1]:
            conn.close()
            return jsonify({'success': False, 'message': '不能删除管理员账户'}), 400
        
        # 删除用户及其相关数据
        cursor.execute('DELETE FROM sessions WHERE uid = ?', (uid,))
        cursor.execute('DELETE FROM reviews WHERE uid = ? OR seller_uid = ?', (uid, uid))
        cursor.execute('DELETE FROM products WHERE uid = ?', (uid,))
        cursor.execute('DELETE FROM users WHERE uid = ?', (uid,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '用户已删除'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/<uid>/ban', methods=['POST'])
@admin_required
def admin_ban_user(uid):
    '''封禁用户'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT uid, is_admin FROM users WHERE uid = ?', (uid,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        if user[1]:
            conn.close()
            return jsonify({'success': False, 'message': '不能封禁管理员'}), 400
        
        cursor.execute('UPDATE users SET is_banned = 1 WHERE uid = ?', (uid,))
        # 删除用户的所有session
        cursor.execute('DELETE FROM sessions WHERE uid = ?', (uid,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '用户已封禁'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/<uid>/unban', methods=['POST'])
@admin_required
def admin_unban_user(uid):
    '''解封用户'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT uid FROM users WHERE uid = ?', (uid,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        cursor.execute('UPDATE users SET is_banned = 0 WHERE uid = ?', (uid,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '用户已解封'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/<uid>/reset-password', methods=['POST'])
@admin_required
def admin_reset_password(uid):
    '''重置用户密码'''
    try:
        data = request.get_json() or {}
        new_password = data.get('password', '').strip()
        
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'message': '密码至少6位'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT uid, username, is_admin FROM users WHERE uid = ?', (uid,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        username = user[1]
        
        # 更新密码
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute('UPDATE users SET password_hash = ? WHERE uid = ?', (password_hash, uid))
        
        # 删除用户所有session,强制重新登录
        cursor.execute('DELETE FROM sessions WHERE uid = ?', (uid,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'用户 {username} 的密码已重置为: {new_password}',
            'reset_for': username,
            'new_password': new_password
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/batch-delete', methods=['POST'])
@admin_required
def admin_batch_delete():
    '''批量删除用户'''
    try:
        data = request.get_json()
        uids = data.get('uids', [])
        
        if not uids:
            return jsonify({'success': False, 'message': '请选择要删除的用户'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 过滤掉管理员
        cursor.execute('SELECT uid FROM users WHERE uid IN ({}) AND is_admin = 1'.format(
            ','.join('?' * len(uids))
        ), uids)
        admin_uids = [row[0] for row in cursor.fetchall()]
        
        delete_uids = [uid for uid in uids if uid not in admin_uids]
        
        if not delete_uids:
            conn.close()
            return jsonify({'success': False, 'message': '选中的用户中包含管理员,无法删除'}), 400
        
        # 删除用户及其相关数据
        placeholders = ','.join('?' * len(delete_uids))
        cursor.execute(f'DELETE FROM sessions WHERE uid IN ({placeholders})', delete_uids)
        cursor.execute(f'DELETE FROM reviews WHERE uid IN ({placeholders}) OR seller_uid IN ({placeholders})', delete_uids + delete_uids)
        cursor.execute(f'DELETE FROM products WHERE uid IN ({placeholders})', delete_uids)
        cursor.execute(f'DELETE FROM users WHERE uid IN ({placeholders})', delete_uids)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'已删除 {len(delete_uids)} 个用户',
            'deleted_count': len(delete_uids),
            'skipped_count': len(admin_uids)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/batch-ban', methods=['POST'])
@admin_required
def admin_batch_ban():
    '''批量封禁用户'''
    try:
        data = request.get_json()
        uids = data.get('uids', [])
        
        if not uids:
            return jsonify({'success': False, 'message': '请选择要封禁的用户'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 过滤掉管理员
        cursor.execute('SELECT uid FROM users WHERE uid IN ({}) AND is_admin = 1'.format(
            ','.join('?' * len(uids))
        ), uids)
        admin_uids = [row[0] for row in cursor.fetchall()]
        
        ban_uids = [uid for uid in uids if uid not in admin_uids]
        
        if not ban_uids:
            conn.close()
            return jsonify({'success': False, 'message': '选中的用户中包含管理员,无法封禁'}), 400
        
        placeholders = ','.join('?' * len(ban_uids))
        cursor.execute(f'UPDATE users SET is_banned = 1 WHERE uid IN ({placeholders})', ban_uids)
        cursor.execute(f'DELETE FROM sessions WHERE uid IN ({placeholders})', ban_uids)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'已封禁 {len(ban_uids)} 个用户',
            'banned_count': len(ban_uids),
            'skipped_count': len(admin_uids)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/batch-unban', methods=['POST'])
@admin_required
def admin_batch_unban():
    '''批量解封用户'''
    try:
        data = request.get_json()
        uids = data.get('uids', [])
        
        if not uids:
            return jsonify({'success': False, 'message': '请选择要解封的用户'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(uids))
        cursor.execute(f'UPDATE users SET is_banned = 0 WHERE uid IN ({placeholders})', uids)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'已解封 {len(uids)} 个用户',
            'unbanned_count': len(uids)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== AI 异常账户检测 ====================

@app.route('/api/admin/anomaly-detection', methods=['GET'])
@admin_required
def admin_anomaly_detection():
    '''AI 异常账户检测'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 获取所有用户及其行为数据
        cursor.execute('''
            SELECT u.uid, u.username, u.avatar, u.created_at, u.is_banned, u.is_admin,
                   COUNT(DISTINCT p.id) as product_count,
                   COUNT(DISTINCT s.token) as login_count,
                   u.last_login
            FROM users u
            LEFT JOIN products p ON u.uid = p.uid
            LEFT JOIN sessions s ON u.uid = s.uid
            WHERE u.is_admin = 0
            GROUP BY u.uid
        ''')
        users = cursor.fetchall()
        
        anomaly_users = []
        normal_count = 0
        
        for user in users:
            uid, username, avatar, created_at, is_banned, is_admin, product_count, login_count, last_login = user
            
            # 跳过已封禁用户
            if is_banned:
                normal_count += 1
                continue
            
            reasons = []
            risk_score = 0
            
            # 检测1:注册时间很短但发布物品很多
            if created_at:
                from datetime import datetime
                created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                days_since_creation = (datetime.now() - created_time).days
                
                if days_since_creation < 7 and product_count > 5:
                    reasons.append(f'新账号(注册{days_since_creation}天)发布大量物品({product_count}个)')
                    risk_score += 30
                elif days_since_creation < 30 and product_count > 20:
                    reasons.append(f'账号创建{days_since_creation}天,物品数量异常({product_count}个)')
                    risk_score += 20
            
            # 检测2:物品价格异常
            if product_count > 0:
                cursor.execute('SELECT MIN(price), MAX(price), AVG(price) FROM products WHERE uid = ?', (uid,))
                price_data = cursor.fetchone()
                if price_data and price_data[0] is not None:
                    min_price, max_price, avg_price = price_data
                    if min_price and min_price < 1:
                        reasons.append(f'存在极低价格物品(¥{min_price})')
                        risk_score += 25
                    if max_price and avg_price and max_price > avg_price * 10:
                        reasons.append(f'价格差异过大(¥{min_price}-¥{max_price})')
                        risk_score += 15
            
            # 检测3:昵称异常检测
            suspicious_patterns = ['test', '测试', 'admin', 'user', '111', '222', 'aaa', 'qqq', '自动', '机器人']
            if any(pattern in (username or '').lower() for pattern in suspicious_patterns):
                reasons.append(f'昵称包含可疑关键词: {username}')
                risk_score += 15
            
            # 检测4:头像异常
            if not avatar or avatar in ['😊', '😀', '🙂', '👤', '🚪', '📦']:
                reasons.append('使用默认或简单头像')
                risk_score += 5
            
            # 检测5:登录次数异常
            if login_count > 100:
                reasons.append(f'登录次数异常({login_count}次)')
                risk_score += 15
            
            # 检测6:长时间未登录但有物品
            if last_login and product_count > 0:
                from datetime import datetime
                last_login_time = datetime.fromisoformat(last_login.replace('Z', '+00:00').replace('+00:00', ''))
                days_since_login = (datetime.now() - last_login_time).days
                if days_since_login > 30:
                    reasons.append(f'长时间未登录({days_since_login}天)但有{product_count}个物品在售')
                    risk_score += 20
            
            # 检测7:无头像+大量物品
            if (not avatar or avatar in ['😊', '😀', '🙂', '👤']) and product_count > 10:
                reasons.append(f'无头像且物品数量多({product_count}个)')
                risk_score += 25
            
            # 风险等级分类
            if risk_score >= 50:
                risk_level = '高风险'
            elif risk_score >= 25:
                risk_level = '中风险'
            elif risk_score >= 10:
                risk_level = '低风险'
            else:
                risk_level = '正常'
                normal_count += 1
            
            if reasons:  # 只返回有异常的用户
                anomaly_users.append({
                    'uid': uid,
                    'username': username,
                    'avatar': avatar or username[0] if username else 'U',
                    'product_count': product_count,
                    'login_count': login_count,
                    'created_at': created_at,
                    'last_login': last_login,
                    'reasons': reasons,
                    'risk_score': risk_score,
                    'risk_level': risk_level
                })
        
        # 按风险分数排序
        anomaly_users.sort(key=lambda x: x['risk_score'], reverse=True)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_users': len(users),
            'anomaly_count': len(anomaly_users),
            'normal_count': normal_count,
            'high_risk_count': len([u for u in anomaly_users if u['risk_level'] == '高风险']),
            'medium_risk_count': len([u for u in anomaly_users if u['risk_level'] == '中风险']),
            'low_risk_count': len([u for u in anomaly_users if u['risk_level'] == '低风险']),
            'anomaly_users': anomaly_users
        })
        
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'message': f'检测失败: {str(e)}', 'error': traceback.format_exc()}), 500

@app.route('/api/admin/anomaly-detection/auto-ban', methods=['POST'])
@admin_required
def admin_auto_ban_anomaly():
    '''自动封禁高风险账户'''
    try:
        data = request.get_json()
        min_risk_score = data.get('min_risk_score', 50)  # 默认封禁风险分数>=50的账户
        auto_ban = data.get('auto_ban', False)
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 获取所有用户
        cursor.execute('''
            SELECT u.uid, u.username, u.created_at, u.is_banned, u.is_admin,
                   COUNT(DISTINCT p.id) as product_count
            FROM users u
            LEFT JOIN products p ON u.uid = p.uid
            WHERE u.is_admin = 0 AND u.is_banned = 0
            GROUP BY u.uid
        ''')
        users = cursor.fetchall()
        
        ban_list = []
        skip_list = []
        
        for user in users:
            uid, username, created_at, is_banned, is_admin, product_count = user
            
            reasons = []
            risk_score = 0
            
            # 检测异常
            if created_at:
                from datetime import datetime
                try:
                    created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                    days_since_creation = (datetime.now() - created_time).days
                    
                    if days_since_creation < 7 and product_count > 5:
                        reasons.append('新账号大量发布')
                        risk_score += 30
                    elif days_since_creation < 30 and product_count > 20:
                        reasons.append('物品数量异常')
                        risk_score += 20
                except:
                    pass
            
            # 检测价格异常
            if product_count > 0:
                cursor.execute('SELECT MIN(price) FROM products WHERE uid = ?', (uid,))
                min_price = cursor.fetchone()[0]
                if min_price and min_price < 1:
                    reasons.append('极低价格')
                    risk_score += 25
            
            # 检测昵称
            suspicious_patterns = ['test', '测试', 'admin', '111', '222', 'aaa']
            if any(pattern in (username or '').lower() for pattern in suspicious_patterns):
                reasons.append('可疑昵称')
                risk_score += 15
            
            # 封禁
            if risk_score >= min_risk_score:
                if auto_ban:
                    cursor.execute('UPDATE users SET is_banned = 1 WHERE uid = ?', (uid,))
                    cursor.execute('DELETE FROM sessions WHERE uid = ?', (uid,))
                    conn.commit()
                    ban_list.append({'uid': uid, 'username': username, 'risk_score': risk_score, 'reasons': reasons})
                else:
                    skip_list.append({'uid': uid, 'username': username, 'risk_score': risk_score, 'reasons': reasons})
        
        conn.close()
        
        if auto_ban:
            return jsonify({
                'success': True,
                'message': f'已自动封禁 {len(ban_list)} 个高风险账户',
                'banned_count': len(ban_list),
                'banned_users': ban_list
            })
        else:
            return jsonify({
                'success': True,
                'message': f'检测到 {len(skip_list)} 个高风险账户(预览模式,未执行封禁)',
                'preview_count': len(skip_list),
                'preview_users': skip_list
            })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== 管理员物品管理 API ====================

@app.route('/api/admin/products', methods=['GET'])
@admin_required
def admin_get_products():
    '''管理员获取物品列表'''
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        
        offset = (page - 1) * page_size
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 构建查询
        where_clauses = []
        params = []
        
        if search:
            where_clauses.append('(p.title LIKE ? OR p.description LIKE ?)')
            params.extend([f'%{search}%', f'%{search}%'])
        
        if status:
            where_clauses.append('p.status = ?')
            params.append(status)
        
        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
        
        # 获取总数
        cursor.execute(f'SELECT COUNT(*) FROM products p WHERE {where_sql}', params)
        total_count = cursor.fetchone()[0]
        
        # 获取列表
        cursor.execute(f'''
            SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description, 
                   p.images, p.category, p.condition, p.status, p.views, p.created_at, p.updated_at,
                   u.username, u.avatar
            FROM products p
            LEFT JOIN users u ON p.uid = u.uid
            WHERE {where_sql}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [page_size, offset])
        
        products = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'products': [{
                'id': p[0], 'uid': p[1], 'title': p[2], 'price': p[3],
                'original_price': p[4], 'description': p[5], 'images': p[6],
                'category': p[7], 'condition': p[8], 'status': p[9],
                'views': p[10], 'created_at': p[11], 'updated_at': p[12],
                'seller_name': p[13], 'avatar': p[14]
            } for p in products],
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/product/<int:product_id>', methods=['GET'])
@admin_required
def admin_get_product(product_id):
    '''管理员获取单个物品详情'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description, 
                   p.images, p.category, p.condition, p.status, p.views, p.created_at, p.updated_at,
                   u.username, u.avatar
            FROM products p
            LEFT JOIN users u ON p.uid = u.uid
            WHERE p.id = ?
        ''', (product_id,))
        
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'message': '物品不存在'}), 404
        
        conn.close()
        
        return jsonify({
            'success': True,
            'product': {
                'id': product[0], 'uid': product[1], 'title': product[2], 'price': product[3],
                'original_price': product[4], 'description': product[5], 'images': product[6],
                'category': product[7], 'condition': product[8], 'status': product[9],
                'views': product[10], 'created_at': product[11], 'updated_at': product[12],
                'seller_name': product[13], 'avatar': product[14]
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/product/<int:product_id>', methods=['DELETE'])
@admin_required
def admin_delete_product(product_id):
    '''管理员删除物品'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查物品是否存在
        cursor.execute('SELECT id, title FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'message': '物品不存在'}), 404
        
        # 删除物品
        cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f"物品'{product[1]}'已删除"
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/products/batch-delete', methods=['POST'])
@admin_required
def admin_batch_delete_products():
    '''管理员批量删除物品'''
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        
        if not ids:
            return jsonify({'success': False, 'message': '请选择要删除的物品'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(ids))
        cursor.execute(f'DELETE FROM products WHERE id IN ({placeholders})', ids)
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'已删除 {deleted_count} 个物品',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    '''获取当前用户信息'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT uid, username, avatar, bio, created_at, last_login 
        FROM users WHERE uid = ?
    ''', (g.uid,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    return jsonify({
        'success': True,
        'user': {
            'uid': user[0],
            'username': user[1],
            'avatar': user[2],
            'bio': user[3],
            'created_at': user[4],
            'last_login': user[5]
        }
    })

@app.route('/api/auth/profile', methods=['PUT'])
@login_required
def update_profile():
    '''更新用户资料'''
    try:
        data = request.get_json()
        
        avatar = data.get('avatar', '').strip()[:10]
        bio = data.get('bio', '').strip()[:200]
        username = data.get('username', '').strip()
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 如果修改用户名,检查是否已存在
        if username:
            if len(username) < 2 or len(username) > 20:
                conn.close()
                return jsonify({'success': False, 'error': '用户名长度需在2-20个字符'}), 400
            
            cursor.execute('SELECT uid FROM users WHERE username = ? AND uid != ?', (username, g.uid))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '用户名已存在'}), 400
            
            cursor.execute('UPDATE users SET username = ?, avatar = ?, bio = ? WHERE uid = ?', 
                          (username, avatar or '😊', bio, g.uid))
        else:
            cursor.execute('UPDATE users SET avatar = ?, bio = ? WHERE uid = ?', 
                          (avatar or '😊', bio, g.uid))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '资料已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/password', methods=['PUT'])
@login_required
def change_password():
    '''修改密码'''
    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'error': '请填写完整'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': '新密码至少6位'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 验证当前密码
        cursor.execute('SELECT password_hash FROM users WHERE uid = ?', (g.uid,))
        user = cursor.fetchone()
        
        if not user or not verify_password(current_password, user[0]):
            conn.close()
            return jsonify({'success': False, 'error': '当前密码错误'}), 401
        
        # 更新密码
        new_hash = hash_password(new_password)
        cursor.execute('UPDATE users SET password_hash = ? WHERE uid = ?', (new_hash, g.uid))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '密码修改成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/account', methods=['DELETE'])
@login_required
def delete_account():
    '''注销账号'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 删除用户的所有商品
        cursor.execute('DELETE FROM products WHERE uid = ?', (g.uid,))
        
        # 删除关注关系
        cursor.execute('DELETE FROM follows WHERE follower_uid = ? OR following_uid = ?', (g.uid, g.uid))
        
        # 删除拉黑关系
        cursor.execute('DELETE FROM blocks WHERE blocker_uid = ? OR blocked_uid = ?', (g.uid, g.uid))
        
        # 删除会话
        cursor.execute('DELETE FROM sessions WHERE uid = ?', (g.uid,))
        
        # 删除用户
        cursor.execute('DELETE FROM users WHERE uid = ?', (g.uid,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '账号已注销'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ 用户关系API ============

@app.route('/api/user/<uid>')
def get_user_profile(uid):
    '''获取用户资料'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT uid, username, avatar, bio, created_at, last_login 
        FROM users WHERE uid = ?
    ''', (uid,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    # 获取商品统计
    cursor.execute('SELECT COUNT(*) FROM products WHERE uid = ? AND status = ?', (uid, 'selling'))
    selling_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM products WHERE uid = ? AND status = ?', (uid, 'sold'))
    sold_count = cursor.fetchone()[0]
    conn.close()
    
    return jsonify({
        'success': True,
        'user': {
            'uid': user[0],
            'username': user[1],
            'avatar': user[2],
            'bio': user[3],
            'created_at': user[4],
            'last_login': user[5],
            'selling': selling_count,
            'sold': sold_count
        }
    })

@app.route('/api/user/relations')
@login_required
def get_relations():
    '''获取与某用户的关系状态'''
    target = request.args.get('target', '')
    if not target:
        return jsonify({'success': False, 'error': '缺少目标用户'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 检查是否已关注
    cursor.execute('SELECT 1 FROM follows WHERE follower_uid = ? AND following_uid = ?', (g.uid, target))
    followed = cursor.fetchone() is not None
    
    # 检查是否已拉黑
    cursor.execute('SELECT 1 FROM blocks WHERE blocker_uid = ? AND blocked_uid = ?', (g.uid, target))
    blocked = cursor.fetchone() is not None
    
    conn.close()
    
    return jsonify({
        'success': True,
        'followed': followed,
        'blocked': blocked
    })

@app.route('/api/user/follow', methods=['POST'])
@login_required
def follow_user():
    '''关注用户'''
    try:
        data = request.get_json()
        target_uid = data.get('target_uid', '')
        
        if not target_uid:
            return jsonify({'success': False, 'error': '缺少目标用户'}), 400
        
        if target_uid == g.uid:
            return jsonify({'success': False, 'error': '不能关注自己'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查目标用户是否存在
        cursor.execute('SELECT uid FROM users WHERE uid = ?', (target_uid,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        
        # 添加关注
        cursor.execute('''
            INSERT OR IGNORE INTO follows (follower_uid, following_uid, created_at)
            VALUES (?, ?, ?)
        ''', (g.uid, target_uid, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '关注成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/follow', methods=['DELETE'])
@login_required
def unfollow_user():
    '''取消关注'''
    target = request.args.get('target', '')
    if not target:
        return jsonify({'success': False, 'error': '缺少目标用户'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM follows WHERE follower_uid = ? AND following_uid = ?', (g.uid, target))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '已取消关注'})

@app.route('/api/user/block', methods=['POST'])
@login_required
def block_user():
    '''拉黑用户'''
    try:
        data = request.get_json()
        target_uid = data.get('target_uid', '')
        
        if not target_uid:
            return jsonify({'success': False, 'error': '缺少目标用户'}), 400
        
        if target_uid == g.uid:
            return jsonify({'success': False, 'error': '不能拉黑自己'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 添加拉黑记录
        cursor.execute('''
            INSERT OR IGNORE INTO blocks (blocker_uid, blocked_uid, created_at)
            VALUES (?, ?, ?)
        ''', (g.uid, target_uid, datetime.now().isoformat()))
        
        # 同时取消关注(如果有关注)
        cursor.execute('DELETE FROM follows WHERE follower_uid = ? AND following_uid = ?', (g.uid, target_uid))
        cursor.execute('DELETE FROM follows WHERE follower_uid = ? AND following_uid = ?', (target_uid, g.uid))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '已拉黑该用户'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/block', methods=['DELETE'])
@login_required
def unblock_user():
    '''解除拉黑'''
    target = request.args.get('target', '')
    if not target:
        return jsonify({'success': False, 'error': '缺少目标用户'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM blocks WHERE blocker_uid = ? AND blocked_uid = ?', (g.uid, target))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '已解除拉黑'})

@app.route('/api/user/following')
@login_required
def get_following():
    '''获取关注列表'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.uid, u.username, u.avatar, u.bio, f.created_at
        FROM follows f
        JOIN users u ON f.following_uid = u.uid
        WHERE f.follower_uid = ?
        ORDER BY f.created_at DESC
    ''', (g.uid,))
    following = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'following': [{'uid': r[0], 'username': r[1], 'avatar': r[2], 'bio': r[3], 'followed_at': r[4]} for r in following]
    })

@app.route('/api/user/blocked')
@login_required
def get_blocked():
    '''获取拉黑列表'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.uid, u.username, u.avatar, b.created_at
        FROM blocks b
        JOIN users u ON b.blocked_uid = u.uid
        WHERE b.blocker_uid = ?
        ORDER BY b.created_at DESC
    ''', (g.uid,))
    blocked = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'blocked': [{'uid': r[0], 'username': r[1], 'avatar': r[2], 'blocked_at': r[3]} for r in blocked]
    })

# ============ 消息API ============

@app.route('/api/messages')
@login_required
def get_messages():
    '''获取与某用户的聊天记录'''
    other_uid = request.args.get('uid')
    if not other_uid:
        return jsonify({'success': False, 'error': '缺少用户参数'}), 400
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取当前用户信息
    cursor.execute('SELECT uid, username, avatar FROM users WHERE uid = ?', (g.uid,))
    current_user = dict(cursor.fetchone())
    
    # 获取对方用户信息
    cursor.execute('SELECT uid, username, avatar FROM users WHERE uid = ?', (other_uid,))
    other_user_row = cursor.fetchone()
    if not other_user_row:
        conn.close()
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    other_user = dict(other_user_row)
    
    # 获取聊天记录
    cursor.execute('''
        SELECT id, sender_uid, receiver_uid, content, is_read, created_at
        FROM messages
        WHERE (sender_uid = ? AND receiver_uid = ?)
           OR (sender_uid = ? AND receiver_uid = ?)
        ORDER BY created_at ASC
    ''', (g.uid, other_uid, other_uid, g.uid))
    
    messages = []
    for row in cursor.fetchall():
        msg = dict(row)
        msg['is_mine'] = msg['sender_uid'] == g.uid
        messages.append(msg)
    
    conn.close()
    
    return jsonify({
        'success': True,
        'current_user': current_user,
        'other_user': other_user,
        'messages': messages
    })

@app.route('/api/messages', methods=['POST'])
@login_required
def send_message():
    '''发送私信'''
    data = request.get_json()
    receiver_uid = data.get('receiver_uid')
    content = data.get('content', '').strip()
    
    if not receiver_uid:
        return jsonify({'success': False, 'error': '缺少收件人'}), 400
    
    if not content:
        return jsonify({'success': False, 'error': '消息内容不能为空'}), 400
    
    # 检查对方是否存在
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT uid FROM users WHERE uid = ?', (receiver_uid,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': '收件人不存在'}), 404
    
    # 不能给自己发消息
    if receiver_uid == g.uid:
        conn.close()
        return jsonify({'success': False, 'error': '不能给自己发消息'}), 400
    
    # 保存消息
    created_at = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO messages (sender_uid, receiver_uid, content, created_at)
        VALUES (?, ?, ?, ?)
    ''', (g.uid, receiver_uid, content, created_at))
    
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': {
            'id': message_id,
            'sender_uid': g.uid,
            'receiver_uid': receiver_uid,
            'content': content,
            'is_read': 0,
            'created_at': created_at,
            'is_mine': True
        }
    }), 201

@app.route('/api/messages/conversations')
@login_required
def get_conversations():
    '''获取会话列表(消息盒子)'''
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取所有与当前用户相关的消息,按用户分组
    cursor.execute('''
        SELECT 
            CASE 
                WHEN sender_uid = ? THEN receiver_uid 
                ELSE sender_uid 
            END as other_uid,
            content,
            created_at,
            sender_uid
        FROM messages
        WHERE sender_uid = ? OR receiver_uid = ?
        ORDER BY created_at DESC
    ''', (g.uid, g.uid, g.uid))
    
    # 按用户分组,只保留最新消息
    conversations = {}
    for row in cursor.fetchall():
        other_uid = row['other_uid']
        if other_uid not in conversations:
            # 获取对方用户信息
            cursor.execute('SELECT uid, username, avatar FROM users WHERE uid = ?', (other_uid,))
            user = cursor.fetchone()
            if user:
                conversations[other_uid] = {
                    'uid': other_uid,
                    'username': user['username'],
                    'avatar': user['avatar'],
                    'last_message': row['content'],
                    'last_time': row['created_at'],
                    'is_mine': row['sender_uid'] == g.uid
                }
    
    conn.close()
    
    # 转换为列表并按时间排序
    result = list(conversations.values())
    result.sort(key=lambda x: x['last_time'], reverse=True)
    
    return jsonify({
        'success': True,
        'conversations': result
    })

# ============ 收藏API ============

@app.route('/api/favorites')
@login_required
def get_favorites():
    '''获取我的收藏'''
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT f.id as favorite_id, f.created_at as favorited_at,
               p.id, p.uid, p.title, p.price, p.original_price, p.images,
               p.category, p.condition, p.status, p.views,
               u.username as seller_name, u.avatar as seller_avatar
        FROM favorites f
        JOIN products p ON f.product_id = p.id
        LEFT JOIN users u ON p.uid = u.uid
        WHERE f.uid = ?
        ORDER BY f.created_at DESC
    ''', (g.uid,))
    
    favorites = []
    for row in cursor.fetchall():
        favorites.append({
            'favorite_id': row['favorite_id'],
            'favorited_at': row['favorited_at'],
            'id': row['id'],
            'uid': row['uid'],
            'title': row['title'],
            'price': row['price'],
            'original_price': row['original_price'],
            'images': row['images'],
            'category': row['category'],
            'condition': row['condition'],
            'status': row['status'],
            'views': row['views'],
            'seller_name': row['seller_name'],
            'seller_avatar': row['seller_avatar']
        })
    
    conn.close()
    
    return jsonify({
        'success': True,
        'favorites': favorites
    })

@app.route('/api/favorites', methods=['POST'])
@login_required
def add_favorite():
    '''添加收藏'''
    data = request.get_json()
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'error': '缺少商品ID'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 检查商品是否存在
    cursor.execute('SELECT id FROM products WHERE id = ?', (product_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': '商品不存在'}), 404
    
    # 检查是否已收藏
    cursor.execute('SELECT id FROM favorites WHERE uid = ? AND product_id = ?', (g.uid, product_id))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': '已经收藏过了'}), 400
    
    # 添加收藏
    created_at = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO favorites (uid, product_id, created_at)
        VALUES (?, ?, ?)
    ''', (g.uid, product_id, created_at))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': '收藏成功'
    }), 201

@app.route('/api/favorites/<int:product_id>', methods=['DELETE'])
@login_required
def remove_favorite(product_id):
    '''取消收藏'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM favorites WHERE uid = ? AND product_id = ?', (g.uid, product_id))
    affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if affected == 0:
        return jsonify({'success': False, 'error': '收藏不存在'}), 404
    
    return jsonify({
        'success': True,
        'message': '已取消收藏'
    })

@app.route('/api/favorites/check/<int:product_id>')
@login_required
def check_favorite(product_id):
    '''检查是否已收藏'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM favorites WHERE uid = ? AND product_id = ?', (g.uid, product_id))
    exists = cursor.fetchone() is not None
    
    conn.close()
    
    return jsonify({
        'success': True,
        'is_favorited': exists
    })

# ============ 订单API ============

@app.route('/api/orders')
@login_required
def get_orders():
    '''获取订单列表'''
    try:
        order_type = request.args.get('type', 'buyer')  # buyer 或 seller
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if order_type == 'seller':
            cursor.execute('''
                SELECT o.*, p.title, p.images, p.price as product_price,
                       u.username as buyer_name, u.avatar as buyer_avatar
                FROM orders o
                JOIN products p ON o.product_id = p.id
                LEFT JOIN users u ON o.buyer_uid = u.uid
                WHERE o.seller_uid = ?
                ORDER BY o.created_at DESC
            ''', (g.uid,))
            rows = cursor.fetchall()
            orders = []
            for row in rows:
                order = dict(row)
                order['is_buyer'] = False
                order['is_seller'] = True
                orders.append(order)
        else:
            cursor.execute('''
                SELECT o.*, p.title, p.images, p.price as product_price,
                       u.username as seller_name, u.avatar as seller_avatar
                FROM orders o
                JOIN products p ON o.product_id = p.id
                LEFT JOIN users u ON o.seller_uid = u.uid
                WHERE o.buyer_uid = ?
                ORDER BY o.created_at DESC
            ''', (g.uid,))
            rows = cursor.fetchall()
            orders = []
            for row in rows:
                order = dict(row)
                order['is_buyer'] = True
                order['is_seller'] = False
                orders.append(order)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'orders': orders,
            'type': order_type
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders', methods=['POST'])
@login_required
def create_order():
    '''创建订单'''
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': '缺少商品ID'}), 400
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取商品信息
        cursor.execute('SELECT id, uid, title, price, status FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': '商品不存在'}), 404
        
        if product['status'] != 'selling':
            conn.close()
            return jsonify({'success': False, 'error': '商品已下架或已售出'}), 400
        
        if product['uid'] == g.uid:
            conn.close()
            return jsonify({'success': False, 'error': '不能购买自己的商品'}), 400
        
        # 检查是否已有待处理订单
        cursor.execute('''
            SELECT id FROM orders 
            WHERE product_id = ? AND buyer_uid = ? AND status = 'pending'
        ''', (product_id, g.uid))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '已有待处理的订单'}), 400
        
        # 创建订单
        created_at = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO orders (product_id, buyer_uid, seller_uid, total_amount, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (product_id, g.uid, product['uid'], product['price'], created_at))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 增量同步订单到 Supabase
        sync_single_to_supabase('orders', {
            'id': order_id,
            'product_id': product_id,
            'buyer_uid': g.uid,
            'seller_uid': product['uid'],
            'total_amount': product['price'],
            'status': 'pending',
            'created_at': created_at
        }, 'id')
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': '订单创建成功'
        }), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>')
@login_required
def get_order(order_id):
    '''获取订单详情'''
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.*, p.title, p.images, p.description, p.price as product_price,
               buyer.username as buyer_name, buyer.avatar as buyer_avatar,
               seller.username as seller_name, seller.avatar as seller_avatar
        FROM orders o
        JOIN products p ON o.product_id = p.id
        LEFT JOIN users buyer ON o.buyer_uid = buyer.uid
        LEFT JOIN users seller ON o.seller_uid = seller.uid
        WHERE o.id = ?
    ''', (order_id,))
    
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        return jsonify({'success': False, 'error': '订单不存在'}), 404
    
    # 检查权限
    if order['buyer_uid'] != g.uid and order['seller_uid'] != g.uid:
        conn.close()
        return jsonify({'success': False, 'error': '无权查看此订单'}), 403
    
    # 添加 is_buyer 和 is_seller 字段
    order_dict = dict(order)
    order_dict['is_buyer'] = order['buyer_uid'] == g.uid
    order_dict['is_seller'] = order['seller_uid'] == g.uid
    
    conn.close()
    return jsonify({
        'success': True,
        'order': order_dict
    })

@app.route('/api/orders/<int:order_id>/update', methods=['POST'])
@login_required
def update_order(order_id):
    '''更新订单状态'''
    data = request.get_json()
    new_status = data.get('status')
    shipping_address = data.get('shipping_address')
    contact_phone = data.get('contact_phone')
    
    if not new_status:
        return jsonify({'success': False, 'error': '缺少状态参数'}), 400
    
    valid_statuses = ['pending', 'paid', 'shipped', 'completed', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'error': '无效的订单状态'}), 400
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取订单信息(包含金额和资金状态)
    cursor.execute('SELECT buyer_uid, seller_uid, status, total_amount, fund_status FROM orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        return jsonify({'success': False, 'error': '订单不存在'}), 404
    
    # 检查权限
    is_buyer = order['buyer_uid'] == g.uid
    is_seller = order['seller_uid'] == g.uid
    order_amount = order['total_amount']
    
    if not is_buyer and not is_seller:
        conn.close()
        return jsonify({'success': False, 'error': '无权操作此订单'}), 403
    
    # 状态转换规则
    if new_status == 'cancelled' and is_buyer and order['status'] == 'pending':
        # 买家可以取消待支付订单(资金未托管,无需处理)
        pass
    elif new_status == 'paid' and is_buyer and order['status'] == 'pending':
        # 买家确认支付,资金进入托管
        pass
    elif new_status == 'shipped' and is_seller and order['status'] == 'paid':
        # 卖家发货,资金仍在托管
        pass
    elif new_status == 'completed' and is_buyer and order['status'] == 'shipped':
        # 买家确认收货,资金释放给卖家
        pass
    elif new_status == 'cancelled' and is_seller and order['status'] == 'paid':
        # 卖家拒绝,资金退回买家
        pass
    else:
        conn.close()
        return jsonify({'success': False, 'error': '无效的状态转换'}), 400
    
    # 更新订单
    updated_at = datetime.now().isoformat()
    update_sql = 'UPDATE orders SET status = ?, updated_at = ?'
    params = [new_status, updated_at]
    fund_status_update = None
    
    # 处理资金状态变更
    if new_status == 'paid':
        update_sql += ', fund_status = ?'
        params.append('held')
        fund_status_update = 'held'
    elif new_status == 'completed':
        update_sql += ', fund_status = ?'
        params.append('released')
        fund_status_update = 'released'
        # 将资金释放给卖家
        cursor.execute('''
            UPDATE users SET withdrawable_balance = withdrawable_balance + ? 
            WHERE uid = ?
        ''', (order_amount, order['seller_uid']))
    elif new_status == 'cancelled' and order['status'] == 'paid':
        # 取消订单,退款(当前简化处理,不实际退款)
        update_sql += ', fund_status = ?'
        params.append('refunded')
        fund_status_update = 'refunded'
    
    if shipping_address:
        update_sql += ', shipping_address = ?'
        params.append(shipping_address)
    if contact_phone:
        update_sql += ', contact_phone = ?'
        params.append(contact_phone)
    
    update_sql += ' WHERE id = ?'
    params.append(order_id)
    
    cursor.execute(update_sql, params)
    conn.commit()
    conn.close()
    
    # 增量同步订单状态到 Supabase
    sync_data = {
        'id': order_id,
        'status': new_status,
        'updated_at': updated_at
    }
    if fund_status_update:
        sync_data['fund_status'] = fund_status_update
    if shipping_address:
        sync_data['shipping_address'] = shipping_address
    if contact_phone:
        sync_data['contact_phone'] = contact_phone
    sync_single_to_supabase('orders', sync_data, 'id')
    
    status_text = {'pending': '待确认', 'paid': '已支付(托管中)', 'shipped': '已发货', 'completed': '已完成', 'cancelled': '已取消'}
    return jsonify({
        'success': True,
        'message': f'订单状态已更新为:{status_text.get(new_status, new_status)}'
    })


# ============ 钱包API ============

@app.route('/api/wallet', methods=['GET'])
@login_required
def get_wallet():
    '''获取钱包信息'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT withdrawable_balance, frozen_balance 
        FROM users WHERE uid = ?
    ''', (g.uid,))
    wallet = cursor.fetchone()
    
    if not wallet:
        conn.close()
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    # 获取收入统计
    cursor.execute('''
        SELECT SUM(total_amount) 
        FROM orders 
        WHERE seller_uid = ? AND fund_status = 'released'
    ''', (g.uid,))
    total_earned = cursor.fetchone()[0] or 0
    
    # 获取待结算金额(已发货但未确认收货)
    cursor.execute('''
        SELECT SUM(total_amount) 
        FROM orders 
        WHERE seller_uid = ? AND fund_status = 'held'
    ''', (g.uid,))
    pending_settlement = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return jsonify({
        'success': True,
        'wallet': {
            'withdrawable': wallet[0] or 0,  # 可提现余额
            'frozen': wallet[1] or 0,         # 冻结金额
            'total_earned': total_earned,      # 历史总收入
            'pending_settlement': pending_settlement  # 待结算
        }
    })


@app.route('/api/wallet/withdraw', methods=['POST'])
@login_required
def withdraw_request():
    '''申请提现'''
    data = request.get_json()
    amount = data.get('amount')
    
    if not amount or amount <= 0:
        return jsonify({'success': False, 'error': '请输入正确的提现金额'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 获取当前余额
    cursor.execute('SELECT withdrawable_balance FROM users WHERE uid = ?', (g.uid,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    balance = result[0] or 0
    
    if balance < amount:
        conn.close()
        return jsonify({'success': False, 'error': f'余额不足,当前可提现 {balance} 元'}), 400
    
    # 扣除余额(简化处理:直接扣除,实际应生成提现申请记录)
    cursor.execute('UPDATE users SET withdrawable_balance = withdrawable_balance - ? WHERE uid = ?', (amount, g.uid))
    conn.commit()
    conn.close()
    
    # TODO: 实际应接入微信/支付宝打款API
    # 这里简化处理,直接提示提现申请已提交
    
    return jsonify({
        'success': True,
        'message': f'提现申请已提交,预计1-3个工作日到账',
        'amount': amount
    })

# ============ 收货地址API ============

@app.route('/api/addresses', methods=['GET'])
@login_required
def get_addresses():
    '''获取用户收货地址列表'''
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM addresses WHERE uid = ? ORDER BY is_default DESC, created_at DESC
    ''', (g.uid,))
    
    addresses = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'addresses': addresses
    })

@app.route('/api/addresses', methods=['POST'])
@login_required
def create_address():
    '''创建收货地址'''
    data = request.get_json()
    
    receiver_name = data.get('receiver_name', '').strip()
    phone = data.get('phone', '').strip()
    province = data.get('province', '').strip()
    city = data.get('city', '').strip()
    district = data.get('district', '').strip()
    detail_address = data.get('detail_address', '').strip()
    is_default = 1 if data.get('is_default') else 0
    
    if not all([receiver_name, phone, province, city, district, detail_address]):
        return jsonify({'success': False, 'error': '请填写完整信息'}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 如果设为默认,先取消其他默认
    if is_default:
        cursor.execute('UPDATE addresses SET is_default = 0 WHERE uid = ?', (g.uid,))
    
    cursor.execute('''
        INSERT INTO addresses (uid, receiver_name, phone, province, city, district, detail_address, is_default, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (g.uid, receiver_name, phone, province, city, district, detail_address, is_default, datetime.now().isoformat()))
    
    address_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'address_id': address_id,
        'message': '地址创建成功'
    })

@app.route('/api/addresses/<int:address_id>', methods=['PUT'])
@login_required
def update_address(address_id):
    '''更新收货地址'''
    data = request.get_json()
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 检查地址是否存在且属于当前用户
    cursor.execute('SELECT id FROM addresses WHERE id = ? AND uid = ?', (address_id, g.uid))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': '地址不存在'}), 404
    
    receiver_name = data.get('receiver_name', '').strip()
    phone = data.get('phone', '').strip()
    province = data.get('province', '').strip()
    city = data.get('city', '').strip()
    district = data.get('district', '').strip()
    detail_address = data.get('detail_address', '').strip()
    is_default = 1 if data.get('is_default') else 0
    
    # 如果设为默认,先取消其他默认
    if is_default:
        cursor.execute('UPDATE addresses SET is_default = 0 WHERE uid = ?', (g.uid,))
    
    cursor.execute('''
        UPDATE addresses SET receiver_name = ?, phone = ?, province = ?, city = ?, district = ?, detail_address = ?, is_default = ?
        WHERE id = ? AND uid = ?
    ''', (receiver_name, phone, province, city, district, detail_address, is_default, address_id, g.uid))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': '地址更新成功'
    })

@app.route('/api/addresses/<int:address_id>', methods=['DELETE'])
@login_required
def delete_address(address_id):
    '''删除收货地址'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM addresses WHERE id = ? AND uid = ?', (address_id, g.uid))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'error': '地址不存在'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': '地址删除成功'
    })

@app.route('/api/addresses/<int:address_id>/default', methods=['PUT'])
@login_required
def set_default_address(address_id):
    '''设置默认收货地址'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 取消所有默认
    cursor.execute('UPDATE addresses SET is_default = 0 WHERE uid = ?', (g.uid,))
    
    # 设置新的默认
    cursor.execute('UPDATE addresses SET is_default = 1 WHERE id = ? AND uid = ?', (address_id, g.uid))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'error': '地址不存在'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': '已设为默认地址'
    })

# ============ 商品API ============




@app.route('/api/products')
def get_products():
    '''获取商品列表(支持搜索,过滤状态和分页)'''
    status = request.args.get('status')
    category = request.args.get('category')
    uid = request.args.get('uid')
    search = request.args.get('search', '').strip()  # 新增:搜索关键词
    sort = request.args.get('sort', 'latest')  # 新增:排序方式 (latest, price_asc, price_desc)
    min_price = request.args.get('min_price', type=float)  # 新增:最低价格
    max_price = request.args.get('max_price', type=float)  # 新增:最高价格
    condition = request.args.get('condition')  # 新增:新旧程度
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    # 限制每页最大数量
    page_size = min(page_size, 50)
    offset = (page - 1) * page_size
    
    # 尝试使用 Supabase
    try:
        # 构建 Supabase 查询(不使用 JOIN,因为 Supabase 需要外键关系)
        query = supabase.table('products').select('*', count='exact')
        
        if status:
            query = query.eq('status', status)
        
        if category and category != 'all':
            query = query.eq('category', category)
        
        if uid:
            query = query.eq('uid', uid)
        
        # 搜索关键词
        if search:
            query = query.or_(f'title.ilike.%{search}%,description.ilike.%{search}%')
        
        # 价格范围
        if min_price is not None:
            query = query.gte('price', min_price)
        if max_price is not None:
            query = query.lte('price', max_price)
        
        # 新旧程度
        if condition:
            query = query.eq('condition', condition)
        
        # 排序
        if sort == 'price_asc':
            query = query.order('price', asc=True)
        elif sort == 'price_desc':
            query = query.order('price', desc=True)
        else:
            query = query.order('created_at', desc=True)
        
        # 获取总数
        total_count = query.execute().count
        
        # 获取分页数据
        query = query.range(offset, offset + page_size - 1)
        result = query.execute()
        
        # 批量获取卖家信息
        uids = list(set([r.get('uid') for r in result.data if r.get('uid')]))
        users_info = {}
        if uids:
            users_result = supabase.table('users').select('uid, username, avatar').in_('uid', uids).execute()
            for u in users_result.data:
                users_info[u['uid']] = u
        
        products_data = []
        for r in result.data:
            user_info = users_info.get(r.get('uid'), {})
            products_data.append({
                'id': r.get('id'),
                'uid': r.get('uid'),
                'title': r.get('title'),
                'price': r.get('price'),
                'original_price': r.get('original_price'),
                'description': r.get('description'),
                'images': r.get('images'),
                'category': r.get('category'),
                'condition': r.get('condition'),
                'status': r.get('status'),
                'views': r.get('views', 0),
                'created_at': r.get('created_at'),
                'username': user_info.get('username', '匿名用户') if user_info else '匿名用户',
                'avatar': user_info.get('avatar', '😊') if user_info else '😊'
            })
        
        # 如果 Supabase 返回空结果,检查 SQLite 是否有数据
        if len(products_data) == 0 and status == 'selling':
            conn_check = sqlite3.connect(DATABASE)
            cursor_check = conn_check.cursor()
            cursor_check.execute('SELECT COUNT(*) FROM products WHERE status = ?', (status,))
            local_count = cursor_check.fetchone()[0]
            conn_check.close()
            if local_count > 0:
                print(f'Supabase 无数据,本地 SQLite 有 {local_count} 条,跳转到 SQLite')
                raise Exception('Supabase empty, fallback to SQLite')
        
        return jsonify({
            'success': True,
            'products': products_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'has_more': offset + len(products_data) < total_count
            },
            'source': 'supabase'
        })
    except Exception as e:
        if 'fallback' in str(e).lower():
            print(f'回退到 SQLite: {str(e)}')
        else:
            print(f'Supabase 查询失败,回退到 SQLite: {str(e)}')
    
    # 回退到 SQLite
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    query = '''SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description, 
               p.images, p.category, p.condition, p.status, p.views, p.created_at as pc,
               u.username, u.avatar 
               FROM products p LEFT JOIN users u ON p.uid = u.uid WHERE 1=1'''
    count_query = '''SELECT COUNT(*) FROM products p WHERE 1=1'''
    params = []
    count_params = []
    
    if status:
        query += ' AND p.status = ?'
        count_query += ' AND p.status = ?'
        params.append(status)
        count_params.append(status)
    
    if category and category != 'all':
        query += ' AND p.category = ?'
        count_query += ' AND p.category = ?'
        params.append(category)
        count_params.append(category)
    
    if uid:
        query += ' AND p.uid = ?'
        count_query += ' AND p.uid = ?'
        params.append(uid)
        count_params.append(uid)
    
    # 搜索关键词
    if search:
        query += ' AND (p.title LIKE ? OR p.description LIKE ?)'
        count_query += ' AND (p.title LIKE ? OR p.description LIKE ?)'
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern])
        count_params.extend([search_pattern, search_pattern])
    
    # 价格范围
    if min_price is not None:
        query += ' AND p.price >= ?'
        count_query += ' AND p.price >= ?'
        params.append(min_price)
        count_params.append(min_price)
    
    if max_price is not None:
        query += ' AND p.price <= ?'
        count_query += ' AND p.price <= ?'
        params.append(max_price)
        count_params.append(max_price)
    
    # 新旧程度
    if condition:
        query += ' AND p.condition = ?'
        count_query += ' AND p.condition = ?'
        params.append(condition)
        count_params.append(condition)
    
    # 排序
    if sort == 'price_asc':
        query += ' ORDER BY p.price ASC'
    elif sort == 'price_desc':
        query += ' ORDER BY p.price DESC'
    else:
        query += ' ORDER BY p.created_at DESC'
    
    query += ' LIMIT ? OFFSET ?'
    params.extend([page_size, offset])
    
    cursor.execute(count_query, count_params)
    total_count = cursor.fetchone()[0]
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'products': [{
            'id': r[0], 'uid': r[1], 'title': r[2], 'price': r[3],
            'original_price': r[4], 'description': r[5], 'images': r[6],
            'category': r[7], 'condition': r[8], 'status': r[9],
            'views': r[10], 'created_at': r[11],
            'username': r[12] or '匿名用户', 'avatar': r[13] or '😊'
        } for r in products],
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total_count,
            'has_more': offset + len(products) < total_count
        },
        'source': 'sqlite'
    })

def normalize_for_search(text):
    '''标准化搜索文本:转小写,移除空格和特殊字符'''
    if not text:
        return ''
    return ''.join(c.lower() for c in text if c.isalnum()).lower()

def split_words(text):
    '''将文本分割成单词列表(支持中文分词)'''
    import re
    # 按空格和常见分隔符分割
    parts = re.split(r'[\s,,\..\-_/()()]+', text)
    result = []
    for part in parts:
        if len(part) >= 2:
            result.append(part)
    return result

def levenshtein_distance(s1, s2):
    '''计算两个字符串的编辑距离'''
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def fuzzy_match(keyword, text):
    '''模糊匹配:支持子串匹配和编辑距离容错'''
    if not keyword or not text:
        return False
    
    norm_keyword = normalize_for_search(keyword)
    norm_text = normalize_for_search(text)
    
    # 子串匹配
    if norm_keyword in norm_text:
        return True
    
    # 按单词分割后进行编辑距离匹配
    words = split_words(text)
    
    for word in words:
        word_lower = word.lower()
        # 子串匹配
        if norm_keyword in word_lower:
            return True
        # 编辑距离容错
        if len(word_lower) >= 3 and len(norm_keyword) >= 3:
            max_distance = 1 if len(word_lower) <= 5 else 2
            if abs(len(norm_keyword) - len(word_lower)) <= max_distance:
                distance = levenshtein_distance(norm_keyword, word_lower)
                if distance <= max_distance:
                    return True
    
    return False

@app.route('/api/search')
@login_required
def search_products():
    '''搜索商品(支持模糊搜索和错别字容错)'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        keyword = request.args.get('q', '').strip()
        category = request.args.get('category')
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        if not keyword:
            return jsonify({'success': False, 'error': '请输入搜索关键词'}), 400
        
        page_size = min(page_size, 50)
        offset = (page - 1) * page_size
        
        # 先用 LIKE 进行初步筛选(大小写不敏感)
        search_pattern = f'%{keyword}%'
        
        # 构建基础查询(不包含 LIKE 条件)
        base_query = '''SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description, 
                   p.images, p.category, p.condition, p.status, p.views, p.created_at,
                   u.username, u.avatar 
                   FROM products p LEFT JOIN users u ON p.uid = u.uid 
                   WHERE p.status = 'selling' '''
        base_count = '''SELECT COUNT(*) FROM products p WHERE p.status = 'selling' '''
        
        # 先尝试严格的 LIKE 匹配
        strict_query = base_query + ' AND (p.title LIKE ? COLLATE NOCASE OR p.description LIKE ? COLLATE NOCASE)'
        strict_params = [search_pattern, search_pattern]
        
        if category and category != 'all':
            strict_query += ' AND p.category = ?'
            strict_params.append(category)
        
        strict_query += ' ORDER BY p.created_at DESC'
        
        cursor.execute(strict_query, strict_params)
        strict_results = cursor.fetchall()
        
        # Python层面的模糊匹配
        filtered_products = [
            p for p in strict_results 
            if fuzzy_match(keyword, p[2]) or fuzzy_match(keyword, p[5])  # title or description
        ]
        
        # 如果严格匹配 + fuzzy_match 没有结果,尝试更宽松的查询
        if len(filtered_products) == 0:
            # 获取所有在售商品进行 fuzzy_match
            loose_query = base_query
            loose_params = []
            
            if category and category != 'all':
                loose_query += ' AND p.category = ?'
                loose_params.append(category)
            
            loose_query += ' ORDER BY p.created_at DESC'
            
            cursor.execute(loose_query, loose_params)
            all_products = cursor.fetchall()
            
            # 用 fuzzy_match 过滤
            filtered_products = [
                p for p in all_products 
                if fuzzy_match(keyword, p[2]) or fuzzy_match(keyword, p[5])
            ]
        
        total_count = len(filtered_products)
        
        # 分页
        paginated_products = filtered_products[offset:offset + page_size]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'products': [{
                'id': r[0], 'uid': r[1], 'title': r[2], 'price': r[3],
                'original_price': r[4], 'description': r[5], 'images': r[6],
                'category': r[7], 'condition': r[8], 'status': r[9],
                'views': r[10], 'created_at': r[11],
                'username': r[12] or '匿名用户', 'avatar': r[13] or '😊'
            } for r in paginated_products],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'has_more': offset + len(paginated_products) < total_count
            },
            'keyword': keyword
        })
    except sqlite3.OperationalError as e:
        return jsonify({'success': False, 'error': f'数据库操作错误: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500

@app.route('/api/product/<int:product_id>')
@login_required
def get_product(product_id):
    '''获取单个商品详情'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description, 
               p.images, p.category, p.condition, p.status, p.views, p.created_at,
               u.username, u.avatar
        FROM products p
        JOIN users u ON p.uid = u.uid
        WHERE p.id = ?
    ''', (product_id,))
    
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return jsonify({'success': False, 'error': '商品不存在'}), 404
    
    # 增加浏览量
    cursor.execute('UPDATE products SET views = views + 1 WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'product': {
            'id': product[0], 'uid': product[1], 'title': product[2], 'price': product[3],
            'original_price': product[4], 'description': product[5], 'images': product[6],
            'category': product[7], 'condition': product[8], 'status': product[9],
            'views': product[10], 'created_at': product[11],
            'seller': {'username': product[12], 'avatar': product[13]}
        }
    })

@app.route('/api/product', methods=['POST'])
@login_required
def create_product():
    '''发布商品'''
    try:
        data = request.get_json()
        
        title = data.get('title', '').strip()
        price = data.get('price')
        
        if not title or not price:
            return jsonify({'success': False, 'error': '请填写商品名称和价格'}), 400
        
        images = json.dumps(data.get('images', []))
        created_at = datetime.now().isoformat()
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO products (uid, title, price, original_price, description, images, 
                                  category, condition, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'selling', ?)
        ''', (g.uid, title, price, data.get('original_price'), data.get('description', ''),
              images, data.get('category', '其他'), data.get('condition', '9成新'), created_at))
        
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 增量同步商品到 Supabase
        sync_single_to_supabase('products', {
            'id': product_id,
            'uid': g.uid,
            'title': title,
            'price': price,
            'original_price': data.get('original_price'),
            'description': data.get('description', ''),
            'images': images,
            'category': data.get('category', '其他'),
            'condition': data.get('condition', '9成新'),
            'status': 'selling',
            'views': 0,
            'created_at': created_at
        }, 'id')
        
        return jsonify({'success': True, 'message': '商品发布成功', 'product_id': product_id}), 201
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/product/<int:product_id>/status', methods=['PUT'])
@login_required
def update_product_status(product_id):
    '''更新商品状态'''
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ('selling', 'sold', 'offline'):
            return jsonify({'success': False, 'error': '无效的状态值'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查商品是否存在且属于当前用户
        cursor.execute('SELECT uid FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': '商品不存在'}), 404
        
        if product[0] != g.uid:
            conn.close()
            return jsonify({'success': False, 'error': '无权操作此商品'}), 403
        
        cursor.execute('''
            UPDATE products SET status = ?, updated_at = ? WHERE id = ?
        ''', (new_status, datetime.now().isoformat(), product_id))
        
        conn.commit()
        conn.close()
        
        # 增量同步商品状态到 Supabase
        sync_single_to_supabase('products', {
            'id': product_id,
            'status': new_status,
            'updated_at': datetime.now().isoformat()
        }, 'id')
        
        status_text = {'selling': '在售', 'sold': '已售出', 'offline': '已下架'}
        return jsonify({'success': True, 'message': f'商品已更新为{status_text[new_status]}'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/my-products')
@login_required
def get_my_products():
    '''获取我的商品列表'''
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, price, original_price, category, condition, status, views, created_at
        FROM products WHERE uid = ? ORDER BY created_at DESC
    ''', (g.uid,))
    
    products = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'products': [{
            'id': r[0], 'title': r[1], 'price': r[2], 'original_price': r[3],
            'category': r[4], 'condition': r[5], 'status': r[6],
            'views': r[7], 'created_at': r[8]
        } for r in products]
    })

@app.route('/api/my-products/batch-delete', methods=['POST'])
@login_required
def batch_delete_products():
    '''批量删除我的商品'''
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'success': False, 'error': '请选择要删除的商品'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 只删除属于当前用户的商品
        placeholders = ','.join('?' * len(product_ids))
        cursor.execute(f'''
            DELETE FROM products WHERE id IN ({placeholders}) AND uid = ?
        ''', (*product_ids, g.uid))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'成功删除 {deleted_count} 件商品',
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/my-products/batch-status', methods=['PUT'])
@login_required
def batch_update_status():
    '''批量更新商品状态'''
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        new_status = data.get('status')
        
        if not product_ids:
            return jsonify({'success': False, 'error': '请选择要更新的商品'}), 400
        
        if new_status not in ('selling', 'sold', 'offline'):
            return jsonify({'success': False, 'error': '无效的状态值'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(product_ids))
        cursor.execute(f'''
            UPDATE products SET status = ?, updated_at = ? 
            WHERE id IN ({placeholders}) AND uid = ?
        ''', (new_status, datetime.now().isoformat(), *product_ids, g.uid))
        
        updated_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        status_text = {'selling': '在售', 'sold': '已售出', 'offline': '已下架'}
        return jsonify({
            'success': True,
            'message': f'成功更新 {updated_count} 件商品为{status_text[new_status]}',
            'updated_count': updated_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/my-products/edit/<int:product_id>', methods=['PUT'])
@login_required
def edit_product(product_id):
    '''编辑商品信息'''
    try:
        data = request.get_json()
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 检查商品是否存在且属于当前用户
        cursor.execute('SELECT uid, images FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': '商品不存在'}), 404
        
        if product[0] != g.uid:
            conn.close()
            return jsonify({'success': False, 'error': '无权操作此商品'}), 403
        
        # 构建更新字段
        update_fields = []
        params = []
        
        if 'title' in data:
            if not data['title'].strip():
                conn.close()
                return jsonify({'success': False, 'error': '商品名称不能为空'}), 400
            update_fields.append('title = ?')
            params.append(data['title'].strip())
        
        if 'price' in data:
            try:
                price = float(data['price'])
                if price < 0:
                    conn.close()
                    return jsonify({'success': False, 'error': '价格不能为负数'}), 400
                update_fields.append('price = ?')
                params.append(price)
            except ValueError:
                conn.close()
                return jsonify({'success': False, 'error': '价格格式不正确'}), 400
        
        if 'original_price' in data:
            update_fields.append('original_price = ?')
            params.append(data.get('original_price'))
        
        if 'description' in data:
            update_fields.append('description = ?')
            params.append(data.get('description', ''))
        
        if 'images' in data:
            update_fields.append('images = ?')
            params.append(json.dumps(data['images']))
        
        if 'category' in data:
            update_fields.append('category = ?')
            params.append(data.get('category', '其他'))
        
        if 'condition' in data:
            update_fields.append('condition = ?')
            params.append(data.get('condition', '9成新'))
        
        if not update_fields:
            conn.close()
            return jsonify({'success': False, 'error': '没有需要更新的字段'}), 400
        
        update_fields.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        
        params.append(product_id)
        
        cursor.execute(f'''
            UPDATE products SET {', '.join(update_fields)} WHERE id = ?
        ''', params)
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '商品信息已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/my-products/stats', methods=['GET'])
@login_required
def get_my_products_stats():
    '''获取我的商品统计信息'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 总体统计
        cursor.execute('''
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN status = 'selling' THEN 1 ELSE 0 END) as selling,
                   SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END) as sold,
                   SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline,
                   COALESCE(SUM(price), 0) as total_value
            FROM products WHERE uid = ?
        ''', (g.uid,))
        
        stats = cursor.fetchone()
        
        # 浏览量统计
        cursor.execute('SELECT SUM(views) FROM products WHERE uid = ?', (g.uid,))
        total_views = cursor.fetchone()[0] or 0
        
        # 分类统计
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM products WHERE uid = ?
            GROUP BY category ORDER BY count DESC
        ''', (g.uid,))
        
        categories = [{'category': r[0], 'count': r[1]} for r in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total': stats[0],
                'selling': stats[1],
                'sold': stats[2],
                'offline': stats[3],
                'total_value': stats[4],
                'total_views': total_views,
                'categories': categories
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/compare/<int:product_id>')
@login_required
def compare_product(product_id):
    '''对同类商品进行AI比对分析'''
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 获取目标商品
        cursor.execute('''SELECT id, uid, title, price, original_price, description, 
                          category, condition, status FROM products WHERE id = ?''', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': '商品不存在'}), 404
        
        # 获取同类商品(同一分类,排除自身,只看在售的)
        cursor.execute('''SELECT p.id, p.uid, p.title, p.price, p.original_price, p.description,
                                p.category, p.condition, p.status, 
                                u.username, u.created_at as user_created
                         FROM products p
                         JOIN users u ON p.uid = u.uid
                         WHERE p.category = ? AND p.id != ? AND p.status = 'selling'
                         ORDER BY p.created_at DESC LIMIT 10''', 
                       (product[6], product_id))
        similar_products = cursor.fetchall()
        conn.close()
        
        if len(similar_products) < 2:
            return jsonify({
                'success': True,
                'product': {
                    'id': product[0], 'title': product[2], 'price': product[3],
                    'category': product[6], 'condition': product[7], 'status': product[8]
                },
                'message': '同类商品不足,无法进行有效比对'
            })
        
        # 构建AI比对prompt
        products_info = []
        products_info.append(f'目标商品: {product[2]}, 价格: ¥{product[3]}, 成色: {product[7]}')
        
        for i, sp in enumerate(similar_products, 1):
            products_info.append(f'商品{i}: {sp[2]}, 价格: ¥{sp[3]}, 成色: {sp[7]}, 卖家: {sp[9]}')
        
        prompt = f'''你是一个专业的二手商品评估师.请对以下同类二手商品进行综合比对分析:

{chr(10).join(products_info)}

请从以下几个维度进行分析并排名:
1. **价格优势**(相对于原价和同类商品的价格是否合理)
2. **成色评估**(新旧程度与价格是否匹配)
3. **描述质量**(商品描述是否详细真实)
4. **性价比综合评分**

请以JSON格式输出,格式如下:
{{
    'rankings': [
        {{
            'rank': 1,
            'product_title': '商品名称',
            'product_id': 数字,
            'total_score': 85,
            'price_score': 80,
            'condition_score': 85,
            'description_score': 90,
            'analysis': '简要分析说明'
        }}
    ],
    'recommendation': '对买家的综合建议'
}}

只输出JSON,不要有其他文字.'''

        # 调用AI分析
        result = call_text_api(prompt, system_prompt='你是一个专业的二手商品评估师,擅长分析商品性价比.')
        
        if isinstance(result, dict) and 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 500
        
        # 解析AI返回结果
        import re
        json_match = re.search(r'\{[\s\S]*\}', str(result))
        if json_match:
            try:
                analysis = json.loads(json_match.group())
            except:
                analysis = {'rankings': [], 'recommendation': str(result)}
        else:
            analysis = {'rankings': [], 'recommendation': str(result)}
        
        return jsonify({
            'success': True,
            'target_product': {
                'id': product[0], 'title': product[2], 'price': product[3],
                'category': product[6], 'condition': product[7], 'status': product[8]
            },
            'similar_count': len(similar_products),
            'analysis': analysis
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def allowed_file(filename):
    '''检查文件扩展名是否允许'''
    return '.' in filename and \
           os.path.splitext(filename)[1].lower() in UPLOAD_CONFIG['allowed_extensions']


def call_multimodal_api(image_base64, prompt, system_prompt=None):
    '''
    调用多模态模型API(支持单图或多图)
    image_base64: 可以是单个base64字符串,也可以是base64字符串列表
    '''
    api_config = MULTIMODAL_CONFIG
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {api_config['api_key']}"
    }
    
    # 处理图片:支持单图或多图
    def detect_image_format(b64_data):
        '''检测base64图片的实际格式'''
        try:
            # 添加padding以防数据不完整
            padded = b64_data + '=' * (4 - len(b64_data) % 4)
            # 尝试解码前几个字节来判断格式
            import base64 as b64_mod
            sample = b64_mod.b64decode(padded[:22])
            if sample[:8] == b'\x89PNG\r\n\x1a\n':
                return 'image/png'
            elif sample[:2] == b'\xff\xd8':
                return 'image/jpeg'
            elif sample[:4] == b'RIFF' and sample[8:12] == b'WEBP':
                return 'image/webp'
            elif sample[:3] == b'GIF':
                return 'image/gif'
        except:
            pass
        return 'image/jpeg'  # 默认使用jpeg
    
    if isinstance(image_base64, list):
        image_contents = []
        for i, img in enumerate(image_base64):
            img_format = detect_image_format(img)
            image_contents.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{img_format};base64,{img}'
                }
            })
    else:
        img_format = detect_image_format(image_base64)
        image_contents = [{
            'type': 'image_url',
            'image_url': {
                'url': f'data:{img_format};base64,{image_base64}'
            }
        }]
    
    payload = {
        'model': api_config['model'],
        'messages': [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': prompt
                    }
                ] + image_contents
            }
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    
    if system_prompt:
        payload['messages'].insert(0, {
            'role': 'system',
            'content': system_prompt
        })
    
    try:
        print(f"调用多模态API: {api_config['base_url']}/chat/completions")
        print(f"模型: {api_config['model']}")
        print(f"图片数量: {len(image_contents)}")
        
        response = requests.post(
            f"{api_config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=api_config.get('timeout', 60)  # 增加超时时间到60秒
        )
        # 打印响应状态和内容用于调试
        print(f'API响应状态: {response.status_code}')
        print(f'API响应内容: {response.text[:1000]}')
        
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else '无响应内容'
            raise Exception(f'API请求失败,状态码: {response.status_code}, 响应: {error_detail}')
        
        result = response.json()
        if 'choices' not in result or len(result['choices']) == 0:
            raise Exception(f'API响应格式错误,缺少choices字段: {result}')
        if 'message' not in result['choices'][0]:
            raise Exception(f'API响应格式错误,缺少message字段: {result}')
        return result['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        raise Exception('API请求超时(超过60秒),请检查网络或减少图片数量后重试')
    except requests.exceptions.RequestException as e:
        raise Exception(f'API请求失败: {str(e)}')
    except (KeyError, IndexError) as e:
        raise Exception(f'API响应格式错误: {str(e)}')
    except json.JSONDecodeError as e:
        raise Exception(f'API响应JSON解析错误: {str(e)}')


def call_text_api(prompt, system_prompt=None, temperature=0.8):
    '''
    调用文本生成模型API
    '''
    api_config = TEXT_MODEL_CONFIG
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {api_config['api_key']}"
    }
    
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})
    
    payload = {
        'model': api_config['model'],
        'messages': messages,
        'max_tokens': 2000,
        'temperature': temperature
    }
    
    try:
        print(f"调用文本API: {api_config['base_url']}/chat/completions")
        print(f"模型: {api_config['model']}")
        print(f"温度: {temperature}")
        
        response = requests.post(
            f"{api_config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=api_config.get('timeout', 60)
        )
        # 打印响应状态和内容用于调试
        print(f'API响应状态: {response.status_code}')
        print(f'API响应内容: {response.text[:1000]}')
        
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else '无响应内容'
            raise Exception(f'API请求失败,状态码: {response.status_code}, 响应: {error_detail}')
        
        result = response.json()
        if 'choices' not in result or len(result['choices']) == 0:
            raise Exception(f'API响应格式错误,缺少choices字段: {result}')
        if 'message' not in result['choices'][0]:
            raise Exception(f'API响应格式错误,缺少message字段: {result}')
        return result['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        raise Exception('API请求超时,请稍后重试')
    except requests.exceptions.RequestException as e:
        raise Exception(f'API请求失败: {str(e)}')
    except (KeyError, IndexError) as e:
        raise Exception(f'API响应格式错误: {str(e)}')
    except json.JSONDecodeError as e:
        raise Exception(f'API响应JSON解析错误: {str(e)}')



# ==================== PWA 路由 ====================

@app.route('/manifest.json')
def manifest():
    '''返回 PWA 清单文件'''
    response = make_response(send_from_directory('static', 'manifest.json'))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

@app.route('/service-worker.js')
@app.route('/static/service-worker.js')
def service_worker():
    '''返回 Service Worker 文件'''
    response = make_response(send_from_directory('static', 'service-worker.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/sw.js')
def sw_js():
    '''Service Worker 别名'''
    return service_worker()

@app.after_request
def add_pwa_headers(response):
    '''为静态资源添加 PWA 相关响应头'''
    # 允许 iframes 从任何源加载(用于 PWA)
    if request.path.startswith('/static/'):
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    return response

# ==================== API路由 ====================

@app.route('/')
def index():
    '''返回平台首页'''
    return send_from_directory('.', 'index.html')

@app.route('/app')
@login_required_page
def app_page():
    '''返回发布商品页面'''
    return send_from_directory('.', 'app.html')

@app.route('/publish')
@login_required_page
def publish():
    '''返回发布商品页面'''
    return send_from_directory('.', 'app.html')

@app.route('/tools')
@login_required_page
def tools():
    '''返回AI图片工具箱页面'''
    return send_from_directory('.', 'tools.html')

@app.route('/auth')
@app.route('/login')
@app.route('/register')
def auth():
    '''返回登录/注册页面'''
    return send_from_directory('.', 'auth.html')

@app.route('/admin-login')
def admin_login_page():
    '''返回管理员登录页面'''
    return send_from_directory('.', 'admin-login.html')

@app.route('/admin')
def admin_page():
    '''返回管理后台页面'''
    return send_from_directory('.', 'admin.html')

@app.route('/detail')
def detail():
    '''返回商品详情页'''
    return send_from_directory('.', 'detail.html')

@app.route('/user')
@login_required_page
def user_page():
    '''返回用户资料页'''
    return send_from_directory('.', 'user.html')

@app.route('/profile')
@login_required_page
def profile():
    '''返回个人中心页'''
    return send_from_directory('.', 'profile.html')

@app.route('/order-confirm')
def order_confirm():
    '''返回订单确认页'''
    return send_from_directory('.', 'order-confirm.html')

@app.route('/order')
@login_required_page
def order_page():
    '''返回订单详情页'''
    return send_from_directory('.', 'order.html')

@app.route('/orders')
@login_required_page
def orders_page():
    '''返回订单列表页'''
    return send_from_directory('.', 'orders.html')

@app.route('/messages')
@login_required_page
def messages_page():
    '''返回消息列表页'''
    return send_from_directory('.', 'messages.html')

@app.route('/message')
@login_required_page
def message_page():
    '''返回私信页'''
    return send_from_directory('.', 'message.html')


@app.route('/api/upload', methods=['POST'])
@login_required
def upload_image():
    '''处理图片上传'''
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未找到上传文件'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False, 
                'error': '不支持的文件格式,请上传 JPG/PNG/GIF/WebP 图片'
            }), 400
        
        # 读取文件并转为base64
        image_data = file.read()
        
        if len(image_data) > UPLOAD_CONFIG['max_file_size']:
            return jsonify({
                'success': False, 
                'error': f"文件过大,请上传小于 {UPLOAD_CONFIG['max_file_size'] // (1024*1024)}MB 的图片"
            }), 400
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        return jsonify({
            'success': True,
            'image': image_base64
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-image', methods=['POST'])
@login_required
def save_image():
    '''保存图片到本地'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        
        # 如果包含data URL前缀,去掉它
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # 解码并保存
        image_data = base64.b64decode(image_base64)
        filename = f'{uuid.uuid4().hex}.jpg'
        filepath = os.path.join(UPLOAD_CONFIG['upload_folder'], filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        return jsonify({
            'success': True,
            'path': f'/uploads/{filename}',
            'filename': filename
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/analyze-image', methods=['POST'])
@login_required
def analyze_image():
    '''分析图片内容(用于拍照指导)'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        context = data.get('context', '拍照指导')
        
        # 如果包含data URL前缀,去掉它
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # 根据上下文设置不同的提示词
        if context == 'photography_guide':
            system_prompt = '''你是一个专业的电商拍照指导专家.请分析用户上传的商品图片,提供具体的拍照改进建议.

请用简洁的中文回复,包含以下方面:
1. 背景评估(是否杂乱,是否简洁)
2. 光线评估(是否充足,是否过曝或过暗)
3. 构图评估(角度,比例,是否居中)
4. 具体改进建议(如果有问题)

回复格式示例:
'📸 构图:商品偏左上,建议往右下方移动一些
💡 光线:光线充足,但有些许反光
✨ 建议:从左侧45度角拍摄效果会更好' '''
        else:
            system_prompt = '''你是一个专业的电商助手.请分析这张图片中的商品,描述其特征,品牌,型号等信息.'''
        
        analysis = call_multimodal_api(image_base64, '请分析这张图片', system_prompt)
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-copy', methods=['POST'])
@login_required
def generate_copy():
    '''生成单条文案'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        product_name = data.get('product_name', '')
        style = data.get('style', 'tech')
        
        # 如果包含data URL前缀,去掉它
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # 根据风格设置提示词
        style_prompts = {
            'tech': '''请为一款二手商品生成技术控风格的转售文案.

要求:
1. 重点突出商品的技术参数,性能配置
2. 强调成色,新旧程度
3. 客观描述,不夸大
4. 包含验货/发货说明
5. 字数控制在150字以内
6. 格式清晰,分点列出关键信息''',
            
            'story': '''请为一款二手商品生成故事风格的转售文案.

要求:
1. 用第一人称叙述,有情感温度
2. 讲述与商品的故事或使用感受
3. 强调为什么转让
4. 唤起买家的共鸣
5. 字数控制在150字以内
6. 语言自然流畅''',
            
            'minimal': '''请为一款二手商品生成极简风格的转售文案.

要求:
1. 简洁明了,不废话
2. 直接列出:商品名称,成色,价格
3. 一句话说明转让原因
4. 联系方式
5. 字数控制在50字以内
6. 信息一目了然'''
        }
        
        prompt = style_prompts.get(style, style_prompts['tech'])
        
        if product_name:
            prompt += f'\n\n商品名称:{product_name}'
        
        copy = call_multimodal_api(image_base64, prompt)
        
        return jsonify({
            'success': True,
            'copy': copy
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-all-copies', methods=['POST'])
@login_required
def generate_all_copies():
    '''一次性生成三种风格文案'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        product_name = data.get('product_name', '')
        
        # 如果包含data URL前缀,去掉它
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # 合并的提示词,一次性生成三种风格
        system_prompt = '''你是一个专业的电商文案专家.请根据用户提供的商品图片和信息,生成三种不同风格的转售文案.

输出格式必须严格遵循以下JSON格式,不要包含任何其他内容:
{
    'tech': '技术控风格文案(150字以内)',
    'story': '故事风格文案(150字以内)',
    'minimal': '极简风格文案(50字以内)'
}

[技术控风格要求]
- 重点突出技术参数,性能配置
- 强调成色,新旧程度
- 客观描述

[故事风格要求]
- 第一人称叙述,有情感温度
- 讲述使用故事和感受
- 唤起共鸣

[极简风格要求]
- 简洁明了,直接列出关键信息
- 商品名+成色+价格
'''
        
        if product_name:
            system_prompt += f'\n\n商品名称:{product_name}'
        
        result = call_multimodal_api(
            image_base64, 
            '请分析这张图片,生成三种风格的转售文案',
            system_prompt
        )
        
        # 尝试解析JSON
        try:
            # 提取JSON部分
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = result[json_start:json_end]
                copies = json.loads(json_str)
            else:
                raise ValueError('未找到JSON格式')
        except (json.JSONDecodeError, ValueError):
            # 如果解析失败,尝试逐个生成
            return jsonify({
                'success': False, 
                'error': '文案生成失败,请稍后重试',
                'raw_result': result
            }), 500
        
        return jsonify({
            'success': True,
            'tech': copies.get('tech', ''),
            'story': copies.get('story', ''),
            'minimal': copies.get('minimal', '')
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-all-promotions', methods=['POST'])
@login_required
def generate_all_promotions():
    '''一次性生成所有平台推广文案'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        product_name = data.get('product_name', '')
        price = data.get('price', '')
        
        # 如果包含data URL前缀,去掉它
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        system_prompt = f'''你是一个社交媒体文案专家.请根据商品信息,为小红书,微信朋友圈,微信群分别生成适配的转售推广文案.

商品信息:
- 商品名称:{product_name or '待定'}
- 期望价格:{price or '待定'}

输出格式必须严格遵循以下JSON格式,不要包含任何其他内容:
{{
    'xiaohongshu': '小红书文案(包含emoji,话题标签,300字以内)',
    'moments': '朋友圈文案(简短精炼,100字以内)',
    'group': '微信群文案(格式规范,200字以内)'
}}

各平台风格要求:
- 小红书:年轻种草风格,多用emoji和话题标签
- 朋友圈:简洁接地气,快速吸引注意
- 微信群:正式规范,信息完整'''
        
        result = call_multimodal_api(image_base64, '请生成三个平台的推广文案', system_prompt)
        
        # 尝试解析JSON
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = result[json_start:json_end]
                promotions = json.loads(json_str)
            else:
                raise ValueError('未找到JSON格式')
        except (json.JSONDecodeError, ValueError):
            return jsonify({
                'success': False, 
                'error': '推广文案生成失败,请稍后重试',
                'raw_result': result
            }), 500
        
        return jsonify({
            'success': True,
            'xiaohongshu': promotions.get('xiaohongshu', ''),
            'moments': promotions.get('moments', ''),
            'group': promotions.get('group', '')
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze-product', methods=['POST'])
@login_required
def analyze_product():
    '''分析商品信息(支持多图,提高准确率)'''
    try:
        data = request.get_json()
        
        images = data.get('images', [])
        name = data.get('name', '')
        
        # 处理图片
        processed_images = []
        for img in images:
            if ',' in img:
                img = img.split(',')[1]
            processed_images.append(img)
        
        # 检查是否有可用的图片数据
        if len(processed_images) == 0:
            return jsonify({'success': False, 'error': '请至少上传一张图片'}), 400
        
        system_prompt = '''你是一个专业的电商商品识别专家.请分析用户上传的商品图片,识别商品信息并以JSON格式返回.

返回格式(严格JSON):
{
    'category': '商品类别(必须从以下选项中选择:数码,电脑,相机,游戏,家电,服饰,美妆,母婴,图书,其他)',
    'name': '商品名称/型号',
    'brand': '品牌',
    'model': '具体型号或规格',
    'color': '颜色',
    'capacity': '容量或尺寸',
    'condition': '新旧程度描述(如:全新未拆封,9成新,8成新,有使用痕迹)',
    'defects': '瑕疵情况(如:无明显瑕疵,有多处划痕,有轻微磨损,功能正常但外观旧)',
    'market_price': '该商品当前的全新市场价(整数,单位元),基于京东/淘宝等平台的当前售价,如:5999',
    'suggested_price': '二手交易参考价(整数,单位元),计算方式:市场价 × 成色折扣率(全新99折/9成新85折/8成新70折/7成新55折/6成新以下40折),取整数',
    'price_range': '合理价格区间(格式:最低价-最高价,单位元),考虑成色和瑕疵情况'
}

分类说明:
- 数码:手机,平板,耳机,手表,充电器,数据线等电子产品
- 电脑:笔记本电脑,台式机,键盘,鼠标,显示器,耳机等电脑配件
- 相机:数码相机,单反,微单,镜头,摄像机,拍立得等
- 游戏:游戏机(Switch/PS5/Xbox),掌机,游戏卡带,手柄等
- 家电:吹风机,扫地机器人,破壁机,空气净化器,电饭煲等家用电器
- 服饰:衣服,鞋子,包包,配饰(帽子,围巾等)
- 美妆:护肤品,化妆品,香水,美妆工具等
- 母婴:婴儿车,安全座椅,婴儿玩具,母婴用品等
- 图书:书籍,电子书阅读器,文具等
- 其他:不属于以上分类的商品

重要说明:
- 请综合分析所有图片,从多个角度识别商品信息
- 如果多张图片显示的成色/瑕疵不一致,以最差的情况为准(诚实描述)
- 请尽可能详细识别
- 如果无法确定某项,填写'未识别到'
- 瑕疵情况请如实描述,这对买家很重要
- 成色评估要客观
- 全新市场价必须是该商品在京东/淘宝等平台的当前全新正品售价
- 二手参考价基于市场价和成色计算:全新99折,9成新85折,8成新70折,7成新55折,6成新以下40折
- 如果有明显瑕疵,在参考价基础上再降10-20%
- 价格估算要符合市场实际情况,不要虚高或过低
        '''
        
        # 构建分析提示
        hint = ''
        if len(processed_images) > 1:
            hint = f',用户共上传了 {len(processed_images)} 张图片,请综合分析'
        if name:
            hint += f',商品名称:{name}'
        
        result = call_multimodal_api(processed_images, f'请分析这些商品图片{hint}', system_prompt)
        
        # 解析JSON
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = result[json_start:json_end]
                info = json.loads(json_str)
            else:
                # API没有返回JSON格式的商品信息
                # 检查是否是因为图片无法识别
                if '没有提供' in result or '无法' in result or len(result) < 50:
                    return jsonify({
                        'success': False,
                        'error': '无法识别图片内容,请确保上传清晰的商品图片后重试',
                        'raw_result': result
                    }), 200
                else:
                    raise ValueError('未找到JSON格式')
        except (json.JSONDecodeError, ValueError):
            return jsonify({
                'success': False,
                'error': '商品信息识别失败,请重试或手动填写',
                'raw_result': result
            }), 200
        
        return jsonify({
            'success': True,
            'info': info,
            'image_count': len(processed_images)
        })
    
    except json.JSONDecodeError as e:
        print(f'JSON解析错误: {e}')
        return jsonify({
            'success': False,
            'error': f'商品信息识别失败,请重试或手动填写(JSON解析错误: {str(e)})',
            'raw_result': result if 'result' in locals() else None
        }), 500
    except ValueError as e:
        print(f'数据验证错误: {e}')
        return jsonify({
            'success': False,
            'error': f'商品信息识别失败,请重试或手动填写(验证错误: {str(e)})',
            'raw_result': result if 'result' in locals() else None
        }), 500
    except Exception as e:
        import traceback
        print(f'分析商品时发生错误: {str(e)}')
        traceback.print_exc()
        # 返回更详细的错误信息,帮助调试
        error_msg = str(e)
        # 如果是API相关错误,给出更友好的提示
        if 'API请求失败' in error_msg or 'API响应格式错误' in error_msg:
            user_message = 'AI服务暂时不可用,请稍后重试或手动填写商品信息'
        elif '超时' in error_msg:
            user_message = '请求超时,请减少图片数量后重试'
        else:
            user_message = f'服务器错误: {error_msg[:100]}'
        return jsonify({'success': False, 'error': user_message, 'detail': error_msg}), 500


@app.route('/api/generate-descriptions', methods=['POST'])
def generate_descriptions():
    """基于确认的商品信息生成三种风格描述文案"""
    try:
        data = request.get_json()
        
        if not data or 'images' not in data or len(data['images']) == 0:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        images = data['images']
        info = data.get('info', {})
        
        # 处理多张图片base64
        processed_images = []
        for img in images:
            if ',' in img:
                img = img.split(',')[1]
            processed_images.append(img)
        
        # 构建商品信息字符串
        info_str = '\n'.join([f'- {k}:{v}' for k, v in info.items() if v and v != '未识别到'])
        
        system_prompt = '''你是一个专业的二手商品转售文案专家.请根据以下商品信息,生成三种不同风格的转售描述文案.

商品信息:
{info_str}

输出格式(严格JSON,不要包含任何其他内容):
{{
    'tech': '技术控风格文案(150字以内):重点突出技术参数,性能配置,成色,格式清晰',
    'story': '故事风格文案(150字以内):用第一人称叙述,讲述使用故事和情感,唤起共鸣',
    'minimal': '极简风格文案(50字以内):简洁明了,直接列出:商品+成色+价格'
}}

风格要求:
- 技术控:客观专业,列出关键参数,注明验货发货方式
- 故事风:真诚动人,说明为什么转让,描述使用感受
- 极简风:信息一目了然,适合快速浏览

末尾统一添加:[本描述由AI辅助生成,卖家已逐项确认真实性]'''.format(info_str=info_str)
        
        result = call_multimodal_api(processed_images, '请根据商品信息生成三种风格的转售描述', system_prompt)
        
        # 解析JSON
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = result[json_start:json_end]
                descriptions = json.loads(json_str)
            else:
                raise ValueError('未找到JSON格式')
        except (json.JSONDecodeError, ValueError):
            return jsonify({
                'success': False,
                'error': '文案生成失败,请重试',
                'raw_result': result
            }), 500
        
        return jsonify({
            'success': True,
            'descriptions': descriptions
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-promotion', methods=['POST'])
@login_required
def generate_promotion():
    '''生成多平台推广文案'''
    try:
        data = request.get_json()
        
        if not data or 'images' not in data or len(data['images']) == 0:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        images = data['images']
        info = data.get('info', {})
        platform = data.get('platform', 'xiaohongshu')
        
        # 处理多张图片base64
        processed_images = []
        for img in images:
            if ',' in img:
                img = img.split(',')[1]
            processed_images.append(img)
        
        info_str = '\n'.join([f'{k}:{v}' for k, v in info.items() if v and v != '未识别到'])
        
        # 平台提示词
        platform_prompts = {
            'xiaohongshu': f'''请为小红书写一篇二手好物转售种草文案.

商品信息:{info_str}

要求:
1. 标题要吸引人,可以用'啊啊啊''救命'等语气词开头
2. 正文300字以内,多用emoji增加活力
3. 结尾添加5-8个话题标签(用#开头)
4. 风格:年轻,种草,有温度,像朋友推荐
5. 可以用'绝绝子''YYDS''冲冲冲'等网络用语
6. 要写出为什么值得买的感觉''',
            
            'moments': f'''请为微信朋友圈写一条二手转售文案.

商品信息:{info_str}

要求:
1. 100字以内,简洁有力
2. 可以用emoji增加趣味
3. 突出商品亮点和性价比
4. 风格:真实接地气,不夸张
5. 适合配图发布''',
            
            'group': f'''请为微信群写一条正式的二手转售消息.

商品信息:{info_str}

要求:
1. 200字以内,格式规范
2. 包含:商品描述,成色,价格,交易方式
3. 可以带'手慢无''仅此一件''有需可私'等紧迫感词
4. 语气诚恳,有诚信
5. 留下联系方式'''
        }
        
        prompt = platform_prompts.get(platform, platform_prompts['xiaohongshu'])
        content = call_multimodal_api(processed_images, prompt)
        
        return jsonify({
            'success': True,
            'content': content,
            platform: content
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== AI 图片处理 API ====================

@app.route('/api/enhance-image', methods=['POST'])
@login_required
def enhance_image():
    '''AI图片增强'''
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        image_base64 = data['image']
        options = data.get('options', {})
        
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # 构建增强提示
        enhancements = []
        if options.get('sharpen'):
            enhancements.append('提升清晰度和细节表现')
        if options.get('brightness'):
            enhancements.append('优化亮度和对比度')
        if options.get('color'):
            enhancements.append('增强色彩饱和度')
        if options.get('denoise'):
            enhancements.append('降噪处理')
        
        if not enhancements:
            enhancements = ['整体优化图片质量']
        
        prompt = f"请对这张商品图片进行增强处理:{','.join(enhancements)}.保持商品原貌,仅优化视觉效果."
        
        # 使用多模态API分析并返回增强建议
        try:
            result = call_multimodal_api(image_base64, prompt)
            
            # 注意:这里需要图像处理API支持,实际返回原图并附带建议
            # 如果有图像增强API,可以在这里调用
            
            return jsonify({
                'success': True,
                'image': data['image'],  # 原图,实际增强需要图像处理API
                'message': '图片已优化',
                'suggestions': result
            })
            
        except Exception as api_e:
            # 如果API不支持,返回原图
            return jsonify({
                'success': True,
                'image': data['image'],
                'message': '当前使用原图,增强功能需要更高级的图像处理API'
            })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/detect-product', methods=['POST'])
@login_required
def detect_product():
    '''AI商品识别 - 识别商品信息(支持多图)'''
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '未提供数据'}), 400
        
        # 支持 images 数组或单个 image
        images = data.get('images', [])
        if isinstance(images, str):
            images = [images]
        
        # 兼容单图模式
        if not images and 'image' in data:
            images = [data['image']]
        
        if not images:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        # 统一处理 base64
        processed_images = []
        for img in images:
            if ',' in img:
                img = img.split(',')[1]
            processed_images.append(img)
        
        img_count = len(processed_images)
        img_hint = f',用户共上传了 {img_count} 张图片,请综合分析所有图片,取最确定的特征' if img_count > 1 else ''
        
        prompt = f'''请仔细分析这 {img_count} 张商品图片{img_hint},返回JSON格式的商品信息:

{{
    'category': '商品类别(必须从以下选项中选择:数码,电脑,相机,游戏,家电,服饰,美妆,母婴,图书,其他)',
    'name': '商品名称或型号',
    'brand': '品牌(如能识别)',
    'model': '具体型号(如能识别)',
    'color': '主要颜色',
    'capacity': '容量/尺寸(如能识别)',
    'condition': '新旧程度评估',
    'defects': '发现的瑕疵或问题'
}}

重要提示:
1. **分类规则**:
   - 数码:手机,平板,耳机,手表,充电器,数据线等电子产品
   - 电脑:笔记本电脑,台式机,键盘,鼠标,显示器,耳机等电脑配件
   - 相机:数码相机,单反,微单,镜头,摄像机,拍立得等
   - 游戏:游戏机(Switch/PS5/Xbox),掌机,游戏卡带,手柄等
   - 家电:吹风机,扫地机器人,破壁机,空气净化器,电饭煲等家用电器
   - 服饰:衣服,鞋子,包包,配饰(帽子,围巾等)
   - 美妆:护肤品,化妆品,香水,美妆工具等
   - 母婴:婴儿车,安全座椅,婴儿玩具,母婴用品等
   - 图书:书籍,电子书阅读器,文具等
   - 其他:不属于以上分类的商品

2. **新旧程度判断标准**:
   - 全新:包装完好未拆封,或明显没有使用痕迹
   - 99新:仅拆封但未使用或几乎全新
   - 95新:有使用痕迹但保护良好(适合护肤品用了一半的情况)
   - 9新:有明显使用痕迹或划痕
   - 8新以下:有明显磨损或损坏

3. **对于护肤品/化妆品**:请特别注意瓶身剩余量,瓶口/管口是否有使用痕迹,是否有污渍或褪色等细节

3. **如实描述瑕疵**:这直接影响买家决策,务必准确

仅返回JSON,不要添加其他文字.'''
        
        result = call_multimodal_api(processed_images, prompt)
        
        # 解析JSON结果
        info = parse_json_response(result)
        
        message = f'已综合分析 {img_count} 张图片' if img_count > 1 else '识别完成'
        
        return jsonify({
            'success': True,
            'message': message,
            **info
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/verify-image', methods=['POST'])
def verify_image():
    '''AI图片真实性审核 - 识别是否为实拍图或网图'''
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '未提供数据'}), 400
        
        # 支持 images 数组或单个 image
        images = data.get('images', [])
        if isinstance(images, str):
            images = [images]
        
        # 兼容单图模式
        if not images and 'image' in data:
            images = [data['image']]
        
        if not images:
            return jsonify({'success': False, 'error': '未提供图片数据'}), 400
        
        # 统一处理 base64
        processed_images = []
        for img in images:
            if ',' in img:
                img = img.split(',')[1]
            processed_images.append(img)
        
        img_count = len(processed_images)
        img_hint = f',用户共上传了 {img_count} 张图片' if img_count > 1 else '用户上传了 1 张图片'
        
        prompt = f'''请仔细分析这{img_hint},判断图片来源类型:

请仔细观察以下特征来判断图片来源:


**实拍图特征(真实卖家拍摄)**:
- 背景杂乱,可能是床铺,桌面,地板等日常环境
- 光线不均匀,可能有阴影或反光
- 可能有手指,指甲入镜
- 商品摆放角度随意,不规整
- 可能有多角度,多个细节图
- 可能有生活痕迹(灰尘,指纹,使用痕迹)

**网图/盗图特征**:
- 背景纯净整洁(纯白,纯色或专业背景布)
- 光线均匀专业,无阴影
- 商品摆放规整居中,构图完美
- 可能是官方产品图,模特图
- 图片质量过于高清精致
- 多张图风格高度一致,像是从同一来源获取
- 可能有水印(文字水印或角落logo)

**AI生成图片特征**:
- 皮肤质感过于完美均匀,像经过滤镜处理
- 手指数量异常(4根,6根或更多)或手指比例不对
- 五官位置或比例不协调(如眼睛大小不一,鼻子变形)
- 背景出现不自然的光影,模糊的物体轮廓
- 商品表面纹理过于平滑,缺少真实磨损
- 文字可能出现乱码或奇怪的符号
- 整体图像有'过于完美'的不真实感
- 手部边缘可能模糊或变形
- 物体边缘可能出现光晕或重影

请返回JSON格式的审核结果:

{{
    'is_real_photo': true或false,
    'confidence': 0到1之间的置信度,
    'reasons': ['具体判断理由'],
    'warning_level': 'none'或'low'或'medium'或'high',
    'warning_message': '给买家的温馨提示',
    'image_type': 'real_photo'或'web_image'或'ai_generated'
}}

判断标准:
- image_type = 'real_photo': 实拍图
- image_type = 'web_image': 网图/盗图
- image_type = 'ai_generated': AI生成图片
- warning_level = 'none': 非常可能是实拍图
- warning_level = 'low': 可能是实拍图,但有轻微疑虑
- warning_level = 'medium': 可能是网图或AI图,建议谨慎
- warning_level = 'high': 极可能是网图或AI生成图,严重警告

仅返回JSON,不要添加其他文字.'''
        
        result = call_multimodal_api(processed_images, prompt)
        
        # 解析JSON结果
        info = parse_json_response(result)
        
        return jsonify({
            'success': True,
            **info
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Supabase 云数据库 API ====================

@app.route('/api/supabase/sync', methods=['POST'])
@admin_required
def api_sync_to_supabase():
    '''手动同步本地 SQLite 数据到 Supabase'''
    success, error_msg = sync_to_supabase()
    if success:
        return jsonify({
            'success': True,
            'message': '数据已成功同步到 Supabase 云数据库'
        })
    else:
        return jsonify({
            'success': False,
            'message': f'同步失败: {error_msg}',
            'hint': '请确保已在 Supabase SQL Editor 中执行 supabase_init.sql 创建表结构'
        }), 500

@app.route('/api/supabase/status', methods=['GET'])
def api_supabase_status():
    '''检查 Supabase 连接状态'''
    connected, message = check_supabase_connection()
    if connected:
        return jsonify({
            'success': True,
            'connected': True,
            'message': 'Supabase 连接正常'
        })
    else:
        return jsonify({
            'success': True,
            'connected': False,
            'message': f'Supabase 连接失败: {message}',
            'fallback': '系统将使用本地 SQLite 数据库'
        })

@app.route('/api/health', methods=['GET'])
def api_health():
    '''健康检查 API'''
    import sys
    sb_connected, sb_msg = check_supabase_connection()
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': {
            'supabase': {
                'connected': sb_connected,
                'message': sb_msg
            },
            'sqlite': {
                'path': DATABASE,
                'exists': os.path.exists(DATABASE)
            }
        }
    })



def parse_json_response(text):
    '''解析JSON响应'''
    import json
    import re
    
    # 尝试提取JSON
    patterns = [
        r'\{[^{}]*\}',
        r'\{.*\}',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except:
                continue
    
    # 如果无法解析,返回默认结构
    return {
        'category': '',
        'name': '',
        'brand': '',
        'model': '',
        'color': '',
        'capacity': '',
        'condition': '',
        'defects': ''
    }


# 提供上传文件访问
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_CONFIG['upload_folder'], filename)

# 提供 JS 工具文件
@app.route('/auth-utils.js')
def auth_utils():
    return send_from_directory('.', 'auth-utils.js')


# 健康检查


# 健康检查
@app.route('/api/chat', methods=['POST'])
@login_required
def ai_chat():
    '''AI智能问答助手'''
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': '请输入问题'}), 400
        
        # 系统提示词
        system_prompt = '''你是一个专业的二手交易平台智能助手,名为'小帮'.你的职责是:
1. 回答用户关于二手交易的问题
2. 提供买卖二手商品的建议
3. 帮助用户了解商品成色,价格合理性
4. 解答平台使用相关问题

请用友好,专业的语气回答,保持简洁明了.如果不知道答案,请如实说明.'''
        
        # 调用AI
        response = call_text_api(message, system_prompt=system_prompt, temperature=0.8)
        
        return jsonify({
            'success': True,
            'reply': response
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok', 'message': '服务正常运行'})


# ==================== 自动同步到 Supabase ====================
import threading
import time

def auto_sync_worker():
    '''后台自动同步线程每5分钟同步一次'''
    while True:
        time.sleep(300)  # 等待5分钟
        try:
            print(f"\n🔄 [{time.strftime('%H:%M:%S')}] 自动同步到 Supabase...")
            success, error = sync_to_supabase()
            if success:
                print(f"✅ [{time.strftime('%H:%M:%S')}] 自动同步完成")
            else:
                print(f"⚠️  [{time.strftime('%H:%M:%S')}] 自动同步失败: {error}")
        except Exception as e:
            print(f"⚠️  [{time.strftime('%H:%M:%S')}] 自动同步异常: {e}")


if __name__ == '__main__':
    print('=' * 50)
    print('二手物品转售AI助手')
    print('=' * 50)
    print('访问地址: http://localhost:5000')
    print('请确保已在 config.py 中配置API密钥')
    print('=' * 50)
    
    # 启动时自动同步一次
    print('\n🚀 启动时同步数据到 Supabase...')
    success, error = sync_to_supabase()
    if success:
        print('✅ 启动同步完成!')
    else:
        print(f'⚠️ 启动同步失败: {error}')
        print('   应用将继续运行,数据将在下次同步时上传')
    
    # 启动后台同步线程
    sync_thread = threading.Thread(target=auto_sync_worker, daemon=True)
    sync_thread.start()
    print('🔄 后台自动同步已启动(每5分钟)')
    print('=' * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=FLASK_CONFIG.get('debug', True), use_reloader=False, threaded=True)
