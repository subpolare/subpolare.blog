<div align="center">
  <h1>subpolare.ru</h1> 
</div>

This is the code base of my blog: https://subpolare.ru

I used the [vas3k.blog code](https://github.com/vas3k/vas3k.blog/blob/main/vas3k_blog) as a basis and edited it. Thank you very much, [vas3k](https://github.com/vas3k). 

☢️ The code is not adapted at all so that someone can take it for themselves. Take it at your own risk and don't be surprised if I did something wrong. 

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

### Local test with `poetry`

If you still decide to run my code, there are two ways. For the test, I recommend using `poetry`. 

```
# Create PostgreSQL database manually 
apt install postgresql 
createdb subpolare

# Install and run poetry
pip3 install poetry
poetry install
poetry run python3 manage.py migrate
poetry run python3 manage.py runserver 8000
```

Now you can open http://localhost:8000 and enjoy your own blog. Don't forget to create superuser to write your posts. 

```
poetry run python3 manage.py createsuperuser
```

### Docker 

There is another option for those who prefer Docker. 

```
# Building the production containers and firing them up
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Quick check if everything's running smoothly 
docker compose -f docker-compose.production.yml ps

# Running migrations and collecting static files
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py migrate
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py collectstatic --noinput

# Creating the admin user for the blog
docker compose -f docker-compose.production.yml exec blog_app python3 manage.py createsuperuser
```

Now the website on http://localhost:8000 is ready! But in order for the whole world to see it, you need to configure `nginx`. 

```
# Updating packages and installing nginx 
sudo apt update
sudo apt install -y nginx

# Copying our nginx config, creating symlink and removing default site
sudo cp /srv/subpolare.blog/etc/nginx/subpolare.ru.conf /etc/nginx/sites-available/subpolare.ru.conf
sudo ln -s /etc/nginx/sites-available/subpolare.ru.conf /etc/nginx/sites-enabled/subpolare.ru.conf
sudo rm -f /etc/nginx/sites-enabled/default

# Testing nginx config, enabling autostart and starting the service
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