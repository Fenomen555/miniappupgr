# ===== HTTPS =====
server {
    server_name stavitskiy.com www.stavitskiy.com;
    listen 38.180.114.244:443 ssl http2;

    ssl_certificate     /var/www/httpd-cert/stavitskiy.com_2025-10-14-15-15_08.crt;
    ssl_certificate_key /var/www/httpd-cert/stavitskiy.com_2025-10-14-15-15_08.key;

    charset utf-8;

    # --- производительность/сжатие ---
    gzip on;
    gzip_vary on;
    gzip_proxied expired no-cache no-store private auth;
    gzip_types text/css text/xml application/javascript text/plain application/json image/svg+xml image/x-icon;
    gzip_comp_level 1;

    # --- базовые лимиты/таймауты ---
    client_max_body_size 10m;
    keepalive_timeout 65s;

    root /var/www/stavitskiy_c_usr/data/www/stavitskiy.com/dist;
    index index.html;

    # ---- API → FastAPI:8000 ----
    location /api/ {
        # ВАЖНО: без завершающего слеша у целевого URL
        proxy_pass http://127.0.0.1:8000;

        # Пробрасываем заголовки
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Keep-Alive к бэкенду + минимальная задержка
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Снижение лага первой байты (отключаем буферы Nginx для API)
        proxy_buffering off;
        proxy_request_buffering off;
        add_header X-Accel-Buffering no;

        # Таймауты
        proxy_connect_timeout 5s;
        proxy_send_timeout    65s;
        proxy_read_timeout    65s;
    }

    # ---- статика (кэшируем) ----
    location ~* \.(?:js|css|png|jpg|jpeg|gif|svg|ico|webp|woff|woff2|ttf|map)$ {
        try_files $uri =404;
        expires 7d;
        access_log off;
        add_header Cache-Control "public, max-age=604800, immutable";
    }

    # ---- SPA роутинг ----
    location / {
        try_files $uri /index.html;
    }

    include "/etc/nginx/fastpanel2-sites/stavitskiy_c_usr/stavitskiy.com.includes";
    include /etc/nginx/fastpanel2-includes/*.conf;

    error_log  /var/www/stavitskiy_c_usr/data/logs/stavitskiy.com-frontend.error.log;
    access_log /var/www/stavitskiy_c_usr/data/logs/stavitskiy.com-frontend.access.log;
}

# ===== HTTP → HTTPS =====
server {
    listen 38.180.114.244:80;
    server_name stavitskiy.com www.stavitskiy.com;
    return 301 https://$host$request_uri;

    error_log  /var/www/stavitskiy_c_usr/data/logs/stavitskiy.com-frontend.error.log;
    access_log /var/www/stavitskiy_c_usr/data/logs/stavitskiy.com-frontend.access.log;
}