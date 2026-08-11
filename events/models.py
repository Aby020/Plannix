from django.conf import settings
from django.db import models


class Event_Company(models.Model):
    """An event package / service offered by a partner vendor on Plannix."""
    event_img = models.ImageField(upload_to='events')
    event_name = models.CharField(max_length=30)
    event_type = models.CharField(max_length=30)
    event_price = models.BigIntegerField()
    event_description = models.TextField()
    event_mobile_number = models.CharField(max_length=10)
    package1 = models.CharField(max_length=30)
    package2 = models.CharField(max_length=30)
    package3 = models.CharField(max_length=30)
    package4 = models.CharField(max_length=30)
    mob_number = models.CharField(max_length=10)
    location = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.event_name


class Event_Booking(models.Model):
    """A booking a user makes for an event package on a chosen date."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings',
    )
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='pending'
    )
    name = models.CharField(max_length=30)
    email = models.EmailField()
    number = models.CharField(max_length=10)
    event_company_name = models.CharField(max_length=30)
    event_type = models.CharField(max_length=30)
    event_price = models.BigIntegerField()
    event_booking_date = models.CharField(max_length=10)
    event_location = models.CharField(max_length=30)
    event_mobile_number = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
