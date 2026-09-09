"""Centralized event lifecycle transitions.

Every status change flows through this module so transitions are explicit,
auditable and enforce business rules in one place.
"""
from django.db import transaction
from django.utils import timezone

from .models import Event, EventAuditLog, EventBooking, EventInclusion


VALID_TRANSITIONS = {
    'draft': ['under_review'],
    'under_review': ['approved', 'rejected'],
    'approved': ['published', 'draft'],
    'published': ['live', 'draft'],
    'live': ['completed', 'cancelled'],
    'completed': [],
    'cancelled': [],
    'rejected': ['under_review'],
}


def _log_transition(event, actor, action, from_status, to_status, reason=''):
    EventAuditLog.objects.create(
        event=event,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
    )


def _validate_submit(event):
    errors = []
    if not event.title:
        errors.append('Title is required.')
    if not event.description:
        errors.append('Description is required.')
    if not event.category:
        errors.append('Category is required.')
    # Package creation carries no start/end dates or venue — the customer
    # supplies their preferred booking date and event location at booking time.
    if not event.location:
        errors.append('Location is required.')
    if event.capacity is not None and event.capacity <= 0:
        errors.append('Capacity must be a positive number.')
    return errors


def submit(event, user):
    """DRAFT -> UNDER_REVIEW. Validates required fields."""
    if event.status != 'draft':
        raise ValueError(f'Cannot submit event in "{event.status}" status.')
    errors = _validate_submit(event)
    if errors:
        raise ValueError('; '.join(errors))
    old_status = event.status
    event.status = 'under_review'
    event.submitted_at = timezone.now()
    event.rejection_reason = ''
    event.save(update_fields=['status', 'submitted_at', 'rejection_reason', 'updated_at'])
    _log_transition(event, user, 'submit', old_status, 'under_review')
    return event


def approve(event, admin, notes=''):
    """UNDER_REVIEW -> APPROVED."""
    if event.status != 'under_review':
        raise ValueError(f'Cannot approve event in "{event.status}" status.')
    old_status = event.status
    event.status = 'approved'
    event.approved_at = timezone.now()
    event.review_notes = notes
    event.save(update_fields=['status', 'approved_at', 'review_notes', 'updated_at'])
    _log_transition(event, admin, 'approve', old_status, 'approved', notes)
    return event


def reject(event, admin, reason=''):
    """UNDER_REVIEW -> REJECTED. Reason is required."""
    if event.status != 'under_review':
        raise ValueError(f'Cannot reject event in "{event.status}" status.')
    if not reason:
        raise ValueError('Rejection reason is required.')
    old_status = event.status
    event.status = 'rejected'
    event.rejection_reason = reason
    event.save(update_fields=['status', 'rejection_reason', 'updated_at'])
    _log_transition(event, admin, 'reject', old_status, 'rejected', reason)
    return event


def resubmit(event, organizer):
    """REJECTED -> UNDER_REVIEW."""
    if event.status != 'rejected':
        raise ValueError(f'Cannot resubmit event in "{event.status}" status.')
    old_status = event.status
    event.status = 'under_review'
    event.submitted_at = timezone.now()
    event.rejection_reason = ''
    event.save(update_fields=['status', 'submitted_at', 'rejection_reason', 'updated_at'])
    _log_transition(event, organizer, 'resubmit', old_status, 'under_review')
    return event


def publish(event, admin):
    """APPROVED -> PUBLISHED."""
    if event.status != 'approved':
        raise ValueError(f'Cannot publish event in "{event.status}" status.')
    old_status = event.status
    event.status = 'published'
    event.publish_at = timezone.now()
    event.save(update_fields=['status', 'publish_at', 'updated_at'])
    _log_transition(event, admin, 'publish', old_status, 'published')
    return event


def approve_and_go_live(event, admin, notes=''):
    """UNDER_REVIEW -> LIVE in one explicit admin action.

    Marketplace packages are approved, published and made bookable in a
    single decision. Each step still runs through its audited transition so
    the review trail records 'approve', 'publish' and 'go_live' rows.
    """
    approve(event, admin, notes)
    publish(event, admin)
    go_live(event, admin)
    return event


