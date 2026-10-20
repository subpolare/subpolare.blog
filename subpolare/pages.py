from django.shortcuts import render


def donate(request):
    return render(request, "donate.html")


def subscribe(request):
    return render(request, "subscribe.html")
