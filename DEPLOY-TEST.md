# Выкатка ветки `feature/personnel-hr-module` на тестовый поддомен

Тестовый сайт **hr.allkey.kz** (и API **api.hr.allkey.kz**) поднимается **рядом**
с рабочим allkey.kz и **его не трогает**: отдельные контейнеры, отдельная база,
отдельный сертификат, свои порты (фронт 3001, backend 8001), отдельный
`SECRET_KEY`. Рабочий сайт продолжает жить как есть.

Файлы для этого уже готовы в репозитории:
- `docker-compose.test.yml` — тестовый стек;
- `nginx/hr.allkey.kz.conf` — конфиг nginx для поддомена;
- `.env.test.example` — шаблон настроек (пароли/ключ).

---

## Что делаете именно ВЫ, а что требует доступа к серверу

| Шаг | Кто может сделать |
|---|---|
| A. DNS-записи в PS.KZ | **Вы сами** (панель регистратора домена) |
| B. Команды на сервере (git, docker, nginx, certbot) | **Нужен SSH/консольный доступ к серверу.** Если его нет — см. раздел «Если у вас нет SSH» в конце |

Порядок: сначала **A (DNS)**, подождать, потом **B (сервер)**.

---

## Часть A. DNS в панели PS.KZ (делаете вы)

Нужно направить два имени на IP-адрес сервера allkey.kz.
**IP сервера** возьмите у того, кто настраивал сервер, или в панели хостинга
(это тот же адрес, на котором сейчас работает allkey.kz).

1. Войдите в личный кабинет **PS.KZ** → раздел **«Домены»** → домен **allkey.kz**
   → **«Управление DNS»** (или «DNS-записи» / «Редактор зоны»).
2. Добавьте **две записи типа A**:

   | Тип | Имя (поддомен) | Значение (куда) | TTL |
   |-----|----------------|-----------------|-----|
   | A   | `hr`           | IP сервера      | 3600 (или минимум) |
   | A   | `api.hr`       | IP сервера      | 3600 |

   > В PS.KZ в поле «Имя» вводится только левая часть — `hr` и `api.hr`
   > (не `hr.allkey.kz` целиком). Если поле требует полное имя — тогда
   > `hr.allkey.kz` и `api.hr.allkey.kz`.

3. Сохраните. Подождите, пока записи «разойдутся» (обычно 10–60 минут, иногда
   до нескольких часов).
4. Проверить, что имя уже указывает на сервер, можно так (на своём компьютере):
   ```
   nslookup hr.allkey.kz
   ```
   В ответе должен быть IP вашего сервера. Пока не так — не переходите к части B.

---

## Часть B. На сервере (нужен SSH)

Все команды выполняются в SSH-сессии на сервере, в папке проекта
(там, где лежит `docker-compose.prod.yml`). Ниже `sudo` — запуск с правами
администратора; если вы уже под root, `sudo` можно опускать.

### B1. Забрать код нужной ветки
```bash
cd /путь/к/проекту/Allkey-2.0-live      # та же папка, где docker-compose.prod.yml
git fetch origin
git checkout feature/personnel-hr-module
git pull origin feature/personnel-hr-module
```

### B2. Создать настройки теста `.env.test`
```bash
cp .env.test.example .env.test
nano .env.test           # откроется редактор
```
В файле:
- `POSTGRES_PASSWORD` — придумайте надёжный пароль;
- `SECRET_KEY` — сгенерируйте отдельный ключ (не такой, как на проде) командой
  в другом окне: `openssl rand -hex 32` и вставьте результат.

Сохранить в `nano`: `Ctrl+O`, `Enter`, затем выйти: `Ctrl+X`.

### B3. Прогнать тесты в целевом образе (обязательный шаг перед сборкой)
Это тот самый прогон в `python:3.11-slim` (важно для pymorphy3 и словарей):
```bash
docker run --rm -v "$PWD/backend:/app" -w /app python:3.11-slim \
  bash -c "pip install -q -r requirements.txt && python -m pytest -q"
```
Должно быть `... passed`. Если есть `failed` — **не продолжайте**, пришлите вывод.

### B4. Поднять тестовые контейнеры
```bash
docker compose -f docker-compose.test.yml --env-file .env.test up -d --build
```
Проверить, что поднялись (frontend/backend/db со статусом `Up`):
```bash
docker compose -f docker-compose.test.yml --env-file .env.test ps
```
Backend локально отвечает (должно вернуть `{"status":"healthy"}`):
```bash
curl -s http://127.0.0.1:8001/health
```

