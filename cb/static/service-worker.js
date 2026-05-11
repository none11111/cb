// PWA Service Worker - 闲置好物
const CACHE_NAME = 'zhixinhaowu-v1';
const STATIC_CACHE = 'zhixinhaowu-static-v1';
const DYNAMIC_CACHE = 'zhixinhaowu-dynamic-v1';

// 需要缓存的静态资源
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/app.html',
  '/auth.html',
  '/manifest.json',
  '/auth-utils.js'
];

// 安装事件 - 缓存静态资源
self.addEventListener('install', event => {
  console.log('[SW] Installing Service Worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('[SW] Caching static assets');
        // 使用 Promise.allSettled 确保即使某些文件失败也不影响整体
        return Promise.allSettled(
          STATIC_ASSETS.map(url => 
            fetch(url).then(response => {
              if (response.ok) {
                return cache.put(url, response);
              }
            }).catch(err => console.log('[SW] Cache failed for:', url, err))
          )
        );
      })
      .then(() => self.skipWaiting())
  );
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', event => {
  console.log('[SW] Activating Service Worker...');
  event.waitUntil(
    caches.keys()
      .then(keys => {
        return Promise.all(
          keys
            .filter(key => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
            .map(key => {
              console.log('[SW] Removing old cache:', key);
              return caches.delete(key);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

// 请求拦截 - 实现缓存策略
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 跳过非GET请求
  if (request.method !== 'GET') {
    return;
  }

  // API请求 - 直接网络请求，不缓存
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // 页面请求 - 直接网络请求
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request));
    return;
  }

  // 静态资源 - 缓存优先
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // 其他请求 - 网络优先
  event.respondWith(fetch(request));
});

// 判断是否为静态资源
function isStaticAsset(pathname) {
  return /\.(js|css|png|jpg|jpeg|gif|svg|webp|woff|woff2|ttf|ico)$/.test(pathname);
}

// 缓存优先策略
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Cache first fetch failed:', error);
    return caches.match('/index.html');
  }
}

// 网络优先策略
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network first fetch failed, trying cache:', error);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // API请求失败时返回错误JSON
    if (request.url.includes('/api/')) {
      return new Response(JSON.stringify({ error: '网络请求失败', offline: true }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    return caches.match('/index.html');
  }
}

// 推送通知处理
self.addEventListener('push', event => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body || '您有新的消息',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/'
    },
    actions: [
      { action: 'open', title: '查看' },
      { action: 'close', title: '关闭' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title || '闲置好物', options)
  );
});

// 通知点击处理
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'close') return;

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        // 如果已有窗口，打开它
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(url);
            return client.focus();
          }
        }
        // 否则打开新窗口
        return clients.openWindow(url);
      })
  );
});

// 后台同步处理
self.addEventListener('sync', event => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

// 数据同步
async function syncData() {
  try {
    // 这里可以实现数据同步逻辑
    console.log('[SW] Syncing data...');
  } catch (error) {
    console.log('[SW] Sync failed:', error);
  }
}

// 消息处理
self.addEventListener('message', event => {
  console.log('[SW] Message received:', event.data);
  
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
  
  if (event.data === 'getVersion') {
    event.ports[0].postMessage({ version: CACHE_NAME });
  }
});
