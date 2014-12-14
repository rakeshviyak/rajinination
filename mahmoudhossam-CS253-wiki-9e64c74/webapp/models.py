from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    
class User(models.Model):
    username = models.CharField(max_length=30)
    hashed_pw = models.CharField(max_length=100)
    salt = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
