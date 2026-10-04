# -*- coding: utf-8 -*-
"""
二手物品转售 AI 助手 - JMeter 测试方案 Python 验证脚本
功能:模拟 JMeter 测试计划中的 5 个线程组,对 Flask 后端进行负载测试
使用方法:
    python jmeter_verify.py              # 默认配置
    python jmeter_verify.py --host localhost --port 5000
    python jmeter_verify.py --users 20 --duration 30    # 自定义并发数和持续时间
"""

import requests
import concurrent.futures
import time
import random
import json
import argparse
import statistics
import threading
from collections import defaultdict
from datetime import datetime

# ============ 配置 ============
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_BASE_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
TEST_PASSWORD = "Test@1234"

# 测试结果存储
results = []
results_lock = threading.Lock()
errors = defaultdict(list)

# ============ 工具函数 ============
def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def record_result(name, status_code, response_time, success, error_msg=None):
    with results_lock:
        results.append({
            "name": name,
            "status_code": status_code,
            "response_time": response_time,
            "success": success,
            "error": error_msg,
            "timestamp": time.time()
        })

def make_request(method, url, **kwargs):
    """发送请求并记录结果"""
    start = time.time()
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30, **kwargs)
        elif method == "POST":
            resp = requests.post(url, timeout=60, **kwargs)
        elif method == "PUT":
            resp = requests.put(url, timeout=30, **kwargs)
        else:
            resp = requests.request(method, url, timeout=30, **kwargs)
        elapsed = (time.time() - start) * 1000  # ms
        return resp, elapsed
    except requests.exceptions.Timeout:
        elapsed = (time.time() - start) * 1000
        return None, elapsed
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return None, elapsed

