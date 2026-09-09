# Data migration: backfill Phase 1 fields from legacy columns.
#
# Runs AFTER the additive/rename migration 0009 and AFTER account_manager 0001
# (OrganizerProfile). All values are sourced from the legacy columns that were
# preserved (event_type, package1-4, mob_number, event_company_name,
# event_booking_date) so that no demo data is lost.
#
# Decision (documented): a dedicated system organizer 'plannix_platform' is
# created and every pre-existing event is assigned to it as its owner. The old
# schema had no owner concept; this single platform account keeps the existing
# events owned by a stable, real user and gives them a public "live" status so
# they remain visible. A real human admin can later re-assign ownership.
#
# This migration also backfills unique slugs for every event (the additive
# migration added slug as non-unique so existing rows could be populated; the
# cleanup migration 0011 re-adds the UNIQUE constraint once values are set).
from datetime import datetime

from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils.text import slugify

LEGACY_GROUPS = ("staff", "customer", "admin")


def _make_unique_slug(title, used):
    base = slugify(title) or "event"
    slug = base
    n = 1
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def backfill_events(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    EventCategory = apps.get_model("events", "EventCategory")
    EventInclusion = apps.get_model("events", "EventInclusion")
    EventBooking = apps.get_model("events", "EventBooking")
    OrganizerProfile = apps.get_model("account_manager", "OrganizerProfile")
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")

    # ------------------------------------------------------------------
    # 0. Groups
    # ------------------------------------------------------------------
    attendee_group, _ = Group.objects.get_or_create(name="Attendee")
    organizer_group, _ = Group.objects.get_or_create(name="EventOrganizer")
    admin_group, _ = Group.objects.get_or_create(name="Admin")

    # ------------------------------------------------------------------
    # 1. Categories from distinct event_type
    # ------------------------------------------------------------------
    category_by_name = {}
    for et in (
        Event.objects.exclude(event_type="")
        .values_list("event_type", flat=True)
        .distinct()
    ):
        category, _ = EventCategory.objects.get_or_create(
            name=et, defaults={"slug": slugify(et)}
        )
        category_by_name[et] = category

    # ------------------------------------------------------------------
    # 2. Dedicated platform organizer + owner assignment
    # ------------------------------------------------------------------
    platform_user, created = User.objects.get_or_create(
        username="plannix_platform",
        defaults={
            "email": "plannix_platform@plannix.app",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )
    if created:
        # Set an unusable password so the platform account cannot be used for
        # interactive logins (it exists only to own/organize events).
        platform_user.password = make_password(None)
        platform_user.save()
    platform_user.groups.add(organizer_group)
    OrganizerProfile.objects.get_or_create(
        user=platform_user,
        defaults={"business_name": "Plannix Platform", "is_verified": True},
    )

    # ------------------------------------------------------------------
    # 3 + 4. category backfill, status -> live, owner, unique slugs
    # ------------------------------------------------------------------
    used_slugs = set(Event.objects.exclude(slug="").values_list("slug", flat=True))
    for event in Event.objects.all():
        event.category = category_by_name.get(event.event_type)
        event.status = "live"
        event.owner = platform_user
        event.slug = _make_unique_slug(event.title, used_slugs)
        event.save(update_fields=["category", "status", "owner", "slug"])

    # ------------------------------------------------------------------
    # 5. Inclusions from package1-4
    # ------------------------------------------------------------------
    inclusion_count = 0
    for event in Event.objects.all():
        for idx, field in enumerate(("package1", "package2", "package3", "package4"), start=1):
            value = getattr(event, field, "") or ""
            if value.strip():
                EventInclusion.objects.create(
                    event=event, name=value.strip(), sort_order=idx
                )
                inclusion_count += 1

    # ------------------------------------------------------------------
    # 6 + 7. Booking event FK backfill + event_booking_date parsing
    # ------------------------------------------------------------------
    events_by_title = {e.title: e for e in Event.objects.all()}
    unmatched = []
    malformed = []
    for booking in EventBooking.objects.all():
        event = events_by_title.get(booking.event_title)
        if event is not None:
            booking.event = event
        else:
            unmatched.append(booking.event_title)
            booking.event = None

        parsed = None
        raw = (booking.event_booking_date or "").strip()
        if raw:
            try:
                parsed = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                malformed.append((booking.pk, raw))
        booking.event_date = parsed
        booking.save(update_fields=["event", "event_date"])

    # ------------------------------------------------------------------
    # 8. Role group membership for existing users
    # ------------------------------------------------------------------
    legacy_groups = {name: Group.objects.filter(name=name).first() for name in LEGACY_GROUPS}
    for user in User.objects.all():
        if user.pk == platform_user.pk:
            # Platform user is already an organizer.
            continue
        if user.is_superuser:
            user.groups.add(admin_group)
        if legacy_groups["staff"] and user.groups.filter(pk=legacy_groups["staff"].pk).exists():
            user.groups.add(organizer_group)
        if legacy_groups["customer"] and user.groups.filter(pk=legacy_groups["customer"].pk).exists():
            user.groups.add(attendee_group)
        if legacy_groups["admin"] and user.groups.filter(pk=legacy_groups["admin"].pk).exists():
            user.groups.add(admin_group)
        if not user.groups.exists():
            user.groups.add(attendee_group)
        # Move users out of the legacy groups into the new ones.
        for name, grp in legacy_groups.items():
            if grp is not None and user.groups.filter(pk=grp.pk).exists():
                user.groups.remove(grp)

    print(
        f"[data] categories={len(category_by_name)} inclusions={inclusion_count} "
        f"unmatched_bookings={len(unmatched)} malformed_dates={len(malformed)}"
    )
    if unmatched:
        print(f"[data] WARNING unmatched booking event_title values: {sorted(set(unmatched))}")
    if malformed:
        print(f"[data] WARNING malformed event_booking_date rows (pk, value): {malformed}")


def noop(apps, schema_editor):
    """Reverse is intentionally a no-op: backfilled data is non-destructive."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0009_rename_models_and_additive_fields"),
        ("account_manager", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_events, noop),
    ]
