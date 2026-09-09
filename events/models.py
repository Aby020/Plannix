from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.text import slugify


class EventCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Event Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Event(models.Model):
    """Renamed from Event_Company. Uses db_table + db_column for data continuity."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='events',
    )
    organization = models.ForeignKey(
        'account_manager.Organization',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events',
    )
    title = models.CharField(max_length=30, db_column='event_name')
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    category = models.ForeignKey(
        EventCategory,
        on_delete=models.PROTECT,
        related_name='events',
        null=True,
        blank=True,
    )
    featured_image = models.ImageField(upload_to='events', db_column='event_img')
    description = models.TextField(db_column='event_description')
    price = models.BigIntegerField(default=0, db_column='event_price')
    venue = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=30)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    contact_number = models.CharField(max_length=10, db_column='event_mobile_number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    publish_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'events_event_company'
        ordering = ['-created_at']
        permissions = [
            ('can_approve_event', 'Can approve events'),
            ('can_reject_event', 'Can reject events'),
            ('can_publish_event', 'Can publish events'),
            ('can_force_cancel_event', 'Can force cancel events'),
            ('can_view_all_events', 'Can view all events'),
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['owner']),
            models.Index(fields=['category']),
            models.Index(fields=['start_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_free(self):
        return self.price == 0

    @property
    def is_bookable(self):
        return self.status == 'live' and self.is_active

    @property
    def is_public(self):
        return self.status in ('live', 'completed')


class EventInclusion(models.Model):
    """Replaces package1-4. Many-to-one with Event."""
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='inclusions')
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name_plural = 'Event Inclusions'

    def __str__(self):
        return f'{self.event.title} - {self.name}'


class EventImage(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='events/gallery')
    caption = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'{self.event.title} - Image {self.sort_order}'


class EventBooking(models.Model):
    """Renamed from Event_Booking. Uses db_table + db_column for data continuity."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    attendee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings',
        db_column='user_id',
    )
    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    name = models.CharField(max_length=30)
    email = models.EmailField()
    number = models.CharField(max_length=10)
    event_title = models.CharField(max_length=30, db_column='event_company_name')
    price = models.BigIntegerField(default=0, db_column='event_price')
    event_location = models.CharField(max_length=30)
    event_date = models.DateField(null=True, blank=True)  # NEW additive field
    event_booking_date = models.CharField(max_length=10, blank=True)  # Legacy kept
    # Human-shareable booking reference (e.g. PXN-8F3K2Z), unique per booking.
    # Nullable so existing rows migrate cleanly (NULLs are distinct under the
    # unique constraint); backfilled by the 0014 data migration.
    booking_reference = models.CharField(max_length=20, unique=True, blank=True,
                                         null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'events_event_booking'
        indexes = [
            models.Index(fields=['attendee']),
            models.Index(fields=['event']),
            models.Index(fields=['status']),
            models.Index(fields=['event_date']),
        ]

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            import uuid
            self.booking_reference = f'PXN-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Review(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='reviews')
    attendee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    booking = models.OneToOneField(
        EventBooking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='review',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    moderation_status = models.CharField(
        max_length=12,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('hidden', 'Hidden')],
        default='pending',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['event']),
            models.Index(fields=['moderation_status']),
        ]

    def __str__(self):
        return f'Review by {self.attendee} on {self.event}'


class EventAuditLog(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=50)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event', 'created_at']),
        ]

    def __str__(self):
        return f'{self.action} on {self.event} by {self.actor}'


class BookingPayment(models.Model):
    """An advance payment against an EventBooking.

    One payment per booking (OneToOne) so an already-paid advance can never be
    paid again. The amount is always the server-calculated advance derived from
    the confirmed package price — never a browser-submitted value. Only Razorpay
    order/payment IDs and the payment reference are stored; no card details and
    no payment secrets ever reach this model or the frontend.
    """

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]
    PURPOSE_ADVANCE = 'advance'
    PURPOSE_CHOICES = [(PURPOSE_ADVANCE, 'Advance')]

    booking = models.OneToOneField(
        EventBooking,
        on_delete=models.CASCADE,
        related_name='payment',
    )
    purpose = models.CharField(max_length=12, choices=PURPOSE_CHOICES,
                               default=PURPOSE_ADVANCE, editable=False)
    payment_reference = models.CharField(max_length=40, unique=True, editable=False)
    razorpay_order_id = models.CharField(max_length=64, unique=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    # Server-calculated advance in rupees (consistent with EventBooking.price);
    # converted to paise only when creating the Razorpay order.
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default=STATUS_PENDING)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.payment_reference} ({self.get_status_display()})'

    @property
    def is_paid(self):
        return self.status == self.STATUS_PAID

    def save(self, *args, **kwargs):
        if not self.payment_reference:
            import uuid
            self.payment_reference = f'PX-{uuid.uuid4().hex[:10]}'
        super().save(*args, **kwargs)
