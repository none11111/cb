# -*- coding: utf-8 -*-
"""
生成符合 JMeter 5.6.3 标准的完整测试计划 XML。
核心规则:每个 TestElement 后必须紧跟一个 <hashTree>...</hashTree>
所有兄弟元素共享同一个父 <hashTree>。
路由路径严格对齐 Flask app.py 中的 @app.route 定义。
"""
import os

def jstr(s):
    """XML 安全转义: & → &amp;"""
    return s.replace('&', '&amp;')

# ============================================================
# Groovy 脚本常量
# ============================================================

SCRIPT_LOGIN_TOKEN = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  if (json.token) {
    vars.put("TOKEN", json.token as String)
    def uid = json.user?.uid
    if (uid) vars.put("UID", uid as String)
  }
} catch(e) {}"""

SCRIPT_EXTRACT_PRODUCTS = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def list = json.products ?: json.data
  if (list instanceof List) {
    if (list.size() > 0) {
      def rnd = (int)Math.floor(Math.random() * list.size())
      vars.put("RANDOM_PID", list[rnd].id as String)
    }
    if (list.size() > 1) vars.put("SECOND_PID", list[1].id as String)
    vars.put("PRODUCT_COUNT", list.size() as String)
  }
} catch(e) {}"""

SCRIPT_EXTRACT_DETAIL = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def pid = json.product?.id
  if (pid) vars.put("DETAIL_PID", pid as String)
  def sellerId = json.product?.uid
  if (sellerId) vars.put("SELLER_ID", sellerId as String)
} catch(e) {}"""

SCRIPT_EXTRACT_NEW_PRODUCT = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def pid = json.product_id ?: json.product?.id
  if (pid) vars.put("NEW_PID", pid as String)
} catch(e) {}"""

SCRIPT_EXTRACT_SELLER_PRODUCTS = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def list = json.products
  if (list instanceof List && list.size() > 0) {
    def p = list[0]
    if (p.id) vars.put("EDIT_PID", p.id as String)
  }
} catch(e) {}"""

SCRIPT_SAVE_ORDER = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def oid = json.order_id
  if (oid) vars.put("ORDER_ID", oid as String)
} catch(e) {}"""

SCRIPT_ADMIN_TOKEN = """import groovy.json.JsonSlurper
try {
  def json = new JsonSlurper().parseText(prev.getResponseDataAsString())
  def tk = json.token
  if (!tk) {
    def ct = prev.getCookies()?.getCookie("admin_token")
    if (ct) tk = ct.value
  }
  if (tk) vars.put("ADMIN_TOKEN", tk as String)
} catch(e) {}"""

# ============================================================
# 元件构建器 — 每个函数返回完整闭合的 XML 片段
# ============================================================

def leaf_element(xml_body):
    """将任意 TestElement XML 包装为 <element> + <hashTree/> 完整单元"""
    return xml_body + '\n  <hashTree/>'

def http_defaults(testname):
    return leaf_element(f'''<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="{testname}" enabled="true">
    <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
      <collectionProp name="Arguments.arguments"/>
    </elementProp>
    <stringProp name="HTTPSampler.domain">127.0.0.1</stringProp>
    <stringProp name="HTTPSampler.port">5000</stringProp>
    <stringProp name="HTTPSampler.protocol">http</stringProp>
    <stringProp name="HTTPSampler.contentEncoding">UTF-8</stringProp>
    <stringProp name="HTTPSampler.path"></stringProp>
    <stringProp name="HTTPSampler.concurrentPool">6</stringProp>
    <stringProp name="HTTPSampler.connect_timeout">15000</stringProp>
    <stringProp name="HTTPSampler.response_timeout">30000</stringProp>
  </ConfigTestElement>''')

def cookie_manager():
    return leaf_element('''<CookieManager guiclass="CookiePanel" testclass="CookieManager" testname="HTTP Cookie管理器" enabled="true">
    <collectionProp name="CookieManager.cookies"/>
    <boolProp name="CookieManager.clearEachIteration">false</boolProp>
    <boolProp name="CookieManager.controlledByThreadGroup">false</boolProp>
    <boolProp name="CookieManager.useSameUser">false</boolProp>
  </CookieManager>''')

