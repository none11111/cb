import sqlite3
import hashlib
import secrets
from datetime import datetime

DATABASE = 'users.db'

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def seed_products():
    """填充初始商品数据"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 检查是否已有商品数据
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] > 0:
        print(f'Already have {cursor.fetchone()[0]} products, skipping...')
        conn.close()
        return
    
    # 创建演示卖家
    seller_uids = ['U00000001', 'U00000002', 'U00000003', 'U00000004']
    for i, uid in enumerate(seller_uids):
        cursor.execute('''INSERT OR IGNORE INTO users (uid, username, password_hash, created_at)
                          VALUES (?, ?, ?, ?)''', 
                      (uid, f'Seller{i+1}', hash_password('demo123'), datetime.now().isoformat()))
    
    # 初始商品数据
    products = [
        # ========== 数码类 - iPhone系列 ==========
        ('U00000001', 'iPhone 14 Pro Max 256G 暗紫色 国行', 5999, 8999, '国行正品，暗紫色256G，全套配件齐全，无划痕无磕碰。', 
         '["https://picsum.photos/400/500?1"]', '数码', '9成新', 'selling', '2026-04-01T10:00:00'),
        ('U00000002', 'iPhone 14 Pro Max 256G 金色 国行', 5800, 8999, '金色256G，屏幕贴膜戴套，无任何划痕，电池健康度98%。', 
         '["https://picsum.photos/400/500?14"]', '数码', '9成新', 'selling', '2026-04-02T11:00:00'),
        ('U00000003', 'iPhone 14 Pro Max 128G 银色 美版', 4500, 8999, '美版单卡，全原无修，屏幕轻微使用痕迹，其他完好。', 
         '["https://picsum.photos/400/500?15"]', '数码', '8成新', 'selling', '2026-04-03T09:00:00'),
        ('U00000001', 'iPhone 15 Pro 256G 钛金属', 6999, 9999, '全新未拆封，钛金属原色，官方在保。', 
         '["https://picsum.photos/400/500?16"]', '数码', '全新', 'selling', '2026-04-04T15:00:00'),
        ('U00000002', 'iPhone 15 Pro 128G 蓝色钛金属', 6200, 9999, '在保到年底，轻微使用痕迹，配件齐全。', 
         '["https://picsum.photos/400/500?17"]', '数码', '9成新', 'selling', '2026-04-05T10:00:00'),
        
        # ========== 数码类 - AirPods系列 ==========
        ('U00000001', 'AirPods Pro 2代 全新未拆封', 1580, 1899, '全新未拆封，保证正品，带发票。', 
         '["https://picsum.photos/400/300?2"]', '数码', '全新', 'selling', '2026-04-05T14:30:00'),
        ('U00000003', 'AirPods Pro 2代 使用3个月', 1350, 1899, '国行在保，9月购入，充电盒轻微划痕，耳机无任何问题。', 
         '["https://picsum.photos/400/300?18"]', '数码', '9成新', 'selling', '2026-04-06T16:00:00'),
        ('U00000004', 'AirPods 3代 全新未拆封', 980, 1399, '全新未拆封，国行正品，假一赔十。', 
         '["https://picsum.photos/400/300?19"]', '数码', '全新', 'selling', '2026-04-07T11:00:00'),
        
        # ========== 数码类 - 相机系列 ==========
        ('U00000001', '索尼 A7M4 全画幅微单相机', 13500, 16999, '索尼A7M4，快门数不到5000，箱说全，送原装电池一块。', 
         '["https://picsum.photos/400/400?4"]', '数码', '9成新', 'selling', '2026-04-10T16:45:00'),
        ('U00000002', '索尼 A7M4 全画幅微单 单机身', 12800, 16999, '单机无镜头，快门数3500，机身有轻微使用痕迹，功能完美。', 
         '["https://picsum.photos/400/400?20"]', '数码', '9成新', 'selling', '2026-04-11T14:00:00'),
        ('U00000003', '佳能 R6 Mark II 微单相机', 14500, 18599, '佳能R6II，12月购入，快门数2000，全套配件，发票齐全。', 
         '["https://picsum.photos/400/400?21"]', '数码', '9成新', 'selling', '2026-04-12T09:30:00'),
        ('U00000004', '富士 X-T5 微单相机 银色', 10200, 11990, '富士XT5，樱花粉色，16-80套机，配件全，在保。', 
         '["https://picsum.photos/400/400?22"]', '数码', '9成新', 'selling', '2026-04-13T11:00:00'),
        
        # ========== 数码类 - 游戏机 ==========
        ('U00000001', '任天堂 Switch OLED 日版', 1850, 2599, '日版OLED白色，双人成行+马里奥派对卡带，贴膜戴套使用。', 
         '["https://picsum.photos/400/350?5"]', '数码', '8成新', 'selling', '2026-04-12T11:20:00'),
        ('U00000002', '任天堂 Switch OLED 港版', 1780, 2599, '港版OLED黑色，附赠Pro手柄，贴膜戴套，无任何问题。', 
         '["https://picsum.photos/400/350?23"]', '数码', '8成新', 'selling', '2026-04-14T15:00:00'),
        ('U00000003', '索尼 PS5 光驱版', 2800, 3899, 'PS5光驱版，附带2个手柄，2025年6月购入，箱说全。', 
         '["https://picsum.photos/400/350?24"]', '数码', '9成新', 'selling', '2026-04-15T10:00:00'),
        ('U00000004', '微软 Xbox Series X', 3200, 4499, 'Xbox Series X日版，2025年3月购入，配件齐全，手柄2个。', 
         '["https://picsum.photos/400/350?25"]', '数码', '9成新', 'selling', '2026-04-16T14:00:00'),
        
        # ========== 家居类 ==========
        ('U00000001', '戴森吹风机 HD03 红色限定版', 2200, 2990, '红色限定版，使用不到10次，功能正常，配件齐全。', 
         '["https://picsum.photos/400/600?3"]', '家居', '9成新', 'selling', '2026-03-20T09:15:00'),
        ('U00000002', '戴森吹风机 Supersonic HD08', 2350, 3299, '国行正品，2025年购入，使用次数不超过20次。', 
         '["https://picsum.photos/400/600?26"]', '家居', '9成新', 'selling', '2026-04-17T11:00:00'),
        ('U00000001', '小米扫地机器人 3C', 850, 1499, '功能正常，扫拖一体，配件齐全，清洗过水箱。', 
         '["https://picsum.photos/400/420?9"]', '家居', '8成新', 'selling', '2026-04-20T15:10:00'),
        ('U00000003', '科沃斯 T20S PRO 扫地机器人', 2200, 4599, '科沃斯旗舰款，扫拖一体，自动集尘，自动洗拖布。', 
         '["https://picsum.photos/400/420?27"]', '家居', '9成新', 'selling', '2026-04-18T10:00:00'),
        ('U00000004', '追觅 W10S PRO 扫地机器人', 1800, 3999, '扫拖洗烘一体，自动清洗拖布，激光导航，功能正常。', 
         '["https://picsum.photos/400/420?28"]', '家居', '9成新', 'selling', '2026-04-19T14:00:00'),
        ('U00000001', '九阳破壁机 Y1', 480, 899, '研磨效果很好，清洗方便，功能完好无损。', 
         '["https://picsum.photos/400/520?12"]', '家居', '8成新', 'selling', '2026-04-28T14:00:00'),
        ('U00000002', '美的破壁机 MJ-PB80S7', 350, 799, '8重降噪，低音破壁，冷热双杯，功能完好。', 
         '["https://picsum.photos/400/520?29"]', '家居', '9成新', 'selling', '2026-04-21T11:00:00'),
        
        # ========== 服装类 ==========
        ('U00000001', 'AJ1 芝加哥复刻 42码', 2800, 1399, '正品过验，保真！穿过两次，鞋底几乎无磨损。', 
         '["https://picsum.photos/400/380?8"]', '服装', '9成新', 'selling', '2026-04-18T19:00:00'),
        ('U00000002', 'AJ1 芝加哥复刻 42.5码', 2600, 1399, '正品过验，穿着次数不超过5次，鞋面无折痕，鞋底微磨损。', 
         '["https://picsum.photos/400/380?30"]', '服装', '8成新', 'selling', '2026-04-22T15:00:00'),
        ('U00000003', 'Nike Dunk Low 熊猫 42码', 650, 1099, '熊猫Dunk low，2025年双十一购入，穿了不到10次。', 
         '["https://picsum.photos/400/380?31"]', '服装', '9成新', 'selling', '2026-04-23T10:00:00'),
        ('U00000004', 'Adidas Yeezy 350 灰橙 43码', 1200, 1899, 'Yeezy 350灰橙配色，侃爷同款，穿了两三次。', 
         '["https://picsum.photos/400/380?32"]', '服装', '9成新', 'selling', '2026-04-24T11:00:00'),
        
        # ========== 美妆类 ==========
        ('U00000001', 'SK-II 神仙水 230ml', 680, 1540, '日上购入，有购买记录，用了一点点，可验货。', 
         '["https://picsum.photos/400/500?7"]', '美妆', '9成新', 'selling', '2026-03-15T20:30:00'),
        ('U00000002', 'SK-II 小灯泡 50ml', 480, 1040, '淡斑美白精华，用了不到三分之一，有购买记录。', 
         '["https://picsum.photos/400/500?33"]', '美妆', '9成新', 'selling', '2026-04-25T14:00:00'),
        ('U00000003', 'La Mer 经典面霜 60ml', 1200, 2800, '海蓝之谜经典面霜，仅试用过一次，不适合我的肤质。', 
         '["https://picsum.photos/400/500?34"]', '美妆', '9成新', 'selling', '2026-04-26T10:00:00'),
        
        # ========== 其他类 ==========
        ('U00000001', 'LAMY 恒星系列 钢笔套装', 380, 680, '银色F尖，写感顺滑，笔尖几乎无磨损，配件齐全。', 
         '["https://picsum.photos/400/450?6"]', '其他', '9成新', 'sold', '2026-03-28T08:00:00'),
        ('U00000001', '乐高星球大战 千年隼', 3200, 5999, '全新未拆封，绝版好价，顺丰保价发货。', 
         '["https://picsum.photos/400/350?11"]', '其他', '全新', 'selling', '2026-04-25T09:30:00'),
        ('U00000002', '乐高 保时捷 911 RSR', 1800, 3599, '全新未拆封，盒况完美，编号完整。', 
         '["https://picsum.photos/400/350?35"]', '其他', '全新', 'selling', '2026-04-27T11:00:00'),
        ('U00000003', 'Apple Watch S9 45mm GPS版', 2600, 3299, 'Apple Watch S9星光色，9月购入，配件齐全。', 
         '["https://picsum.photos/400/450?36"]', '数码', '9成新', 'selling', '2026-04-28T09:00:00'),
        ('U00000004', 'Apple Watch Ultra 2 钛金属', 4200, 5999, 'Ultra 2钛金属原色，2025年购入，在保，配件全。', 
         '["https://picsum.photos/400/450?37"]', '数码', '9成新', 'selling', '2026-04-29T10:00:00'),
        
        # ========== 已售/下架商品 ==========
        ('U00000002', '富士拍立得 mini90', 950, 1280, '黑色限量版，配件有电池、充电线、相纸5张，包装齐全。', 
         '["https://picsum.photos/400/480?10"]', '数码', '9成新', 'sold', '2026-04-22T12:00:00'),
    ]
    
    cursor.executemany('''INSERT INTO products 
        (uid, title, price, original_price, description, images, category, condition, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', products)
    
    conn.commit()
    conn.close()
    print(f'Seeded {len(products)} products successfully!')

if __name__ == '__main__':
    seed_products()
    
    # Verify
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM products')
    print(f'Total products in DB: {cursor.fetchone()[0]}')
    
    cursor.execute("SELECT category, COUNT(*) FROM products WHERE status='selling' GROUP BY category")
    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]} products')
    
    cursor.execute("SELECT id, title, price FROM products WHERE title LIKE '%iPhone%' AND status='selling'")
    print('\n iPhone products:')
    for row in cursor.fetchall():
        print(f'  ID:{row[0]} - {row[1]} - {row[2]}')
    
    cursor.execute("SELECT id, title, price FROM products WHERE (title LIKE '%索尼%' OR title LIKE '%A7%') AND status='selling'")
    print('\n Camera products:')
    for row in cursor.fetchall():
        print(f'  ID:{row[0]} - {row[1]} - {row[2]}')
    
    conn.close()
