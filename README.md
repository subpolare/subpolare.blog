<div align="center">
  <h1>subpolare.ru</h1> 
</div>

This is the code base of my blog: https://subpolare.ru

I used the [vas3k.blog code](https://github.com/vas3k/vas3k.blog/blob/main/vas3k_blog) as a basis and edited it. Thank you very much, [vas3k](https://github.com/vas3k). 

☢️ _The code is not adapted at all so that someone can take it for themselves. Take it at your own risk and don't be surprised if I did something wrong._

## ⚙️ Tech details

**Backend:**
- Python 3.12+ with Django (versions in `pyproject.toml` / `poetry.lock`)
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

## Карта статей

После «Обо мне» главная показывает физическую карту с точками статей. Данные
Natural Earth и Leaflet 1.9.4 лежат локально: ключи API, тайлы, внешний геокодер
и frontend-сборка не нужны. До приближения к карте загружается только маленький
загрузчик; без JavaScript или при ошибке остаётся список статей.

Управление: `/godmode/map/mapmarker/`, раздел **Map → Точки**. Доступ имеет
только активный superuser с `is_staff`. Нажатие на свободное место обзорной карты
открывает добавление с координатами, на точку — редактирование. В форме можно
найти город, передвинуть точку, выбрать статью, цвет и превью. Изменения карты
попадают в БД только после «Сохранить». Одна статья — одна точка. Публичная карта
исключает выключенные точки, черновики, будущие и закрытые статьи; учитывает язык
сайта, но не флаг показа статьи в основной ленте.

Жёлтые места: `/godmode/map/mapplace/`, раздел **Map → Жёлтые точки**, с теми же
правами доступа. Название, широту и долготу можно ввести вручную или выбрать
координаты на карте. Необязательная заметка (до 500 символов) показывается вместе
с названием при наведении, фокусе с клавиатуры или нажатии на точку. Выключенные
места не попадают в публичный `/map/places/`. Миграции `0002_mapplace` и
`0003_seed_places` создают таблицу и добавляют 37 мест; повторяющиеся Токио и
Осака объединены, Идзу обозначает полуостров, Молдино — село в Тверской области.
Для стран, морей и регионов выбраны условные точки внутри их территории.

Превью — квадрат WebP 128×128 до 20 КБ, хранится в БД. Режим «Из статьи» сохраняет
снимок `Post.main_image()` при сохранении точки. Действие «Обновить превью из
статьи» в списке обновляет такие снимки; режим «Своё» оно пропускает. Исходники
не сохраняются и не передаются посетителям. При ошибке используется заглушка,
а godmode показывает предупреждение.

`MAP_IMAGE_ALLOWED_HOSTS` задаётся в серверном окружении: точные имена хостов
через запятую, без схемы, пути и wildcard; по умолчанию `i.subpolare.ru`.
Например, `MAP_IMAGE_ALLOWED_HOSTS=i.subpolare.ru,images.example.org`.
Скачивание разрешено только по HTTPS:443, без редиректов, прокси и непубличных IP.
Ограничения: 8 МиБ, 24 Мп, 12000 px по стороне; DNS до 3 с, транспорт до 8 с
с таймаутом отдельной операции до 3 с. Добавлять хост нужно только при доверии
к его содержимому. Свой файл загружается непосредственно в форму точки.

### Данные и обновление статики

Использованы `ne_50m_land.geojson`, `ne_50m_lakes.geojson`,
`ne_50m_rivers_lake_centerlines.geojson` и `ne_50m_populated_places.geojson`, а также координаты из
`ne_10m_populated_places_simple.geojson` из
[Natural Earth, ревизия ca96624](https://github.com/nvkelso/natural-earth-vector/tree/ca96624a56bd078437bca8184e78163e5039ad19/geojson).
Natural Earth разрешает использование и изменение этих данных как
[public domain](https://www.naturalearthdata.com/about/terms-of-use/).
В подготовленных слоях суши, 412 озёр и 62 участков крупнейших рек нет атрибутов;
реки отбираются по `scalerank <= 2` и рисуются линией 0,65 px с прозрачностью 0,22.
У 1251 города остаются координаты, русское/английское название, ранг и население;
12 точек малых океанских островов скрыты, но доступны для поиска в редакторе.
Ещё 1239 небольших городов добавлены в тот же JSON только координатами с флагом
`secondary`: они на 15% меньше, с непрозрачностью 0,32 вместо 0,6. Они не участвуют
в поиске по названию. При подготовке выбираются города с населением 1000–150000
по данным источника, без близких повторов (в пределах 0,15° по обеим осям).
Координаты округлены до трёх знаков. Государственных границ нет.
Карта использует `L.CRS.EPSG4326`: обычные города показаны тусклыми точками без
подписей. Их радиус плавно растёт от 1,1 до 3 px при приближении; диаметр жёлтых
мест — от 5 до 10 px, превью статей — от 44 до 72 px. В светлой теме посещённые места
окрашены в тёплый оранжевый `#C76A24`, в тёмной — жёлтый `#F2C94C`. Эти места заменяют
совпадающие фоновые точки. Единственный мир ограничен долготами ±180° и широтами
±90°. Начальный обзор на большом экране вмещает весь мир, на мобильном — статьи.
Leaflet взят из официального npm-архива 1.9.4; BSD-2-Clause лицензия сохранена
в `frontend/static/map/leaflet-1.9.4/LICENSE`. Вид колец основан на
[референсе vas3k.club](https://github.com/vas3k/vas3k.club/blob/master/frontend/static/css/components/people.css).

Воспроизводимая подготовка с проверкой SHA-256 исходников:

```sh
poetry run python utils/prepare_map_assets.py
# Без сети: каталог содержит пять исходных GeoJSON и leaflet-1.9.4.tgz
poetry run python utils/prepare_map_assets.py --source-dir /path/to/downloads
# Только координаты городов, без пересборки геометрии и Leaflet:
poetry run python utils/prepare_map_assets.py --cities-only --source-dir /path/to/downloads
# После изменений JS/CSS (также обновляет hash в URL и проверяет лимит 325 000 байт):
poetry run python utils/prepare_map_assets.py --pack-only
```

Готовые JSON, JS, CSS, `.gz` и `manifest.json` нужно включать в один коммит.
Приложение никогда не скачивает Natural Earth или Leaflet во время работы.
Шаблоны используют версию из manifest; после обновления ресурсов перезапустите
приложение, чтобы сбросить кеш версии. Nginx уже отдаёт `frontend/static/`
с `gzip_static on`; добавлен `gzip_vary on`. `tmp/static/` не редактируется.

### Проверки и применение владельцем

```sh
poetry run python manage.py test --settings=subpolare.test_settings
node --test frontend/tests/*.test.cjs
node --check frontend/static/map/loader.js
node --check frontend/static/map/map.js
node --check frontend/static/js/post-editor.js
git diff --check
```

Для отдельных интеграционных тестов нужен **одноразовый PostgreSQL**, пользователь
с правом создания БД и Python 3.12 (на нём выполнена приёмка). Экспортируйте
`MAP_TEST_HOST`, `MAP_TEST_PORT`, `MAP_TEST_USER`, `MAP_TEST_PASSWORD`, `MAP_TEST_DB`;
значения по умолчанию описаны в `subpolare/integration_test_settings.py`.
Тесты создают и удаляют `test_subpolare_map`, не подключайте их к рабочему кластеру.

```sh
poetry run python manage.py test map.integration_tests --settings=subpolare.integration_test_settings --noinput
```

Перед запуском обновлённого приложения примените новую миграцию на нужной БД:

```sh
poetry run python manage.py migrate
# Либо для существующей production-конфигурации:
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py migrate
```

Затем перезапустите приложение, проверьте `nginx -t` и примените конфигурацию
nginx обычным способом. Статика отдаётся из исходного каталога, отдельной npm
сборки нет. При необходимости отката Python-кода таблицу карты можно оставить;
обратная миграция удаляет точки и их превью. Автоматический деплой не выполнялся.

Замеры, выполненные проверки, ограничения ручной приёмки и скриншоты находятся
в [отчёте по карте](docs/map-acceptance.md).