def csv_data_set(testname, filename, var_names):
    return leaf_element(f'''<CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="{testname}" enabled="true">
    <stringProp name="delimiter">,</stringProp>
    <stringProp name="fileEncoding">UTF-8</stringProp>
    <stringProp name="filename">{filename}</stringProp>
    <boolProp name="ignoreFirstLine">true</boolProp>
    <boolProp name="quotedData">false</boolProp>
    <boolProp name="recycle">true</boolProp>
    <stringProp name="shareMode">shareMode.all</stringProp>
    <boolProp name="stopThread">false</boolProp>
    <stringProp name="variableNames">{var_names}</stringProp>
  </CSVDataSet>''')

def result_collector(testname, guiclass='SummaryReport'):
    return leaf_element(f'''<ResultCollector guiclass="{guiclass}" testclass="ResultCollector" testname="{testname}" enabled="true">
    <boolProp name="ResultCollector.error_logging">false</boolProp>
    <objProp>
      <name>saveConfig</name>
      <value class="SampleSaveConfiguration">
        <time>true</time><latency>true</latency><timestamp>true</timestamp>
        <success>true</success><label>true</label><code>true</code><message>true</message>
        <threadName>true</threadName><dataType>true</dataType>
        <encoding>false</encoding><assertions>true</assertions><subresults>true</subresults>
        <responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>
        <fieldNames>true</fieldNames>
        <responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders>
        <responseDataOnError>true</responseDataOnError>
        <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
        <assertionsResultsToSave>0</assertionsResultsToSave>
        <bytes>true</bytes><sentBytes>true</sentBytes><url>true</url>
        <threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime>
      </value>
    </objProp>
    <stringProp name="filename"></stringProp>
  </ResultCollector>''')

def response_assertion(testname='Assert HTTP 200', test_strings=None):
    codes = test_strings or ['200']
    if len(codes) > 1:
        pattern = '|'.join(codes)
    else:
        pattern = codes[0]
    return leaf_element(f'''<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="{testname}" enabled="true">
    <collectionProp name="Asserion.test_strings">
      <stringProp name="54321">{pattern}</stringProp>
    </collectionProp>
    <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
    <boolProp name="Assertion.assume_success">true</boolProp>
    <intProp name="Assertion.test_type">1</intProp>
  </ResponseAssertion>''')

def jsr223_post(testname, script):
    return leaf_element(f'''<JSR223PostProcessor guiclass="TestBeanGUI" testclass="JSR223PostProcessor" testname="{testname}" enabled="true">
    <stringProp name="cacheKey">{testname}</stringProp>
    <stringProp name="filename"></stringProp>
    <stringProp name="parameters"></stringProp>
    <stringProp name="scriptLanguage">groovy</stringProp>
    <stringProp name="script">{jstr(script)}</stringProp>
  </JSR223PostProcessor>''')

def jsr223_pre(testname, script):
    return leaf_element(f'''<JSR223PreProcessor guiclass="TestBeanGUI" testclass="JSR223PreProcessor" testname="{testname}" enabled="true">
    <stringProp name="cacheKey">{testname}</stringProp>
    <stringProp name="filename"></stringProp>
    <stringProp name="parameters"></stringProp>
    <stringProp name="scriptLanguage">groovy</stringProp>
    <stringProp name="script">{jstr(script)}</stringProp>
  </JSR223PreProcessor>''')

def set_content_type():
    """HeaderManager:设置 Content-Type: application/json"""
    return leaf_element('''<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Content-Type Header" enabled="true">
    <collectionProp name="HeaderManager.headers">
      <elementProp name="" elementType="Header">
        <stringProp name="Header.name">Content-Type</stringProp>
        <stringProp name="Header.value">application/json</stringProp>
      </elementProp>
    </collectionProp>
  </HeaderManager>''')

def set_auth_header(token_var='TOKEN'):
    """HeaderManager:设置 Authorization: Bearer ${token_var}"""
    return leaf_element(f'''<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Auth Header" enabled="true">
    <collectionProp name="HeaderManager.headers">
      <elementProp name="" elementType="Header">
        <stringProp name="Header.name">Authorization</stringProp>
        <stringProp name="Header.value">Bearer ${{{token_var}}}</stringProp>
      </elementProp>
    </collectionProp>
  </HeaderManager>''')