# ============ 场景 1:冒烟测试 ============
def smoke_test(base_url):
    """验证所有核心接口可用"""
    log("=" * 50)
    log("场景 1:冒烟测试")
    log("=" * 50)
    
    # 1. 商品列表(公开)
    resp, ms = make_request("GET", f"{base_url}/api/products?page=1&page_size=3&status=selling")
    ok = resp and resp.status_code == 200
    record_result("GET /api/products", resp.status_code if resp else 0, ms, ok)
    log(f"  GET /api/products: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 2. 注册
    username = f"verify_{random.randint(10000,99999)}"
    body = {"username": username, "password": TEST_PASSWORD}
    resp, ms = make_request("POST", f"{base_url}/api/auth/register", json=body)
    ok = resp and resp.status_code in (200, 201)
    record_result("POST /api/auth/register", resp.status_code if resp else 0, ms, ok)
    log(f"  POST /api/auth/register: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 3. 登录
    body = {"username": username, "password": TEST_PASSWORD}
    resp, ms = make_request("POST", f"{base_url}/api/auth/login", json=body)
    login_ok = resp and resp.status_code == 200
    token = None
    if login_ok:
        try:
            token = resp.json().get("token")
        except:
            pass
    record_result("POST /api/auth/login", resp.status_code if resp else 0, ms, login_ok)
    log(f"  POST /api/auth/login: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    if not token:
        log("  ⚠ 登录失败,跳过需要鉴权的接口")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 4. /api/auth/me
    resp, ms = make_request("GET", f"{base_url}/api/auth/me", headers=headers)
    ok = resp and resp.status_code == 200
    record_result("GET /api/auth/me", resp.status_code if resp else 0, ms, ok)
    log(f"  GET /api/auth/me: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 5. /api/product/1
    resp, ms = make_request("GET", f"{base_url}/api/product/1", headers=headers)
    ok = resp and resp.status_code == 200
    record_result("GET /api/product/1", resp.status_code if resp else 0, ms, ok)
    log(f"  GET /api/product/1: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 6. /api/search
    resp, ms = make_request("GET", f"{base_url}/api/search?q=iPhone", headers=headers)
    ok = resp and resp.status_code == 200
    record_result("GET /api/search", resp.status_code if resp else 0, ms, ok)
    log(f"  GET /api/search: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 7. 发布商品
    product_body = {
        "title": f"验证商品_{int(time.time())}",
        "price": random.randint(10, 9999),
        "original_price": random.randint(100, 10000),
        "description": "验证用商品",
        "images": [],
        "category": "数码",
        "condition": "9成新"
    }
    resp, ms = make_request("POST", f"{base_url}/api/product", headers=headers, json=product_body)
    product_ok = resp and resp.status_code in (200, 201)
    product_id = None
    if product_ok:
        try:
            product_id = resp.json().get("product_id")
        except:
            pass
    record_result("POST /api/product", resp.status_code if resp else 0, ms, product_ok)
    log(f"  POST /api/product: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 8. 创建订单(使用另一个用户)
    if product_id:
        # 注册并登录买家
        buyer_username = f"verify_buyer_{random.randint(10000,99999)}"
        make_request("POST", f"{base_url}/api/auth/register", json={"username": buyer_username, "password": TEST_PASSWORD})
        resp_buyer, _ = make_request("POST", f"{base_url}/api/auth/login", json={"username": buyer_username, "password": TEST_PASSWORD})
        if resp_buyer and resp_buyer.status_code == 200:
            buyer_token = resp_buyer.json().get("token")
            buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
            order_body = {"product_id": product_id}
            resp, ms = make_request("POST", f"{base_url}/api/orders", headers=buyer_headers, json=order_body)
            order_ok = resp and resp.status_code in (200, 201)
            record_result("POST /api/orders", resp.status_code if resp else 0, ms, order_ok)
            log(f"  POST /api/orders: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    # 9. 管理员登录
    admin_body = {"username": "admin", "password": "admin123"}
    resp, ms = make_request("POST", f"{base_url}/api/admin/login", json=admin_body)
    admin_ok = resp and resp.status_code == 200
    admin_token = None
    if admin_ok:
        try:
            admin_token = resp.json().get("token")
        except:
            pass
    record_result("POST /api/admin/login", resp.status_code if resp else 0, ms, admin_ok)
    log(f"  POST /api/admin/login: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    if admin_token:
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        resp, ms = make_request("GET", f"{base_url}/api/admin/users", headers=admin_headers)
        ok = resp and resp.status_code == 200
        record_result("GET /api/admin/users", resp.status_code if resp else 0, ms, ok)
        log(f"  GET /api/admin/users: {resp.status_code if resp else 'FAIL'} ({ms:.0f}ms)")
    
    log("✅ 冒烟测试完成\n")
    return True

# ============ 场景 2:用户认证链路负载测试 ============
def auth_load_test(base_url, num_users=50, duration=30):
    """模拟并发用户登录/登出"""
    log("=" * 50)
    log(f"场景 2:用户认证链路 ({num_users} 并发, {duration}s)")
    log("=" * 50)
    
    stop_event = threading.Event()
    users_created = []
    
    # 先注册测试用户
    for i in range(1, num_users + 1):
        username = f"loaduser_{i}"
        try:
            resp = requests.post(f"{base_url}/api/auth/register", 
                               json={"username": username, "password": TEST_PASSWORD}, 
                               timeout=10)
            if resp.status_code in (200, 201, 400):  # 400 = 已存在
                users_created.append(username)
        except:
            pass
    
    log(f"  已准备 {len(users_created)} 个测试用户")
    
    def auth_worker(username):
        iterations = 0
        while not stop_event.is_set():
            try:
                # 登录
                resp, ms = make_request("POST", f"{base_url}/api/auth/login", 
                                       json={"username": username, "password": TEST_PASSWORD})
                if resp and resp.status_code == 200:
                    token = resp.json().get("token")
                    if token:
                        headers = {"Authorization": f"Bearer {token}"}
                        # /api/auth/me
                        resp2, ms2 = make_request("GET", f"{base_url}/api/auth/me", headers=headers)
                        record_result(f"GET /api/auth/me", resp2.status_code if resp2 else 0, ms2, 
                                     resp2 and resp2.status_code == 200)
                        # 登出
                        resp3, ms3 = make_request("POST", f"{base_url}/api/auth/logout", headers=headers)
                        record_result(f"POST /api/auth/logout", resp3.status_code if resp3 else 0, ms3,
                                     resp3 and resp3.status_code == 200)
                record_result(f"POST /api/auth/login", resp.status_code if resp else 0, ms,
                             resp and resp.status_code == 200)
                iterations += 1
            except:
                pass
            if not stop_event.is_set():
                time.sleep(random.uniform(0.5, 2.0))
        return iterations
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = {executor.submit(auth_worker, u): u for u in users_created}
        time.sleep(duration)
        stop_event.set()
        
        done_count = 0
        for f in concurrent.futures.as_completed(futures):
            done_count += 1
        
    log(f"  ✅ 认证链路测试完成,共执行 {len([r for r in results if 'login' in r['name'].lower()])} 次登录请求\n")

# ============ 场景 3:商品浏览读密集测试 ============
def browse_load_test(base_url, num_users=200, duration=60):
    """模拟高并发商品浏览"""
    log("=" * 50)
    log(f"场景 3:商品浏览 ({num_users} 并发, {duration}s)")
    log("=" * 50)
    
    stop_event = threading.Event()
    
    # 注册并登录用户
    def login_and_get_token(i):
        username = f"browseuser_{i}"
        try:
            requests.post(f"{base_url}/api/auth/register", 
                        json={"username": username, "password": TEST_PASSWORD}, timeout=10)
            resp = requests.post(f"{base_url}/api/auth/login", 
                               json={"username": username, "password": TEST_PASSWORD}, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("token")
        except:
            pass
        return None
    
    tokens = []
    for i in range(1, min(num_users + 1, 51)):  # 最多准备 50 个用户
        t = login_and_get_token(i)
        if t:
            tokens.append(t)
    
    log(f"  已准备 {len(tokens)} 个登录用户")
    
    if not tokens:
        log("  ⚠ 无可用用户,跳过鉴权接口测试")
    
    keywords = ["iPhone", "笔记本", "自行车", "耳机", "书", "键盘", "鼠标", "显示器", "沙发"]
    
    def browse_worker(token):
        while not stop_event.is_set():
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            
            # 商品列表(无需鉴权)
            resp, ms = make_request("GET", f"{base_url}/api/products?page={random.randint(1,50)}&page_size=20&status=selling")
            record_result("GET /api/products", resp.status_code if resp else 0, ms,
                         resp and resp.status_code == 200)
            
            # 商品详情(需要鉴权)
            if token:
                pid = random.randint(1, 100)
                resp, ms = make_request("GET", f"{base_url}/api/product/{pid}", headers=headers)
                record_result("GET /api/product/<id>", resp.status_code if resp else 0, ms,
                             resp and resp.status_code == 200)
            
            # 搜索(需要鉴权)
            if token:
                kw = random.choice(keywords)
                resp, ms = make_request("GET", f"{base_url}/api/search?q={kw}", headers=headers)
                record_result("GET /api/search", resp.status_code if resp else 0, ms,
                             resp and resp.status_code == 200)
            
            time.sleep(random.uniform(0.5, 1.5))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = []
        for i in range(num_users):
            t = tokens[i % len(tokens)] if tokens else None
            futures.append(executor.submit(browse_worker, t))
        
        time.sleep(duration)
        stop_event.set()
        
        for f in concurrent.futures.as_completed(futures):
            pass
    
    log(f"  ✅ 浏览测试完成\n")

# ============ 场景 4:商品发布与订单写密集测试 ============
def write_load_test(base_url, num_users=20, duration=30):
    """模拟商品发布和订单创建"""
    log("=" * 50)
    log(f"场景 4:商品发布与订单 ({num_users} 并发, {duration}s)")
    log("=" * 50)
    
    stop_event = threading.Event()
    
    # 准备卖家和买家
    def setup_user(prefix):
        username = f"{prefix}_{random.randint(10000,99999)}"
        requests.post(f"{base_url}/api/auth/register", 
                    json={"username": username, "password": TEST_PASSWORD}, timeout=10)
        resp = requests.post(f"{base_url}/api/auth/login", 
                           json={"username": username, "password": TEST_PASSWORD}, timeout=10)
        if resp.status_code == 200:
            return username, resp.json().get("token")
        return username, None
    
    sellers = []
    buyers = []
    for i in range(max(num_users, 5)):
        _, st = setup_user(f"seller_w_{i}")
        if st:
            sellers.append(st)
        _, bt = setup_user(f"buyer_w_{i}")
        if bt:
            buyers.append(bt)
    
    log(f"  卖家: {len(sellers)}, 买家: {len(buyers)}")
    
    def write_worker(seller_token):
        while not stop_event.is_set():
            try:
                headers = {"Authorization": f"Bearer {seller_token}"}
                
                # 发布商品
                product_body = {
                    "title": f"压测商品_{int(time.time())}_{random.randint(1000,9999)}",
                    "price": random.randint(10, 9999),
                    "original_price": random.randint(100, 10000),
                    "description": "负载测试自动生成",
                    "images": [],
                    "category": "数码",
                    "condition": "9成新"
                }
                resp, ms = make_request("POST", f"{base_url}/api/product", headers=headers, json=product_body)
                record_result("POST /api/product", resp.status_code if resp else 0, ms,
                             resp and resp.status_code in (200, 201))
                
                # 如果发布成功,尝试用买家下单
                if resp and resp.status_code in (200, 201) and buyers:
                    try:
                        product_id = resp.json().get("product_id")
                        if product_id:
                            buyer_token = random.choice(buyers)
                            buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
                            order_body = {"product_id": product_id}
                            resp2, ms2 = make_request("POST", f"{base_url}/api/orders", 
                                                    headers=buyer_headers, json=order_body)
                            record_result("POST /api/orders", resp2.status_code if resp2 else 0, ms2,
                                         resp2 and resp2.status_code in (200, 201))
                            
                            # 更新订单
                            if resp2 and resp2.status_code in (200, 201):
                                order_id = resp2.json().get("order_id")
                                if order_id:
                                    resp3, ms3 = make_request("POST", 
                                                              f"{base_url}/api/orders/{order_id}/update",
                                                              headers=buyer_headers,
                                                              json={"status": "paid"})
                                    record_result("POST /api/orders/<id>/update", 
                                                 resp3.status_code if resp3 else 0, ms3,
                                                 resp3 and resp3.status_code == 200)
                    except:
                        pass
                
                time.sleep(random.uniform(1, 3))
            except:
                pass
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sellers)) as executor:
        futures = [executor.submit(write_worker, st) for st in sellers]
        time.sleep(duration)
        stop_event.set()
        for f in concurrent.futures.as_completed(futures):
            pass
    
    log(f"  ✅ 写密集测试完成\n")

# ============ 报告生成 ============
def generate_report():
    """生成测试报告"""
    log("=" * 50)
    log("📊 测试报告")
    log("=" * 50)
    
    if not results:
        log("  无测试结果")
        return
    
    # 按接口分组
    by_endpoint = defaultdict(list)
    for r in results:
        by_endpoint[r["name"]].append(r)
    
    log(f"\n  总请求数: {len(results)}")
    log(f"  总接口数: {len(by_endpoint)}")
    
    total_success = sum(1 for r in results if r["success"])
    total_failed = len(results) - total_success
    log(f"  成功: {total_success}, 失败: {total_failed}")
    log(f"  总体成功率: {total_success/len(results)*100:.1f}%")
    
    # 各接口统计
    log(f"\n  {'接口':<40} {'请求数':>6} {'成功率':>8} {'平均ms':>8} {'P90ms':>8} {'P99ms':>8}")
    log(f"  {'-'*40} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    
    for endpoint, reqs in sorted(by_endpoint.items()):
        times = [r["response_time"] for r in reqs]
        successes = [r for r in reqs if r["success"]]
        success_rate = len(successes) / len(reqs) * 100 if reqs else 0
        avg_time = statistics.mean(times) if times else 0
        sorted_times = sorted(times)
        p90 = sorted_times[int(len(sorted_times) * 0.9)] if sorted_times else 0
        p99 = sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
        
        log(f"  {endpoint:<40} {len(reqs):>6} {success_rate:>7.1f}% {avg_time:>7.0f} {p90:>7.0f} {p99:>7.0f}")
    
    # SLA 检查
    log(f"\n  ⚖ SLA 检查:")
    sla_pass = True
    for endpoint, reqs in by_endpoint.items():
        times = [r["response_time"] for r in reqs if r["success"]]
        if not times:
            continue
        sorted_times = sorted(times)
        p90 = sorted_times[int(len(sorted_times) * 0.9)]
        success_rate = sum(1 for r in reqs if r["success"]) / len(reqs) * 100
        
        # 分类检查
        is_ai = "generate" in endpoint or "analyze" in endpoint
        is_read = "GET" in endpoint.split(" ")[0]
        is_write = "POST" in endpoint.split(" ")[0]
        
        if is_ai:
            sla_time, sla_rate = 15000, 95
        elif is_read:
            sla_time, sla_rate = 500, 99.5
        else:
            sla_time, sla_rate = 2000, 99
        
        p90_ok = "✅" if p90 <= sla_time else "❌"
        rate_ok = "✅" if success_rate >= sla_rate else "❌"
        
        if p90 == "❌" or rate_ok == "❌":
            sla_pass = False
            log(f"    {endpoint}: P90={p90:.0f}ms (SLA<{sla_time}ms) {p90_ok}, 成功率={success_rate:.1f}% (SLA>{sla_rate}%) {rate_ok}")
    
    if sla_pass:
        log("    ✅ 所有接口均满足 SLA")
    else:
        log("    ⚠ 部分接口未满足 SLA")
    
    # 错误详情
    failed = [r for r in results if not r["success"]]
    if failed:
        log(f"\n  ❌ 失败请求详情 (共 {len(failed)} 条):")
        for r in failed[:10]:  # 只显示前 10 条
            log(f"    {r['name']}: HTTP {r['status_code']} ({r['response_time']:.0f}ms)")
        if len(failed) > 10:
            log(f"    ... 还有 {len(failed) - 10} 条")
    
    log("\n" + "=" * 50)
    log("🏁 测试完成")
    log("=" * 50)

# ============ 主入口 ============
def main():
    parser = argparse.ArgumentParser(description="二手物品转售 AI 助手 - JMeter 验证脚本")
    parser.add_argument("--host", default=DEFAULT_HOST, help="目标主机")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="目标端口")
    parser.add_argument("--smoke-only", action="store_true", help="仅运行冒烟测试")
    parser.add_argument("--auth-users", default=50, type=int, help="认证链路并发数")
    parser.add_argument("--browse-users", default=100, type=int, help="浏览并发数")
    parser.add_argument("--write-users", default=10, type=int, help="写操作并发数")
    parser.add_argument("--duration", default=30, type=int, help="负载测试持续时间(秒)")
    args = parser.parse_args()
    
    base_url = f"http://{args.host}:{args.port}"
    log(f"目标: {base_url}")
    log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("")
    
    # 冒烟测试(必须通过)
    if not smoke_test(base_url):
        log("❌ 冒烟测试失败,终止测试")
        return
    
    if args.smoke_only:
        generate_report()
        return
    
    # 负载测试
    auth_load_test(base_url, args.auth_users, args.duration)
    browse_load_test(base_url, args.browse_users, args.duration)
    write_load_test(base_url, args.write_users, args.duration)
    
    # 生成报告
    generate_report()

if __name__ == "__main__":
    main()
