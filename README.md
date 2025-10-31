<div align="center">
  <h1>subpolare.ru</h1> 
</div>

This is the code base of my blog. I used the [vas3k.blog code](https://github.com/vas3k/vas3k.blog/blob/main/vas3k_blog) as a basis and edited it. 

## ⚙️ Tech details

**Backend:**
- Python 3.11+ with Django 4+
- PostgreSQL
- [Poetry](https://python-poetry.org/) as a package manager

**Frontend:**
- [htmx](https://htmx.org/)
- Mostly pure JS, no webpack, no builders
- No CSS framework

**Blogging part:**
- Markdown with a bunch of [custom plugins](common/markdown/plugins)

## 🏗️ How to build

If you like to build it, don't forget to create an empty PostgreSQL database or your migrations will fail.

```
createdb subpolare
```

After that use poetry and open http://localhost:8000 to see an empty page.

```
pip3 install poetry
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver 8000
```

Then you need to create a superuser to write your posts using http://localhost:8000/godmode 

```
poetry run python manage.py createsuperuser
```

Also there is one more option for those who prefer Docker. 

```
# Create container with the blog 
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Check that everything is alright
docker compose -f docker-compose.production.yml ps

# 
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py migrate
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py collectstatic --noinput

# Create superuser 
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py createsuperuser

# 
docker compose -f docker-compose.production.yml -f docker-compose.tls.yml up -d
docker compose -f docker-compose.production.yml -f docker-compose.tls.yml logs -f caddy
```
