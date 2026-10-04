# -*- coding: utf-8 -*-
"""
JMeter 测试数据准备脚本
运行 JMeter 前执行此脚本注册测试用户
使用方法: python setup_test_users.py [--host localhost] [--port 5000]
"""

import requests
import sys
import time
import argparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
TEST_PASSWORD = "Test@1234"

def register_user(base_url, username, password):
    """注册单个用户,返回 (成功, 状态码)"""
    try:
        resp = requests.post(
            f"{base_url}/api/auth/register",
            json={"username": username, "password": password},
            timeout=10
        )
        return resp.status_code in (200, 201, 400), resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    parser = argparse.ArgumentParser(description="JMeter 测试数据准备")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--buyers", default=50, type=int, help="注册买家数量")
    parser.add_argument("--sellers", default=5, type=int, help="注册卖家数量")
    parser.add_argument("--check", action="store_true", help="仅检查服务可用性")
    args = parser.parse_args()
    
    base_url = f"http://{args.host}:{args.port}"
    
    # 检查服务可用性
    try:
        resp = requests.get(f"{base_url}/api/products?page=1&page_size=1", timeout=5)
        if resp.status_code == 200:
            print(f"✅ Flask 服务运行正常: {base_url}")
        else:
            print(f"⚠ Flask 服务响应异常: HTTP {resp.status_code}")
            return
    except Exception as e:
        print(f"❌ 无法连接到 Flask 服务: {e}")
        print("   请先启动 Flask: python app.py")
        return
    
    if args.check:
        return
    
    print(f"\n开始注册测试用户...")
    print(f"目标: {base_url}")
    print(f"买家: {args.buyers} 个, 卖家: {args.sellers} 个")
    print(f"密码: {TEST_PASSWORD}")
    print("-" * 50)
    
    success = 0
    skipped = 0
    failed = 0
    
    # 注册买家
    for i in range(1, args.buyers + 1):
        username = f"testuser_{i}"
        ok, code = register_user(base_url, username, TEST_PASSWORD)
        if ok:
            if code in (200, 201):
                success += 1
                print(f"  ✅ {username}: 注册成功")
            else:
                skipped += 1
                if i <= 5:  # 只显示前 5 个的跳过信息
                    print(f"  ⏭ {username}: 已存在 (HTTP {code})")
        else:
            failed += 1
            print(f"  ❌ {username}: 失败 ({code})")
        
        if i % 10 == 0:
            print(f"  ... 已处理 {i}/{args.buyers}")
            time.sleep(0.3)  # 避免请求过快
    
    # 注册卖家
    for i in range(1, args.sellers + 1):
        username = f"seller_{i}"
        ok, code = register_user(base_url, username, TEST_PASSWORD)
        if ok:
            if code in (200, 201):
                success += 1
                print(f"  ✅ {username}: 注册成功")
            else:
                skipped += 1
        else:
            failed += 1
            print(f"  ❌ {username}: 失败 ({code})")
        time.sleep(0.3)
    
    print("-" * 50)
    print(f"📊 注册完成: 成功 {success}, 跳过(已存在) {skipped}, 失败 {failed}")
    print(f"\n下一步:")
    print(f"  1. 运行 JMeter: jmeter -n -t cb-jmeter-test.jmx -l result.jtl -e -o ./report")
    print(f"  2. 或运行 Python 验证: python jmeter_verify.py")

if __name__ == "__main__":
    main()