def publish_and_go_live(event, admin):
    """APPROVED (or PUBLISHED) -> LIVE.

    Completes packages that passed the older staged-approval flow and are
    stuck in 'approved'/'published'. Approval already happened; this only
    finishes the remaining publishing steps.
    """
    if event.status == 'approved':
        publish(event, admin)
    go_live(event, admin)
    return event


def go_live(event, actor):
    """PUBLISHED -> LIVE. MVP: admin only."""
    if event.status != 'published':
        raise ValueError(f'Cannot go live from "{event.status}" status.')
    old_status = event.status
    event.status = 'live'
    event.save(update_fields=['status', 'updated_at'])
    _log_transition(event, actor, 'go_live', old_status, 'live')
    return event


def complete(event, actor=None):
    """LIVE -> COMPLETED. Typically called by system/cron."""
    if event.status != 'live':
        raise ValueError(f'Cannot complete event in "{event.status}" status.')
    old_status = event.status
    event.status = 'completed'
    event.save(update_fields=['status', 'updated_at'])
    _log_transition(event, actor, 'complete', old_status, 'completed')
    # Finalize bookings: confirmed->completed, pending->cancelled
    EventBooking.objects.filter(event=event, status='confirmed').update(status='completed')
    EventBooking.objects.filter(event=event, status='pending').update(status='cancelled')
    return event


def cancel(event, actor, reason=''):
    """LIVE -> CANCELLED. Auto-cancels non-cancelled bookings."""
    if event.status not in ('live', 'published'):
        raise ValueError(f'Cannot cancel event in "{event.status}" status.')
    old_status = event.status
    event.status = 'cancelled'
    event.save(update_fields=['status', 'updated_at'])
    _log_transition(event, actor, 'cancel', old_status, 'cancelled', reason)
    # Auto-cancel non-cancelled bookings
    EventBooking.objects.filter(event=event).exclude(status='cancelled').update(status='cancelled')
    return event


def publish_live(event, actor):
    """DRAFT -> LIVE for an organizer whose Organization is approved.

    Organization approval is the only admin gate: an approved organizer
    publishes a finished package directly, with no second admin review.
    """
    org = getattr(actor, 'organization', None)
    if org is None or not org.is_approved:
        raise ValueError(
            'Your Organization must be approved before publishing event packages.'
        )
    if event.status != 'draft':
        raise ValueError(f'Cannot publish event in "{event.status}" status.')
    old_status = event.status
    event.status = 'live'
    event.publish_at = timezone.now()
    event.save(update_fields=['status', 'publish_at', 'updated_at'])
    _log_transition(event, actor, 'publish_live', old_status, 'live')
    return event


def auto_publish_org_packages(org, actor):
    """Flip an approved Organization's packages to LIVE.

    Called when an Organization is approved — its packages that are still
    draft, under review, approved or published become live immediately,
    because Organization approval is the only gate. Packages already live,
    completed or cancelled are left untouched.
    """
    events = Event.objects.filter(
        organization=org,
        status__in=('draft', 'under_review', 'approved', 'published'),
    )
    for event in events:
        old_status = event.status
        event.status = 'live'
        event.publish_at = timezone.now()
        event.save(update_fields=['status', 'publish_at', 'updated_at'])
        _log_transition(
            event, actor, 'auto_publish', old_status, 'live',
            'Organization approved — package published live',
        )
    return events


def edit_sets_draft(event):
    """Any edit to APPROVED/PUBLISHED/LIVE resets to DRAFT. MVP default."""
    if event.status in ('approved', 'published', 'live'):
        old_status = event.status
        event.status = 'draft'
        event.approved_at = None
        event.publish_at = None
        event.submitted_at = None
        event.rejection_reason = ''
        event.save(update_fields=[
            'status', 'approved_at', 'publish_at', 'submitted_at',
            'rejection_reason', 'updated_at',
        ])
        _log_transition(event, None, 'edit_reset', old_status, 'draft',
                        'Edit while in review/published/live — reset to draft')
        return True
    return False