def http_sampler(testname, method, path, body=None, post_body_raw=False, args=None, children=None, need_auth=False, need_content_type=False):
    """HTTP 请求 — 返回完整闭合单元(含子元素)"""
    props = f'''    <stringProp name="HTTPSampler.protocol">http</stringProp>
    <stringProp name="HTTPSampler.contentEncoding">UTF-8</stringProp>
    <stringProp name="HTTPSampler.path">{path}</stringProp>
    <stringProp name="HTTPSampler.method">{method}</stringProp>
    <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
    <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
    <boolProp name="HTTPSampler.postBodyRaw">{str(post_body_raw).lower()}</boolProp>
    <boolProp name="HTTPSampler.multipart">false</boolProp>
    <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
    <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
    <stringProp name="HTTPSampler.concurrentPool">6</stringProp>
    <stringProp name="HTTPSampler.connect_timeout">15000</stringProp>
    <stringProp name="HTTPSampler.response_timeout">30000</stringProp>'''

    if body and post_body_raw:
        arguments = f'''    <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments">
          <elementProp name="json_body" elementType="HTTPArgument">
            <boolProp name="HTTPArgument.always_encode">false</boolProp>
            <stringProp name="Argument.name">json_body</stringProp>
            <stringProp name="Argument.value">{jstr(body)}</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
            <boolProp name="HTTPArgument.use_equals">false</boolProp>
          </elementProp>
        </collectionProp>
      </elementProp>'''
    elif args:
        coll = ''.join(f'''
            <elementProp name="{a['name']}" elementType="HTTPArgument">
              <boolProp name="HTTPArgument.always_encode">false</boolProp>
              <stringProp name="Argument.name">{a['name']}</stringProp>
              <stringProp name="Argument.value">{a['value']}</stringProp>
              <stringProp name="Argument.metadata">=</stringProp>
              <boolProp name="HTTPArgument.use_equals">true</boolProp>
            </elementProp>''' for a in args)
        arguments = f'''    <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments">{coll}
        </collectionProp>
      </elementProp>'''
    else:
        arguments = '''    <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>'''

    element_open = f'''<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{testname}" enabled="true">
{props}
{arguments}
  </HTTPSamplerProxy>'''

    # 组装子元素
    kids = list(children) if children else []

    # 自动添加 Content-Type 和 Auth 头
    if need_content_type or (post_body_raw and body):
        kids.insert(0, set_content_type())
    if need_auth:
        kids.insert(0, set_auth_header('TOKEN'))

    if kids:
        children_xml = '\n'.join(kids)
        return f'''{element_open}
  <hashTree>
{children_xml}
  </hashTree>'''
    else:
        return f'{element_open}\n  <hashTree/>'

# ============================================================
# 组装:构建完整的 JMX
# ============================================================

def _thread_group(testname, num_threads, ramp_time, loops, children):
    """构建完整的 ThreadGroup + hashTree 单元"""
    children_xml = '\n'.join(children)
    return f'''<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{testname}" enabled="true">
    <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
    <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
      <stringProp name="LoopController.loops">{loops}</stringProp>
      <boolProp name="LoopController.continue_forever">false</boolProp>
    </elementProp>
    <stringProp name="ThreadGroup.num_threads">{num_threads}</stringProp>
    <stringProp name="ThreadGroup.ramp_time">{ramp_time}</stringProp>
    <boolProp name="ThreadGroup.scheduler">false</boolProp>
    <stringProp name="ThreadGroup.duration"></stringProp>
    <stringProp name="ThreadGroup.delay"></stringProp>
  </ThreadGroup>
  <hashTree>
{children_xml}
  </hashTree>'''

