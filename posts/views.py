from datetime import datetime

from django.db.models import F
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, get_language

from comments.models import Comment
from posts.forms import PostEditForm
from posts.models import Post
from posts.renderers import render_list, render_list_all, render_post
from vas3k_blog.posts import POST_TYPES


def index(request):
    toples_posts = list(
        Post.visible_objects()
        .filter(type="toples", is_visible_on_home_page=True)
        .order_by("-published_at")[:3]
    )

    blocks = []

    if toples_posts:
        blocks.append({
            "title": _("ТОПЛЕС"),
            "template": "index/toples.html",
            "posts": toples_posts,
            "url": reverse("list_posts", args=("toples",)),
        })

    blocks.append({
        "title": _("Обо мне"),
        "template": "index/about.html",
        "posts": [],
    })

    return render(request, "index.html", {
        "blocks": blocks,
    })


def list_posts(request, post_type="all"):
    posts = Post.visible_objects().select_related()

    if post_type and post_type != "all":
        if post_type not in POST_TYPES:
            raise Http404()

        posts = posts.filter(type=post_type)
        if not posts.exists():
            return render(request, "message.html", {
                "title": _("Здесь пока ничего нет"),
                "message": _("Я ещё не добавил посты в этот раздел"),
            })

        return render_list(request, post_type, posts)

    if not posts.exists():
        return render(request, "message.html", {
            "title": _("Здесь пока ничего нет"),
            "message": _("Я ещё не опубликовал ни одной записи"),
        })

    return render_list_all(request, posts)


def show_post(request, post_type, post_slug):
    post = get_object_or_404(Post, slug=post_slug, lang=get_language())

    # post_type can be changed
    if post.type != post_type:
        return redirect("show_post", post.type, post.slug)

    # post_type can be removed
    if post_type not in POST_TYPES:
        raise Http404()

    # drafts are visible only with a flag
    if not post.is_visible and not request.GET.get("preview"):
        raise Http404()

    Post.objects.filter(id=post.id)\
        .update(view_count=F("view_count") + 1)

    if post.url:
        return redirect(post.url)

    comments = Comment.visible_objects()\
        .filter(post=post)\
        .order_by("created_at")

    translations = Post.objects.filter(
        type=post.type,
        slug=post.slug,
        is_visible=True,
        published_at__lte=datetime.utcnow(),
    ).exclude(
        lang=get_language()
    ).order_by("lang")

    return render_post(request, post, {
        "post": post,
        "comments": comments,
        "translations": translations,
    })


def edit_post(request, post_type, post_slug):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden()

    post = get_object_or_404(Post, type=post_type, slug=post_slug, lang=get_language())

    if request.method == "POST":
        form = PostEditForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            return redirect("show_post", post_type=post.type, post_slug=post.slug)
    else:
        form = PostEditForm(instance=post)

    return render(request, "posts/edit.html", {
        "form": form,
    })
