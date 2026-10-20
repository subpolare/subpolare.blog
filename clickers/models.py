from django.db import models


class Clicker(models.Model):
    post = models.ForeignKey("posts.Post", related_name="clickers", on_delete=models.CASCADE)
    block = models.TextField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ipaddress = models.GenericIPAddressField(db_index=True)
    useragent = models.CharField(max_length=256)

    class Meta:
        db_table = "clickers"
