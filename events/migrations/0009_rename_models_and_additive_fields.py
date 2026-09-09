# Hand-written additive migration that PRESERVES existing demo data.
#
# The previous auto-generated migration treated Event_Company -> Event and
# Event_Booking -> EventBooking as delete+create, which would have DROPPED the
# events_event_company (20 rows) and events_event_booking (11 rows) tables and
# lost all data. This migration instead renames the models and fields so the
# underlying tables and rows are kept intact.
#
# Notes:
# - Event.owner is added as null=True temporarily (existing rows have no
#   owner); the data migration (0010) assigns the plannix_platform organizer,
#   then the cleanup migration (0011) alters it to NOT NULL.
# - Event.slug is added as unique=False temporarily (all existing rows start
#   blank); the data migration backfills unique slugs, then the cleanup
#   migration (0011) adds the unique constraint.
# - Legacy fields (Event.event_type, package1-4, mob_number and
#   EventBooking.event_type, event_mobile_number) are intentionally KEPT in
#   this additive step and removed by the cleanup migration (0011).
from django.conf import settings
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0008_remove_event_company_event_img2_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ---------------------------------------------------------------
        # Rename models: keeps the same db_table, so all rows are preserved.
        # ---------------------------------------------------------------
        migrations.RenameModel(
            old_name="Event_Company",
            new_name="Event",
        ),
        migrations.RenameModel(
            old_name="Event_Booking",
            new_name="EventBooking",
        ),
        # Restore the original physical table names. The old models had no
        # explicit Meta.db_table in migration state, so RenameModel computed
        # new names (events_event / events_eventbooking). The new models pin
        # Meta.db_table to the legacy table names for continuity, so rename the
        # physical tables back. Data is preserved throughout.
        migrations.AlterModelTable(
            name="Event",
            table="events_event_company",
        ),
        migrations.AlterModelTable(
            name="EventBooking",
            table="events_event_booking",
        ),
        # ---------------------------------------------------------------
        # Rename fields: all of these keep the same db_column, so the
        # underlying column (and data) is unchanged.
        # ---------------------------------------------------------------
        migrations.RenameField(
            model_name="Event",
            old_name="event_name",
            new_name="title",
        ),
        migrations.RenameField(
            model_name="Event",
            old_name="event_img",
            new_name="featured_image",
        ),
        migrations.RenameField(
            model_name="Event",
            old_name="event_description",
            new_name="description",
        ),
        migrations.RenameField(
            model_name="Event",
            old_name="event_price",
            new_name="price",
        ),
        migrations.RenameField(
            model_name="Event",
            old_name="event_mobile_number",
            new_name="contact_number",
        ),
        migrations.RenameField(
            model_name="EventBooking",
            old_name="event_company_name",
            new_name="event_title",
        ),
        migrations.RenameField(
            model_name="EventBooking",
            old_name="event_price",
            new_name="price",
        ),
        migrations.RenameField(
            model_name="EventBooking",
            old_name="user",
            new_name="attendee",
        ),
        # ---------------------------------------------------------------
        # Match new model field definitions (blank=True) so migration state
        # lines up with events/models.py for the legacy fields that are kept
        # through this step.
        # ---------------------------------------------------------------
        migrations.AlterField(
            model_name="Event",
            name="event_type",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="Event",
            name="package1",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="Event",
            name="package2",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="Event",
            name="package3",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="Event",
            name="package4",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="Event",
            name="mob_number",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AlterField(
            model_name="EventBooking",
            name="event_booking_date",
            field=models.CharField(blank=True, max_length=10),
        ),
        # ---------------------------------------------------------------
        # New model: EventCategory (referenced by Event.category below).
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="EventCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "slug",
                    models.SlugField(blank=True, max_length=120, unique=True),
                ),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name_plural": "Event Categories",
            },
        ),
        # ---------------------------------------------------------------
        # New Event fields (additive). owner null=True until data migration.
        # slug unique=False until data migration backfills unique values.
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="Event",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="Event",
            name="slug",
            field=models.SlugField(blank=True, max_length=140),
        ),
        migrations.AddField(
            model_name="Event",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="events",
                to="events.eventcategory",
            ),
        ),
        migrations.AddField(
            model_name="Event",
            name="venue",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="Event",
            name="start_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="end_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="capacity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("under_review", "Under Review"),
                    ("approved", "Approved"),
                    ("published", "Published"),
                    ("live", "Live"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("rejected", "Rejected"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="Event",
            name="featured",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="Event",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="publish_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="review_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="Event",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # ---------------------------------------------------------------
        # New EventBooking fields (additive).
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="EventBooking",
            name="event_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="EventBooking",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="events.event",
            ),
        ),
        # ---------------------------------------------------------------
        # New models with FKs to Event / EventBooking.
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="EventInclusion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inclusions",
                        to="events.event",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order"],
                "verbose_name_plural": "Event Inclusions",
            },
        ),
        migrations.CreateModel(
            name="EventImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image", models.ImageField(upload_to="events/gallery")),
                ("caption", models.CharField(blank=True, max_length=200)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="events.event",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order"],
            },
        ),
        migrations.CreateModel(
            name="EventAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("action", models.CharField(max_length=50)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="events.event",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Review",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ]
                    ),
                ),
                ("comment", models.TextField(blank=True)),
                (
                    "moderation_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("hidden", "Hidden"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "attendee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "booking",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="review",
                        to="events.eventbooking",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to="events.event",
                    ),
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # Event Meta options (ordering + permissions).
        # ---------------------------------------------------------------
        migrations.AlterModelOptions(
            name="Event",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("can_approve_event", "Can approve events"),
                    ("can_reject_event", "Can reject events"),
                    ("can_publish_event", "Can publish events"),
                    ("can_force_cancel_event", "Can force cancel events"),
                    ("can_view_all_events", "Can view all events"),
                ],
            },
        ),
        # ---------------------------------------------------------------
        # Indexes matching events/models.py.
        # ---------------------------------------------------------------
        migrations.AddIndex(
            model_name="Event",
            index=models.Index(fields=["status"], name="events_even_status_8ffad6_idx"),
        ),
        migrations.AddIndex(
            model_name="Event",
            index=models.Index(fields=["owner"], name="events_even_owner_i_c8057d_idx"),
        ),
        migrations.AddIndex(
            model_name="Event",
            index=models.Index(fields=["category"], name="events_even_categor_298e0d_idx"),
        ),
        migrations.AddIndex(
            model_name="Event",
            index=models.Index(fields=["start_at"], name="events_even_start_a_759546_idx"),
        ),
        migrations.AddIndex(
            model_name="EventBooking",
            index=models.Index(fields=["attendee"], name="events_even_user_id_3e6ffc_idx"),
        ),
        migrations.AddIndex(
            model_name="EventBooking",
            index=models.Index(fields=["event"], name="events_even_event_i_54032d_idx"),
        ),
        migrations.AddIndex(
            model_name="EventBooking",
            index=models.Index(fields=["status"], name="events_even_status_2532db_idx"),
        ),
        migrations.AddIndex(
            model_name="EventBooking",
            index=models.Index(fields=["event_date"], name="events_even_event_d_6368ed_idx"),
        ),
        migrations.AddIndex(
            model_name="EventAuditLog",
            index=models.Index(fields=["event", "created_at"], name="events_even_event_i_de8a2e_idx"),
        ),
        migrations.AddIndex(
            model_name="Review",
            index=models.Index(fields=["event"], name="events_revi_event_i_a27f12_idx"),
        ),
        migrations.AddIndex(
            model_name="Review",
            index=models.Index(fields=["moderation_status"], name="events_revi_moderat_ce8687_idx"),
        ),
    ]
