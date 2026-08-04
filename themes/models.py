from django.db import models

# Create your models here.
class Feedback(models.Model):
    name = models.CharField(max_length=25)
    email = models.EmailField()
    number = models.CharField(max_length=10)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self) -> str:
        return self.name