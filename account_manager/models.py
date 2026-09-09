from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    """The business entity an organizer operates in the Plannix marketplace.

    An Organization owns event packages, receives booking requests, and is
    subject to admin approval before it can operate. Organization approval is
    the single marketplace gate: once approved, the organizer's packages are
    live and bookable — no per-package admin approval.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization',
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    contact_number = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='organizations', blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    is_verified = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'

    def __str__(self):
        return self.name

    @property
    def is_approved(self):
        return self.status == 'approved'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:180]
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class OrganizerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organizer_profile',
    )
    business_name = models.CharField(max_length=200, blank=True)
    contact_number = models.CharField(max_length=15, blank=True)
    bio = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organizer Profile'
        verbose_name_plural = 'Organizer Profiles'

    def __str__(self):
        return f'Organizer: {self.user.username}'