### B5. Получить SSL-сертификат для поддомена
Сначала — временный http-конфиг только для проверки владения доменом:
```bash
sudo mkdir -p /var/www/certbot
sudo tee /etc/nginx/sites-available/hr-temp.conf >/dev/null <<'EOF'
server {
    listen 80;
    server_name hr.allkey.kz api.hr.allkey.kz;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'ok'; add_header Content-Type text/plain; }
}
EOF
sudo ln -sf /etc/nginx/sites-available/hr-temp.conf /etc/nginx/sites-enabled/hr-temp.conf
sudo nginx -t && sudo systemctl reload nginx
```
Запросить сертификат (замените e-mail на свой):
```bash
sudo certbot certonly --webroot -w /var/www/certbot \
  -d hr.allkey.kz -d api.hr.allkey.kz \
  --agree-tos -m ВАШ_EMAIL --no-eff-email
```
Должно быть «Successfully received certificate».

### B6. Включить рабочий nginx-конфиг поддомена
```bash
sudo rm -f /etc/nginx/sites-enabled/hr-temp.conf
sudo cp nginx/hr.allkey.kz.conf /etc/nginx/sites-available/hr.allkey.kz.conf
sudo ln -sf /etc/nginx/sites-available/hr.allkey.kz.conf /etc/nginx/sites-enabled/hr.allkey.kz.conf
sudo nginx -t && sudo systemctl reload nginx
```
> `nginx -t` не должен показывать ошибок. Если показывает — не перезагружайте,
> пришлите вывод. Рабочий сайт при ошибке `-t` не пострадает (nginx не
> перечитает конфиг).

### B7. Проверить
Откройте в браузере **https://hr.allkey.kz** — должен открыться тестовый сайт.
Зарегистрируйте учётную запись (как на обычном сайте) — она получит роль
сотрудника и увидит пункт меню «Кадровые документы».

Автопродление сертификата уже настроено на сервере (общий `certbot renew` по
cron) — новый сертификат продлевается автоматически, отдельно настраивать не
нужно.

---

## Обновить тест позже (после новых коммитов)
```bash
cd /путь/к/проекту/Allkey-2.0-live
git pull origin feature/personnel-hr-module
docker compose -f docker-compose.test.yml --env-file .env.test up -d --build
```

## Остановить / убрать тест (прод не затрагивается)
```bash
docker compose -f docker-compose.test.yml --env-file .env.test down
# и, если нужно, отключить nginx-конфиг поддомена:
sudo rm -f /etc/nginx/sites-enabled/hr.allkey.kz.conf
sudo systemctl reload nginx
```

---

## Если у вас нет SSH-доступа к серверу — честно

Чтобы код заработал как сайт, кто-то должен выполнить команды **на сервере**.
Способа «выложить сайт вообще без доступа к какой-либо машине» не существует —
это не ограничение проекта, так устроены серверы. Реальные варианты:

1. **Отдать эту инструкцию тому, у кого есть доступ к серверу allkey.kz**
   (тот, кто его настраивал). Он выполняет Часть B по шагам — от вас только DNS
   (Часть A) и `.env.test`. Самый простой путь.

2. **Панель хостинга с веб-консолью.** У многих VPS есть в личном кабинете
   «Консоль»/«Terminal» прямо в браузере — это тот же доступ к серверу, просто
   без отдельной SSH-программы. Тогда Часть B делаете вы там.

3. **Облачный хостинг приложений (PaaS: Render, Railway, Fly.io).**
   Подключаете GitHub-репозиторий через их сайт, они сами собирают и запускают —
   SSH не нужен, всё через веб-интерфейс; затем поддомен `hr.allkey.kz`
   направляется на их адрес (CNAME в PS.KZ). Это **отдельная площадка** со своей
   базой и своей настройкой (не этот `docker-compose`), нужен их аккаунт и,
   как правило, привязка карты. Если пойдём этим путём — подготовлю отдельную
   конфигурацию под выбранный сервис.

Чего сделать нельзя: опубликовать работающий сайт, не имея командного доступа
ни к одному серверу и ни к одному PaaS. Тут обхода нет — нужен доступ хотя бы
к чему-то одному из списка выше.