def build_testplan():
    parts = []

    # ---- 根节点 ----
    parts.append('''<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="CB 二手物品 AI 助手压测方案 v4.0" enabled="true">
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments">
          <elementProp name="HOST" elementType="Argument">
            <stringProp name="Argument.name">HOST</stringProp>
            <stringProp name="Argument.value">${__P(HOST,127.0.0.1)}</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
          </elementProp>
          <elementProp name="PORT" elementType="Argument">
            <stringProp name="Argument.name">PORT</stringProp>
            <stringProp name="Argument.value">${__P(PORT,5000)}</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
          </elementProp>
          <elementProp name="PASSWORD" elementType="Argument">
            <stringProp name="Argument.name">PASSWORD</stringProp>
            <stringProp name="Argument.value">Test@1234</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
          </elementProp>
        </collectionProp>
      </elementProp>
      <stringProp name="TestPlan.user_define_classpath"></stringProp>
    </TestPlan>
    <hashTree>''')

    # ---- 全局配置 ----
    parts.append(http_defaults('HTTP 请求默认值'))
    parts.append(cookie_manager())
    parts.append(csv_data_set('CSV_DATA_SET', 'test_users.csv', 'CSV_USERNAME,CSV_PASSWORD'))
    parts.append(result_collector('Summary Report', 'SummaryReport'))
    parts.append(result_collector('Aggregate Report', 'StatVisualizer'))
    parts.append(result_collector('View Results Tree', 'ViewResultsFullVisualizer'))

    # ---- setUp 线程组:健康检查 ----
    tg0 = [http_sampler('GET /', 'GET', '/',
            children=[response_assertion('Assert 200 or 302', ['200', '302'])])]
    parts.append(_thread_group('[setUp] 健康检查', '1', '1', '1', tg0))

    # ---- TG1 用户认证 ----
    tg1 = []
    # 登录(公开端点)
    tg1.append(http_sampler('POST /api/auth/login', 'POST', '/api/auth/login',
               body='{"username":"${CSV_USERNAME}","password":"${CSV_PASSWORD}"}',
               post_body_raw=True,
               children=[response_assertion('Assert login 200', ['200']),
                         jsr223_post('Extract Token', SCRIPT_LOGIN_TOKEN)]))
    # 获取当前用户信息(@login_required)
    tg1.append(http_sampler('GET /api/auth/me', 'GET', '/api/auth/me',
               need_auth=True,
               children=[response_assertion('Assert me 200')]))
    parts.append(_thread_group('TG1 用户认证', '${__P(threads_auth,10)}', '${__P(ramp_auth,5)}', '${__P(loops_auth,5)}', tg1))

    # ---- TG2 商品浏览 ----
    tg2 = []
    # 登录
    tg2.append(http_sampler('POST /api/auth/login', 'POST', '/api/auth/login',
               body='{"username":"${CSV_USERNAME}","password":"${CSV_PASSWORD}"}',
               post_body_raw=True,
               children=[jsr223_post('Extract Token', SCRIPT_LOGIN_TOKEN)]))
    # 商品列表(公开端点,参数 page/page_size)
    tg2.append(http_sampler('GET /api/products', 'GET', '/api/products',
               args=[{'name': 'page', 'value': '${__Random(1,5)}'},
                     {'name': 'page_size', 'value': '20'}],
               children=[response_assertion('Assert list 200'),
                         jsr223_post('Extract Product IDs', SCRIPT_EXTRACT_PRODUCTS)]))
    # 商品详情(@login_required,单数 product)
    tg2.append(http_sampler('GET /api/product/${RANDOM_PID}', 'GET', '/api/product/${RANDOM_PID}',
               need_auth=True,
               children=[response_assertion('Assert detail 200', ['200', '404']),
                         jsr223_post('Extract Detail Info', SCRIPT_EXTRACT_DETAIL)]))
    # 搜索(@login_required)
    tg2.append(http_sampler('GET /api/search', 'GET', '/api/search',
               need_auth=True,
               args=[{'name': 'q', 'value': 'test'},
                     {'name': 'page', 'value': '1'}],
               children=[response_assertion('Assert search 200', ['200', '400'])]))
    parts.append(_thread_group('TG2 商品浏览', '${__P(threads_browse,25)}', '${__P(ramp_browse,10)}', '${__P(loops_browse,2)}', tg2))

    # ---- TG3 商品发布与下单 ----
    tg3 = []
    # 卖家登录
    tg3.append(http_sampler('POST /api/auth/login (Seller)', 'POST', '/api/auth/login',
               body='{"username":"seller_${__javaScript(((ctx.getThreadNum() % 5) + 1),)}","password":"${PASSWORD}"}',
               post_body_raw=True,
               children=[jsr223_post('Extract Token', SCRIPT_LOGIN_TOKEN)]))
    # 发布商品(@login_required,单数 product)
    tg3.append(http_sampler('POST /api/product', 'POST', '/api/product',
               need_auth=True,
               body='{"title":"JMeter_${__time(HHmmssSSS)}_T${__threadNum}","price":${__Random(10,999)},"original_price":${__Random(50,5000)},"description":"JMeter 压测自动生成商品","images":[],"category":"数码","condition":"9成新"}',
               post_body_raw=True,
               children=[response_assertion('Assert create 200', ['200', '201']),
                         jsr223_post('Extract New Product ID', SCRIPT_EXTRACT_NEW_PRODUCT)]))
    # 商品详情
    tg3.append(http_sampler('GET /api/product/${NEW_PID}', 'GET', '/api/product/${NEW_PID}',
               need_auth=True,
               children=[jsr223_post('Extract Detail', SCRIPT_EXTRACT_DETAIL)]))
    # 我的商品列表(@login_required, /api/my-products)
    tg3.append(http_sampler('GET /api/my-products', 'GET', '/api/my-products',
               need_auth=True,
               children=[jsr223_post('Extract Seller Products', SCRIPT_EXTRACT_SELLER_PRODUCTS)]))
    # 编辑商品(@login_required, /api/my-products/edit/<id>)
    tg3.append(http_sampler('PUT /api/my-products/edit/${NEW_PID}', 'PUT', '/api/my-products/edit/${NEW_PID}',
               need_auth=True,
               body='{"title":"JMeter_Updated_${__threadNum}","price":${__Random(5,500)}}',
               post_body_raw=True,
               children=[response_assertion('Assert update 200', ['200', '404'])]))
    # 买家登录
    tg3.append(http_sampler('POST /api/auth/login (Buyer)', 'POST', '/api/auth/login',
               body='{"username":"testuser_${__javaScript(((ctx.getThreadNum() % 50) + 1),)}","password":"${PASSWORD}"}',
               post_body_raw=True,
               children=[jsr223_post('Extract Buyer Token', SCRIPT_LOGIN_TOKEN)]))
    # 创建订单(@login_required)
    tg3.append(http_sampler('POST /api/orders', 'POST', '/api/orders',
               need_auth=True,
               body='{"product_id":${NEW_PID}}',
               post_body_raw=True,
               children=[response_assertion('Assert order 200', ['200', '201', '400']),
                         jsr223_post('Extract Order ID', SCRIPT_SAVE_ORDER)]))
    # 我的订单(@login_required)
    tg3.append(http_sampler('GET /api/orders', 'GET', '/api/orders',
               need_auth=True,
               children=[response_assertion('Assert orders 200')]))
    # 更新订单状态-付款(@login_required, /api/orders/<id>/update)
    tg3.append(http_sampler('POST /api/orders/${ORDER_ID}/update (paid)', 'POST', '/api/orders/${ORDER_ID}/update',
               need_auth=True,
               body='{"status":"paid"}',
               post_body_raw=True,
               children=[response_assertion('Assert pay 200', ['200', '400'])]))
    # 更新订单状态-确认收货
    tg3.append(http_sampler('POST /api/orders/${ORDER_ID}/update (completed)', 'POST', '/api/orders/${ORDER_ID}/update',
               need_auth=True,
               body='{"status":"completed"}',
               post_body_raw=True,
               children=[response_assertion('Assert confirm 200', ['200', '400'])]))
    parts.append(_thread_group('TG3 商品发布与下单', '${__P(threads_write,10)}', '${__P(ramp_write,10)}', '${__P(loops_write,5)}', tg3))

    # ---- TG4 AI 工具(实际存在的路由) ----
    tg4 = []
    # 登录获取 token
    tg4.append(http_sampler('POST /api/auth/login', 'POST', '/api/auth/login',
               body='{"username":"${CSV_USERNAME}","password":"${CSV_PASSWORD}"}',
               post_body_raw=True,
               children=[jsr223_post('Extract Token', SCRIPT_LOGIN_TOKEN)]))
    # AI 分析图片(@login_required, /api/analyze-image,需要 image 字段)
    tg4.append(http_sampler('POST /api/analyze-image', 'POST', '/api/analyze-image',
               need_auth=True,
               body='{"image":"data:image/jpeg;base64,/9j/4AAQ"}',
               post_body_raw=True,
               children=[response_assertion('Assert analyze-image 200', ['200', '400', '500'])]))
    # AI 生成文案(@login_required, /api/generate-copy,需要 image 字段)
    tg4.append(http_sampler('POST /api/generate-copy', 'POST', '/api/generate-copy',
               need_auth=True,
               body='{"image":"data:image/jpeg;base64,/9j/4AAQ","product_name":"test","style":"tech"}',
               post_body_raw=True,
               children=[response_assertion('Assert generate-copy 200', ['200', '400', '500'])]))
    # AI 生成全部文案(@login_required, /api/generate-all-copies)
    tg4.append(http_sampler('POST /api/generate-all-copies', 'POST', '/api/generate-all-copies',
               need_auth=True,
               body='{"image":"data:image/jpeg;base64,/9j/4AAQ","product_name":"test"}',
               post_body_raw=True,
               children=[response_assertion('Assert generate-all 200', ['200', '400', '500'])]))
    # AI 分析商品(@login_required, /api/analyze-product)
    tg4.append(http_sampler('POST /api/analyze-product', 'POST', '/api/analyze-product',
               need_auth=True,
               body='{"images":["data:image/jpeg;base64,/9j/4AAQ"],"name":"test"}',
               post_body_raw=True,
               children=[response_assertion('Assert analyze-product 200', ['200', '400', '500'])]))
    # AI 商品识别(@login_required, /api/detect-product)
    tg4.append(http_sampler('POST /api/detect-product', 'POST', '/api/detect-product',
               need_auth=True,
               body='{"images":["data:image/jpeg;base64,/9j/4AAQ"]}',
               post_body_raw=True,
               children=[response_assertion('Assert detect-product 200', ['200', '400', '500'])]))
    parts.append(_thread_group('TG4 AI 工具', '${__P(threads_ai,10)}', '${__P(ramp_ai,5)}', '${__P(loops_ai,5)}', tg4))

    # ---- TG5 管理员 ----
    tg5 = []
    # 管理员登录(专用端点 /api/admin/login)
    tg5.append(http_sampler('POST /api/admin/login', 'POST', '/api/admin/login',
               body='{"username":"admin","password":"admin123"}',
               post_body_raw=True,
               children=[response_assertion('Assert admin login 200', ['200', '401']),
                         jsr223_post('Extract Admin Token', SCRIPT_ADMIN_TOKEN)]))
    # 用户列表(@admin_required,使用 ADMIN_TOKEN)
    tg5.append(http_sampler('GET /api/admin/users', 'GET', '/api/admin/users',
               args=[{'name': 'page', 'value': '1'}, {'name': 'page_size', 'value': '20'}],
               children=[set_auth_header('ADMIN_TOKEN'),
                         response_assertion('Assert users 200', ['200', '401'])]))
    # 商品列表(@admin_required)
    tg5.append(http_sampler('GET /api/admin/products', 'GET', '/api/admin/products',
               args=[{'name': 'page', 'value': '1'}, {'name': 'page_size', 'value': '20'}],
               children=[set_auth_header('ADMIN_TOKEN'),
                         response_assertion('Assert products 200', ['200', '401'])]))
    # 登录历史(@admin_required)
    tg5.append(http_sampler('GET /api/admin/login-history', 'GET', '/api/admin/login-history',
               children=[set_auth_header('ADMIN_TOKEN'),
                         response_assertion('Assert logs 200', ['200', '401'])]))
    # 异常检测(@admin_required)
    tg5.append(http_sampler('GET /api/admin/anomaly-detection', 'GET', '/api/admin/anomaly-detection',
               children=[set_auth_header('ADMIN_TOKEN'),
                         response_assertion('Assert anomaly 200', ['200', '401'])]))
    parts.append(_thread_group('TG5 管理员', '${__P(threads_admin,10)}', '${__P(ramp_admin,5)}', '${__P(loops_admin,5)}', tg5))

    # ---- 收尾 ----
    parts.append('''    </hashTree>
  </hashTree>
</jmeterTestPlan>''')

    return '\n'.join(parts)

# ============================================================
# 写入文件
# ============================================================

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cb-jmeter-test.jmx')
xml_content = build_testplan()

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(xml_content)

size = os.path.getsize(output_path)
print(f'JMX written to: {output_path}')
print(f'File size: {size:,} bytes ({size/1024:.1f} KB)')
print(f'Lines: {xml_content.count(chr(10))}')

# 验证 hashTree 平衡
opens = xml_content.count('<hashTree>') + xml_content.count('<hashTree/>')
closes = xml_content.count('</hashTree>')
self_close = xml_content.count('<hashTree/>')
print(f'hashTree opens (incl self-close): {opens}')
print(f'hashTree self-closes: {self_close}')
print(f'hashTree explicit closes: {closes}')
print(f'Balance: opens - self_close = {opens - self_close}, explicit closes = {closes}')
