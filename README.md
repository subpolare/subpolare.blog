# My blog

## ⚙️ Tech details

**Backend:**
- Python 3.11+
- Django 4+
- PostgreSQL
- [Poetry](https://python-poetry.org/) as a package manager

**Frontend:**
- [htmx](https://htmx.org/)
- Mostly pure JS, no webpack, no builders
- No CSS framework

**Blogging part:**
- Markdown with a bunch of [custom plugins](common/markdown/plugins)

## 🏗️ How to build

If you like to build it from scratch don't forget to create an empty Postgres database or your migrations will fail.

```
createdb subpolare
psql subpolare -c "CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'postgres';"
```

```
pip3 install poetry
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver 8000
```

Another option for those who prefer Docker:

```
$ docker-compose up
```

Then open http://localhost:8000 and see an empty page.
