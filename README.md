<div align="center">
  <h1>subpolare.ru</h1> 
</div>

This is the code base of my blog: https://subpolare.ru

I used the [vas3k.blog code](https://github.com/vas3k/vas3k.blog/blob/main/vas3k_blog) as a basis and edited it. Thank you very much, [vas3k](https://github.com/vas3k). 

☢️ _The code is not adapted at all so that someone can take it for themselves. Take it at your own risk and don't be surprised if I did something wrong._

## ⚙️ Tech details

**Backend:**
- Python 3.11+ with Django 4+
- PostgreSQL
- [Poetry](https://python-poetry.org/) as a package manager

**Frontend:**
- [htmx](https://htmx.org/)
- Mostly pure JavaScript (no webpack, no builders)
- No CSS framework

**Blogging part:**
- Markdown with a bunch of [custom plugins](common/markdown/plugins)

## 🌊 How to build

### 1. poetry

If you still decide to run my code, there are two ways. For the test, I recommend using `poetry`. Fisrt, you need to creat an empty PostgreSQL database. 

```
apt install postgresql 
createdb subpolare
```

Than you can install and run `poetry`. 

```
pip3 install poetry
poetry install
poetry run python3 manage.py migrate
poetry run python3 manage.py runserver 8000
```

Now you can open http://localhost:8000 and enjoy your own blog. Don't forget to create superuser to write your posts. 

```
poetry run python3 manage.py createsuperuser
```

### 2. Docker 

There is another option for those who prefer Docker. 

```
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

docker compose -f docker-compose.production.yml exec blog_app python3 manage.py migrate
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py collectstatic --noinput

docker compose -f docker-compose.production.yml exec blog_app python3 manage.py createsuperuser
```

Now the website on http://localhost:8000 is ready! But in order for the whole world to see it, you need to configure `nginx`. 

```
sudo apt update
sudo apt install -y nginx

sudo cp /srv/subpolare.blog/etc/nginx/subpolare.ru.conf /etc/nginx/sites-available/subpolare.ru.conf
sudo ln -s /etc/nginx/sites-available/subpolare.ru.conf /etc/nginx/sites-enabled/subpolare.ru.conf
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
```

If you don't enable HTTPS, you also need to do this. 

```
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d subpolare.ru -d www.subpolare.ru
```

That's how my blog started.

## Markdown-редактор постов

Существующая форма `/<тип>/<slug>/edit/` доступна только суперпользователю.
Она хранит исходный Markdown в `Post.text`; сохранение использует прежний
`Post.save()` и сброс `html_cache`. Комментарии, RSS, raw HTML и плагины блога
сохраняют прежний renderer. Скрытый пост через `?preview=1` теперь тоже доступен
только суперпользователю.

Основа — [vas3k.club, ревизия 2c8bb711](https://github.com/vas3k/vas3k.club/tree/2c8bb71126336106d46823144046837defc27960):
`frontend/static/js/common/markdown-editor.js`, `App.js` и vendored
`inline-attachment`. EasyMDE **2.20.0** взят из версии, зафиксированной в lock-файле
Клуба; готовые JS/CSS и MIT-лицензия лежат в `frontend/static/js/vendor/easymde/`.
SHA-512 npm-архива проверен по lock-файлу Клуба. Сборщик и npm install не нужны.

Отличия от Клуба:

- Обычные static-скрипты вместо ES modules/Vue/Webpack: у блога нет такой сборки.
- Загрузка идёт через закрытый `POST /editor/upload/` с CSRF. В Клубе upload code
  включён в общий шаблон `common/js.html`; в публичном блоге он остаётся на сервере.
  Прокси передаёт Pepic multipart `media`, параметр `code`, заголовок
  `Accept: application/json`, возвращает только `{"uploaded": "URL"}`.
- Только JPEG/PNG/WebP/GIF, до 14 МиБ: задача про изображения, а nginx уже
  ограничивает весь запрос 15 МиБ. Видео из панели Клуба не добавлялись.
- Независимые отметки файлов, замена диапазона вместо всего документа, timeout,
  ошибки и блокировка сохранения нужны для сохранности текста и параллельных
  загрузок. Неудачную отметку нужно удалить после повторной загрузки или отказа от неё.
- `POST /<тип>/<slug>/edit/preview/` рендерит несохранённый текст renderer'ом блога;
  кнопка preview Клуба проходит через сохранение формы. Здесь не меняются кеш,
  даты и счётчики. Предпросмотр изолирован в iframe: стили и специальные блоки
  сохранены, скрипты из raw HTML, формы и действия комментариев/кликеров отключены.
  Спойлеры и подсветку кода подключает родительская страница. Панель включает
  предпросмотр, две колонки и полноэкранный режим из существующей заготовки блога.

### Настройка и локальная проверка владельцем

Новые переменные `PEPIC_UPLOAD_URL` и `PEPIC_UPLOAD_CODE` в `.env.example` пустые.
`.env` исключён из Git. URL хранилища отсутствовал в настройках этого репозитория;
для указанного владельцем хранилища задайте
`PEPIC_UPLOAD_URL=https://media.subpolare.ru/upload/multipart/` только после
подтверждения адреса. Код доступа задаётся владельцем в серверном окружении или
серверном `.env`; не добавляйте его в Git, HTML/JS и команды с литералом секрета.
Без этих настроек редактор и preview работают, загрузка отвечает понятной ошибкой 503.

Для обычного локального запуска используйте отдельный тестовый PostgreSQL
и `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`,
`POSTGRES_PORT`, описанные в `subpolare/settings.py`. `DATABASE_URL` не читается.
При запуске через Poetry `.env` автоматически не загружается: экспортируйте
переменные в окружение процесса. `DEBUG=true` включает dev-режим.

```sh
poetry install
poetry run python3 manage.py migrate
poetry run python3 manage.py createsuperuser
poetry run python3 manage.py runserver 127.0.0.1:8000
```

В `/godmode/` создайте тестовый пост, затем откройте его `/edit/`. Проверьте
форматирование, `[[[...]]]`, `{{{...}}}`, `[? ... ?]`, raw HTML, preview и сохранение.
Для загрузки выберите картинку скрепкой, перетащите файл и вставьте изображение
из буфера; во время загрузки сохранение заблокировано. Проверьте ошибку сети,
повторную загрузку и сохранность текста. Без входа и с обычным пользователем
редактирование, preview и upload должны возвращать 403; скрытый пост с
`?preview=1` — 404. В тестах upload всегда подменён; вызов настроенного реального
URL вручную действительно загрузит файл в хранилище.

Полный набор автоматических тестов без БД, контейнеров и сетевых запросов:

```sh
poetry run python3 manage.py test --settings=subpolare.test_settings
node --test frontend/tests/post-editor.test.cjs
node --check frontend/static/js/post-editor.js
node --check frontend/static/js/vendor/inline-attachment/core.js
node --check frontend/static/js/vendor/inline-attachment/codemirror4.js
git diff --check
```

Тесты проверяют маршруты, суперпользователя, CSRF, plugins/raw HTML, отсутствие
записи при preview, обычный путь сохранения, контракт и ошибки Pepic, параллельные
загрузки и сохранность Markdown. База в test settings отключена; фактическая запись
в PostgreSQL этими тестами не проверяется.

### Деплой владельцем через Git

Локально после проверки diff:

```sh
git status --short
git diff --check
git add .env.example README.md frontend/html/posts/edit.html frontend/html/posts/editor-preview.html frontend/static/css/post-editor.css frontend/static/js/post-editor.js frontend/static/js/vendor/easymde frontend/static/js/vendor/inline-attachment frontend/tests/post-editor.test.cjs posts/editor.py posts/forms.py posts/views.py posts/templatetags/posts.py posts/tests.py subpolare/settings.py subpolare/urls.py subpolare/test_settings.py
git diff --cached --stat
git commit -m "Add admin Markdown editor with private uploads and server preview"
git push
```

На сервере, из каталога проекта (в nginx указан `/srv/subpolare.blog`):

```sh
cd /srv/subpolare.blog
git pull --ff-only
docker compose -f docker-compose.production.yml build blog_app
docker compose -f docker-compose.production.yml up -d --no-deps blog_app
```

Перед перезапуском владелец задаёт upload-переменные в серверном `.env`;
production compose уже подключает его через `env_file`. Новых миграций нет;
`make docker-run-production` сам выполняет существующий `migrate` при старте.
Отдельный `collectstatic` для показанной конфигурации nginx не нужен: nginx отдаёт
`frontend/static/`, обновлённый через Git; этот же каталог смонтирован в контейнер.
Frontend-сборки нет. Перезапуск нужен для Python-кода и переменных окружения.
Dockerfile уже выполняет `poetry lock` при сборке — это существующее поведение,
зависимости и lock-файл в рамках редактора не изменялись.
