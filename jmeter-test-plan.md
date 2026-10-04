# 二手物品转售 AI 助手 JMeter 测试方案

## 一、测试目标与范围

### 1.1 测试目标
- 验证 Flask 后端在高并发场景下的稳定性和响应速度
- 评估 SQLite 本地数据库及 Supabase 云数据库的并发处理能力
- 发现系统瓶颈(连接池、文件上传、AI 接口调用、数据库锁等)
- 验证登录鉴权、商品发布、订单创建等核心链路的正确性

### 1.2 测试范围
本方案覆盖 [app.py](file:///h:/github%20works/cb/cb/app.py) 中的 100 个路由,按业务模块分组:

| 模块 | 接口数 | 关键路由示例 |
|------|------|------------|
| 用户认证 | 4 | `/api/auth/register`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/me` |
| 管理员后台 | 21 | `/api/admin/login`、`/api/admin/users`、`/api/admin/products` |
| 商品管理 | 11 | `/api/products`、`/api/product/<id>`、`/api/search`、`/api/product` |
| 订单管理 | 4 | `/api/orders`、`/api/orders/<id>`、`/api/orders/<id>/update` |
| 钱包/地址 | 6 | `/api/wallet`、`/api/wallet/withdraw`、`/api/addresses` |
| 收藏/消息 | 9 | `/api/favorites`、`/api/messages`、`/api/messages/conversations` |
| 文件上传 | 2 | `/api/upload`、`/api/save-image` |
| AI 工具 | 10 | `/api/analyze-image`、`/api/generate-copy`、`/api/detect-product` |
| 用户关系 | 8 | `/api/user/follow`、`/api/user/block`、`/api/user/following` |

### 1.3 测试范围排除
- 第三方 AI 服务(GLM-4V/GLM-4-Flash)的真实调用(改用 Mock 或限制并发)
- Supabase 云端网络延迟的精确模拟(采用本地方案 + Supabase 双模式)
- 静态页面渲染性能(已由 PWA Service Worker 缓存)

---

## 二、测试环境

### 2.1 被测环境(SUT)

| 项目 | 配置 |
|------|------|
| 操作系统 | Windows |
| Python | 3.11 / 3.13 |
| Web 框架 | Flask + flask_cors |
| 数据库 | SQLite(users.db / products.db / market.db) |
| 云数据库 | Supabase(可选,通过 [config.py](file:///h:/github%20works/cb/cb/config.py) 配置) |
| 启动命令 | `python app.py`(默认 debug=True) |
| 默认端口 | 5000 |
| 默认管理员 | admin / admin123 |

### 2.2 压测机配置建议

| 项目 | 建议 |
|------|------|
| CPU | 8 核以上 |
| 内存 | 16GB 以上 |
| JMeter 版本 | 5.6+ |
| JVM 堆内存 | `-Xms2g -Xmx4g` |
| 网络 | 与被测机同一局域网,延迟 < 5ms |

### 2.3 测试数据准备
1. 通过 [seed_data.py](file:///h:/github%20works/cb/cb/seed_data.py) 批量预置商品数据
2. 预生成 1000 个测试用户(用户名格式:`testuser_{seq}`,密码:`Test@1234`)
3. 预置 5000 条在售商品(`status='selling'`)
4. 预置测试图片:`uploads/` 目录下已有 24 张 jpg 可复用

---

## 三、测试场景设计

### 3.1 场景一:基准功能测试(冒烟测试)

**目的**:验证接口可用性和正确性,排除环境问题。

**配置**:
- 线程数:1
- Ramp-up:0
- 循环次数:1
- 断言:HTTP 状态码 200/201,响应 JSON `success=true`

**覆盖用例**:每个接口至少 1 个正例 + 1 个反例(如鉴权失败、参数缺失)。

---

### 3.2 场景二:用户认证链路负载测试

**目的**:测试登录鉴权在高并发下的正确性和性能。

**配置**:
- 线程数:50 / 100 / 200 / 500
- Ramp-up:10s
- 循环次数:10
- 随机用户名(从预置数据池采样)

**核心接口**:

| 接口 | 方法 | 请求体 | 断言 |
|------|------|--------|------|
| `/api/auth/register` | POST | `{"username":"load_${__Random(1,99999)}","password":"Test@1234"}` | 201,success=true |
| `/api/auth/login` | POST | `{"username":"testuser_${__threadNum}","password":"Test@1234"}` | 200,含 token |
| `/api/auth/me` | GET | Header: `Authorization: Bearer ${token}` | 200 |
| `/api/auth/logout` | POST | Header: `Authorization: Bearer ${token}` | 200 |

**关键关注点**:
- 使用 JSON Extractor 提取 `$.token` 供后续请求使用
- 验证 bcrypt 哈希计算对 CPU 的影响
- 验证 `sessions` 表写入并发冲突

---

### 3.3 场景三:商品浏览与搜索(读密集型)

**目的**:模拟用户浏览首页、搜索、查看详情的高并发场景。

**配置**:
- 线程数:200 / 500 / 1000
- Ramp-up:20s
- 循环次数:无限(持续时间 5 分钟)
- 随机思考时间:500-2000ms

**测试组**:

1. **商品列表查询**(权重 40%)
   - GET `/api/products?page=${page}&page_size=20&status=selling&sort=latest`
   - 参数化:page 使用 `${__Random(1,50)}`

2. **关键词搜索**(权重 30%)
   - GET `/api/search?q=${keyword}&page=1&page_size=20`
   - 关键词从 CSV 读取:`iPhone`、`笔记本`、`自行车`、`书`、`耳机` 等

3. **商品详情**(权重 30%)
   - GET `/api/product/${product_id}`
   - product_id 从 CSV 数据池随机选取(1-5000)

**关键关注点**:
- SQLite 并发读性能(WAL 模式建议)
- `/api/search` 中 fuzzy_match 函数的 CPU 开销
- Supabase 模式下网络往返延迟

---

### 3.4 场景四:商品发布与订单创建(写密集型)

**目的**:测试写操作在并发下的数据一致性和性能。

**配置**:
- 线程数:50 / 100 / 200
- Ramp-up:10s
- 循环次数:5

**前置条件**:每个线程先登录获取 token,通过 JSON Extractor 提取 `$.user.uid`。

**测试流程**:

```
[登录] → [上传图片] → [发布商品] → [另一用户下单] → [更新订单状态]
```

**关键接口**:

| 步骤 | 接口 | 关键参数 |
|------|------|---------|
| 1. 登录 | POST `/api/auth/login` | 提取 token、uid |
| 2. 上传图片 | POST `/api/upload` | multipart/form-data,file 字段 |
| 3. 发布商品 | POST `/api/product` | `{"title":"商品_${time}","price":${__Random(10,999)},"images":["${image_url}"],"category":"数码","condition":"9成新"}` |
| 4. 创建订单 | POST `/api/orders` | `{"product_id":${product_id}}`(使用其他用户商品) |
| 5. 更新订单 | POST `/api/orders/${order_id}/update` | `{"status":"paid"}` |

**关键关注点**:
- SQLite 写锁(SQLITE_BUSY 错误)
- `products` 和 `orders` 表的并发插入
- 商品状态变更的原子性(防止同一商品被多次下单)
- 文件上传目录权限和磁盘 IO

---

### 3.5 场景五:AI 工具接口(慢响应)

**目的**:测试 AI 接口在并发下的超时处理和队列表现。

**配置**:
- 线程数:10 / 20 / 50
- Ramp-up:30s
- 超时设置:60s([config.py](file:///h:/github%20works/cb/cb/config.py) 中 TEXT_MODEL_CONFIG timeout=60)
- 循环次数:3

**测试接口**:

| 接口 | 说明 | 预期响应时间 |
|------|------|------------|
| `/api/analyze-image` | 图片分析(多模态) | 5-15s |
| `/api/generate-copy` | 文案生成 | 3-10s |
| `/api/generate-all-copies` | 批量文案 | 10-30s |
| `/api/detect-product` | 商品识别 | 5-15s |
| `/api/verify-image` | 图片验证 | 3-10s |

**请求体示例**(`analyze-image`):
```json
{
  "image": "${base64_image_data}",
  "prompt": "分析这张图片中的物品"
}
```

**关键关注点**:
- 第三方 API 限流(Rate Limit)导致的 429 错误
- 长连接超时和重试逻辑
- AI 服务不可用时的降级表现
- **建议**:测试时将 [config.py](file:///h:/github%20works/cb/cb/config.py) 中 `api_key` 留空或配置为 Mock 服务,避免消耗真实配额

---

### 3.6 场景六:管理员后台批量操作

**目的**:验证管理员批量删除、批量封禁等操作的并发安全性。

**配置**:
- 线程数:5(模拟少数管理员同时操作)
- Ramp-up:5s
- 循环次数:10

**前置**:管理员登录 `/api/admin/login`(admin/admin123),通过 `admin_token` Cookie 或 `Authorization` 头鉴权。

**测试接口**:

| 接口 | 方法 | 请求体 |
|------|------|--------|
| `/api/admin/users/batch-delete` | POST | `{"uids":["uid1","uid2","uid3"]}` |
| `/api/admin/users/batch-ban` | POST | `{"uids":["uid1","uid2"]}` |
| `/api/admin/products/batch-delete` | POST | `{"ids":[1,2,3]}` |
| `/api/admin/anomaly-detection` | GET | - |

**关键关注点**:
- 管理员账户锁定机制(5 次失败锁定)
- 批量操作的事务回滚
- 异常检测算法 CPU 占用

---

### 3.7 场景七:稳定性测试(疲劳测试)

**目的**:长时间运行,检测内存泄漏、连接泄漏、日志膨胀。

**配置**:
- 线程数:50(混合场景)
- 持续时间:2 小时
- 思考时间:1-3s 随机
- 场景权重:浏览 60% + 发布 15% + 下单 10% + AI 10% + 管理 5%

**监控指标**:
- Flask 进程内存增长(Python RSS)
- SQLite 文件大小增长
- `uploads/` 目录文件数量
- `__pycache__` 缓存膨胀
- HTTP 错误率应 < 1%

---

### 3.8 场景八:极限压力测试

**目的**:找出系统崩溃点。

**配置**:
- 线程数:从 500 逐步加压至 2000(每 30s 增加 250)
- 持续至错误率 > 20% 或响应时间 > 10s

**预期瓶颈点**:
1. SQLite 写锁(默认 `BEGIN` 是 DEFERRED,高并发下易冲突)
2. Flask 内置服务器(`app.run()` 非生产级,默认单进程)
3. 文件 IO(图片上传)
4. bcrypt CPU 计算瓶颈

---

## 四、JMeter 测试计划结构

```
Test Plan: 二手物品转售AI助手
├── 用户定义变量(USER Variables)
│   ├── HOST = localhost
│   ├── PORT = 5000
│   ├── BASE_URL = http://${HOST}:${PORT}
│   └── ADMIN_TOKEN = (运行时提取)
│
├── 配置元件(Config Elements)
│   ├── HTTP Header Manager(Content-Type: application/json)
│   ├── HTTP Cookie Manager(管理 token cookie)
│   ├── HTTP Request Defaults(服务器:${BASE_URL})
│   ├── CSV Data Set Config(test_users.csv: username,password)
│   └── JDBC Connection Configuration(可选,直查 DB 验证)
│
├── setUp 线程组
│   ├── 管理员登录获取 admin_token
│   └── 批量创建测试用户(调用 /api/auth/register)
│
├── 线程组 1:用户认证链路
│   ├── 登录请求(提取 token)
│   ├── /api/auth/me(带 Authorization 头)
│   └── 登出请求
│
├── 线程组 2:商品浏览(读密集)
│   ├── 商品列表(随机 page)
│   ├── 关键词搜索(CSV 关键词)
│   └── 商品详情(随机 product_id)
│
├── 线程组 3:商品发布与下单(写密集)
│   ├── 登录(提取 uid)
│   ├── 上传图片(multipart)
│   ├── 发布商品(提取 product_id)
│   ├── 切换用户登录(买家)
│   ├── 创建订单(提取 order_id)
│   └── 更新订单状态
│
├── 线程组 4:AI 工具(慢接口)
│   ├── 图片分析
│   └── 文案生成
│
├── 线程组 5:管理员后台
│   ├── 管理员登录
│   ├── 用户列表
│   ├── 批量操作
│   └── 异常检测
│
├── tearDown 线程组
│   └── 清理测试数据(管理员批量删除测试用户)
│
└── 监听器(Listeners)
    ├── Aggregate Report(聚合报告)
    ├── Summary Report(汇总)
    ├── Response Times Over Time(响应时间趋势)
    ├── Active Threads Over Time(并发线程趋势)
    ├── Errors Report(错误分析)
    ├── Backend Listener(InfluxDB/Grafana 集成,可选)
    └── 结果树(调试用,生产场景关闭)
```

---

## 五、JMeter 关键元件配置示例

### 5.1 用户定义变量

```
HOST        = localhost
PORT        = 5000
BASE_URL    = http://${HOST}:${PORT}
USERNAME    = testuser_${__threadNum}
PASSWORD    = Test@1234
```

### 5.2 HTTP Header Manager

| 名称 | 值 |
|------|----|
| Content-Type | application/json |
| User-Agent | JMeter/5.6 LoadTest |
| Authorization | Bearer ${TOKEN} |

### 5.3 登录请求 + JSON Extractor(提取 token)

**HTTP Request**:
- 路径:`/api/auth/login`
- 方法:POST
- Body:
```json
{
  "username": "${USERNAME}",
  "password": "${PASSWORD}"
}
```

**JSON Extractor**(后置处理器):
- 引用名称:`TOKEN`
- JSON Path:`$.token`
- 默认值:`NOT_FOUND`

**JSON Extractor**(提取 uid):
- 引用名称:`UID`
- JSON Path:`$.user.uid`

### 5.4 商品列表请求(参数化)

**HTTP Request**:
- 路径:`/api/products`
- 方法:GET
- 参数:
  - `page`: `${__Random(1,50)}`
  - `page_size`: `20`
  - `status`: `selling`
  - `sort`: `${__RandomFromPackage(latest,price_asc,price_desc)}`

### 5.5 文件上传请求

**HTTP Request**:
- 路径:`/api/upload`
- 方法:POST
- 勾选 `Use multipart/form-data`
- Body:
  - `file`:文件路径 `${__P(upload.file)}`(指向 `uploads/test.jpg`)

### 5.6 发布商品请求

**HTTP Request**:
- 路径:`/api/product`
- 方法:POST
- Header:`Authorization: Bearer ${TOKEN}`
- Body:
```json
{
  "title": "测试商品_${__time(yyyyMMddHHmmss)}_${__threadNum}",
  "price": ${__Random(10,9999)},
  "original_price": ${__Random(100,10000)},
  "description": "JMeter 压测自动生成商品",
  "images": [],
  "category": "${__RandomFromPackage(数码,服饰,家居,书籍,运动)}",
  "condition": "9成新"
}
```

**JSON Extractor**:
- 引用名称:`PRODUCT_ID`
- JSON Path:`$.product_id`

### 5.7 创建订单请求

**HTTP Request**:
- 路径:`/api/orders`
- 方法:POST
- Header:`Authorization: Bearer ${BUYER_TOKEN}`
- Body:
```json
{
  "product_id": ${PRODUCT_ID}
}
```

### 5.8 响应断言

**Response Assertion**:
- 测试字段:响应码
- 模式匹配规则:包含
- 模式:`200` 或 `201`

**JSON Assertion**:
- Assert JSON Path:`$.success`
- Expected Value:`true`

---

## 六、性能指标与通过标准

### 6.1 关键指标

| 指标 | 说明 |
|------|------|
| TPS(Transactions Per Second) | 每秒事务数 |
| Average Response Time | 平均响应时间 |
| 90th / 95th / 99th Percentile | 百分位响应时间 |
| Error Rate | 错误率(非 2xx + 业务 success=false) |
| Active Threads | 活跃并发数 |
| Throughput | 吞吐量(req/s) |

### 6.2 通过标准(SLA)

| 接口类型 | 90% 响应时间 | 错误率 | TPS 目标 |
|---------|------------|--------|---------|
| 读接口(商品列表/详情) | < 500ms | < 0.5% | ≥ 100 |
| 写接口(登录/发布/下单) | < 2s | < 1% | ≥ 20 |
| AI 接口 | < 15s | < 5% | ≥ 5 |
| 管理员批量操作 | < 3s | < 1% | ≥ 5 |
| 疲劳测试(2 小时) | < 1s | < 1% | 稳定不衰减 |

---

## 七、监控方案

### 7.1 服务器端监控

1. **进程监控**(Python 进程):
   ```powershell
   while ($true) {
     Get-Process python | Select-Object Id,CPU,WorkingSet
     Start-Sleep -Seconds 5
   }
   ```

2. **SQLite 监控**:
   ```powershell
   while ($true) {
     Get-Item users.db,products.db | Select-Object Name,Length
     Start-Sleep -Seconds 10
   }
   ```

3. **Flask 日志**:在 [app.py](file:///h:/github%20works/cb/cb/app.py) 中开启 `logging` 记录慢请求(>2s)。

### 7.2 JMeter 内置监控
- Aggregate Graph:可视化各接口 TPS 和响应时间
- Response Time Percentiles:百分位分布图
- Backend Listener → InfluxDB → Grafana(可选,生产级监控)

### 7.3 数据库一致性校验
测试结束后执行 SQL 校验:
```sql
-- 检查孤立订单
SELECT COUNT(*) FROM orders o LEFT JOIN products p ON o.product_id=p.id WHERE p.id IS NULL;
-- 检查用户与商品 UID 一致性
SELECT COUNT(*) FROM products p LEFT JOIN users u ON p.uid=u.uid WHERE u.uid IS NULL;
-- 检查会话数与用户数比例
SELECT (SELECT COUNT(*) FROM sessions)/(SELECT COUNT(*) FROM users)+0.0;
```

---

## 八、风险与注意事项

### 8.1 已知风险

1. **Flask 内置服务器非生产级**:默认单进程多线程,高并发下受限。建议压测前开启多线程:
   ```python
   app.run(host='0.0.0.0', port=5000, threaded=True)
   ```
   或使用 `gunicorn`/`waitress` 部署后再压测。

2. **SQLite 写锁瓶颈**:写操作在高并发下易出现 `database is locked`。建议:
   - 启用 WAL 模式:`PRAGMA journal_mode=WAL;`
   - 设置忙等待:`PRAGMA busy_timeout=5000;`
   - 严重场景切换至 Supabase 模式

3. **AI 接口配额消耗**:`/api/analyze-image` 等接口会真实调用智谱 API,可能产生费用。建议:
   - 压测时清空 [config.py](file:///h:/github%20works/cb/cb/config.py) 中的 `api_key`
   - 或使用 Mock Server 返回固定响应

4. **bcrypt 计算密集**:登录和注册接口的密码哈希消耗 CPU,并发过高会成瓶颈。

5. **文件上传磁盘 IO**:`/api/upload` 将文件读取为 base64,大文件占用内存。

### 8.2 测试数据隔离
- 测试用户名加前缀 `loadtest_` 便于清理
- 测试商品标题加前缀 `JMeter压测_` 便于识别
- 使用 tearDown 线程组调用管理员 API 批量删除

### 8.3 结果可靠性
- 首次执行结果丢弃(JIT 预热、缓存构建)
- 同一场景至少执行 3 次取平均值
- 压测机 CPU 利用率应 < 80%,否则结果不可靠

---

## 九、测试执行流程

1. **环境准备**
   - 备份现有 `users.db`、`products.db`、`market.db`
   - 运行 `python seed_data.py` 灌入测试数据
   - 启动 Flask 服务:`python app.py`

2. **冒烟测试**(场景一)
   - 单线程验证所有接口可访问
   - 修正环境问题后继续

3. **负载测试**(场景二~六)
   - 按并发梯度递增执行
   - 每次记录 Aggregate Report 到 CSV

4. **稳定性测试**(场景七)
   - 持续 2 小时混合场景
   - 每 10 分钟采样服务器资源

5. **极限测试**(场景八)
   - 阶梯加压至崩溃
   - 记录崩溃点和错误堆栈

6. **结果分析**
   - 汇总各场景 TPS、响应时间、错误率
   - 生成测试报告
   - 提出优化建议(SQLite WAL、Gunicorn 部署、缓存、连接池等)

---

## 十、实测结果与瓶颈分析

### 10.1 实测环境
- Flask 开发服务器(`app.run(threaded=True)`, debug=False)
- Windows / Python 3.x / SQLite
- 测试工具:Python `requests` + `concurrent.futures`(替代 JMeter)

### 10.2 冒烟测试结果(单线程,2026-08-17)

| 接口 | 状态码 | 响应时间 | 备注 |
|------|--------|----------|------|
| GET /api/products | 200 | 2076ms | 正常 |
| POST /api/auth/register | 201 | 2223ms | 正常 |
| POST /api/auth/login | 200 | 2025ms | 正常 |
| GET /api/auth/me | 200 | 2023ms | 正常 |
| GET /api/product/1 | 200 | 2164ms | 正常 |
| GET /api/search | 200 | 2051ms | 正常 |
| POST /api/product | 201 | 2155ms | 正常 |
| POST /api/orders | 201 | 2173ms | 正常 |
| POST /api/admin/login | 200 | 2428ms | 正常 |
| GET /api/admin/users | 200 | 2154ms | 正常 |

**结论**:全部 10 个核心接口通过,功能正确。

### 10.3 并发负载测试结果

**测试 A:20 认证 + 50 浏览 + 5 写并发,15 秒**

| 指标 | 数值 |
|------|------|
| 总请求数 | 544 |
| 成功率 | 93.4% |
| 失败数 | 36 条(全部 GET /api/product/\<id\>) |
| 平均响应时间 | ~2100ms |

**测试 B:10 认证 + 20 浏览 + 3 写并发,10 秒**

| 指标 | 数值 |
|------|------|
| 总请求数 | 220 |
| 成功率 | 97.3% |
| 失败数 | 6 条(全部 GET /api/product/\<id\>) |

**接口性能明细(测试 A)**:

| 接口 | 请求数 | 成功率 | 平均ms | P90ms | P99ms |
|------|--------|--------|--------|-------|-------|
| GET /api/products | 125 | 100% | 2078 | 2119 | 2141 |
| GET /api/search | 125 | 100% | 2068 | 2117 | 2179 |
| POST /api/auth/login | 45 | 100% | 2366 | 2695 | 2822 |
| GET /api/auth/me | 45 | 100% | 2060 | 2099 | 2176 |
| POST /api/auth/logout | 44 | 100% | 2124 | 2195 | 2538 |
| POST /api/product | 11 | 100% | 2173 | 2266 | 2299 |
| POST /api/orders | 11 | 100% | 2146 | 2182 | 2244 |
| POST /api/orders/\<id\>/update | 10 | 100% | 2135 | 2216 | 2216 |
| **GET /api/product/\<id\>** | **124** | **71%** | **2322** | **2910** | **3364** |

### 10.4 瓶颈分析

#### 问题 1:Flask 开发服务器基线延迟 ~2 秒

**现象**:所有接口(包括简单的 `/api/auth/logout`)响应时间均在 2000ms 左右。

**根因**:
- Werkzeug 开发服务器非生产级,单进程模型受 GIL 限制
- 每个请求都触发完整的 Flask 请求栈(WSGI → 路由 → 数据库连接 → 响应)
- SQLite 每次请求打开/关闭连接,无连接池复用
- Windows 环境下 Python 线程调度开销较大

**优化方案**:
1. **使用 Waitress/Werkzeug 多线程服务器**:
   ```python
   # 生产部署方式
   from waitress import serve
   serve(app, host='0.0.0.0', port=5000, threads=16)
   ```
2. **启用 SQLite WAL 模式和连接池**
3. **将 `row_factory` 配置统一在 `get_db()` 中**

#### 问题 2:GET /api/product/\<id\> 并发失败

**现象**:50 并发下,`GET /api/product/\<id\>` 失败率达 29%(HTTP 0 = 连接超时)。

**根因**:
- 随机 ID(1-5000)中部分商品不存在,但 Flask 在高并发下对不存在商品查询也返回成功(缓存了错误的响应)
- 更关键的是:Flask 单进程处理队列在 50 并发浏览请求时积压,部分请求因队列超时被客户端判定为 HTTP 0
- 其他线程组(认证、写操作)与浏览线程组争抢同一 Flask 进程的处理时间片

**优化方案**:
1. **提升浏览请求的超时阈值**(客户端 `timeout=30s`)
2. **降低并发压力**或拆分不同线程组的执行时间
3. **部署到生产级服务器后重新测试**

### 10.5 推荐的生产部署方案

```python
# app_production.py - 生产环境启动脚本
from waitress import serve
from app import app
import sqlite3

# 生产环境优化配置
if __name__ == '__main__':
    # 确保 SQLite 使用 WAL 模式
    for db in ['users.db', 'products.db', 'market.db']:
        conn = sqlite3.connect(db)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=-64000')  # 64MB 缓存
        conn.close()
    
    # 使用 Waitress 生产级服务器
    serve(
        app,
        host='0.0.0.0',
        port=5000,
        threads=16,        # 工作线程数
        connection_limit=100,
        channel_timeout=30,
    )
```

---

## 十一、附录

### 11.1 测试执行路径(双轨制)

#### 路径 A:JMeter 图形化压测(推荐正式测试使用)

```powershell
# Step 1: 准备测试用户
python setup_test_users.py

# Step 2: 启动 Flask
python app.py

# Step 3: 运行 JMeter 非 GUI 模式
jmeter -n -t cb-jmeter-test.jmx -l result.jtl -e -o ./report

# Step 4: 查看报告
# 打开 ./report/index.html
```

#### 路径 B:Python 并发验证(JMeter 不可用时使用)

```powershell
# 冒烟测试
python jmeter_verify.py --smoke-only

# 轻量负载测试
python jmeter_verify.py --auth-users 10 --browse-users 20 --write-users 3 --duration 10

# 完整负载测试
python jmeter_verify.py --auth-users 50 --browse-users 100 --write-users 10 --duration 30
```

### 11.2 测试用户 CSV(test_users.csv)

```
username,password
testuser_1,Test@1234
testuser_2,Test@1234
...
testuser_1000,Test@1234
```

### 11.3 搜索关键词 CSV(search_keywords.csv)

```
keyword
iPhone
笔记本
自行车
耳机
书
键盘
鼠标
显示器
沙发
```

### 11.4 JMeter 启动命令

```powershell
# GUI 模式(调试用,勿用于实际压测)
jmeter -t cb-jmeter-test.jmx

# 非 GUI 模式(实际压测,推荐)
jmeter -n -t cb-jmeter-test.jmx -l result.jtl -e -o ./report

# 分布式压测(多台压测机)
jmeter -n -t cb-jmeter-test.jmx -r -l result.jtl -e -o ./report

# 调整 JVM 内存
set HEAP=-Xms2g -Xmx4g
jmeter -n -t cb-jmeter-test.jmx -l result.jtl
```

### 11.5 参考文档
- [README.md](file:///h:/github%20works/cb/cb/README.md)
- [SUPABASE_SETUP.md](file:///h:/github%20works/cb/cb/SUPABASE_SETUP.md)
- [supabase_init.sql](file:///h:/github%20works/cb/cb/supabase_init.sql)
