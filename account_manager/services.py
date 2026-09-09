"""Centralized Organization lifecycle transitions.

Mirrors ``events.services``: every status change flows through this module so
approvals are explicit, validated, and enforce business rules in one place.
Approval notes / rejection reasons live on the Organization row itself.
"""
from django.utils import timezone


def _validate_submission(org):
    errors = []
    if not org.name:
        errors.append('Organization name is required.')
    if not org.description:
        errors.append('A short description of the organization is required.')
    if not org.contact_number:
        errors.append('A contact number is required so customers can reach you.')
    return errors


def submit_organization(org):
    """PENDING/REJECTED -> PENDING (submitted for admin review)."""
    if org.status not in ('pending', 'rejected'):
        raise ValueError(f'Cannot submit an organization in "{org.status}" status.')
    errors = _validate_submission(org)
    if errors:
        raise ValueError('; '.join(errors))
    org.status = 'pending'
    org.submitted_at = timezone.now()
    org.rejection_reason = ''
    org.save(update_fields=['status', 'submitted_at', 'rejection_reason', 'updated_at'])
    return org


def approve_organization(org, admin, notes=''):
    """PENDING -> APPROVED.

    Organization approval is the single marketplace gate: once approved, the
    organizer's existing packages are auto-published live (no second admin
    approval), and new packages are created live.
    """
    if org.status != 'pending':
        raise ValueError(f'Cannot approve an organization in "{org.status}" status.')
    org.status = 'approved'
    org.approved_at = timezone.now()
    org.review_notes = notes
    org.save(update_fields=['status', 'approved_at', 'review_notes', 'updated_at'])

    # Auto-publish the org's packages that are still awaiting a decision.
    from events.services import auto_publish_org_packages
    auto_publish_org_packages(org, admin)

    return org


def reject_organization(org, admin, reason=''):
    """PENDING -> REJECTED. A reason is required.

    ``submitted_at`` is cleared so the rejection reads as "no longer in
    review": the template shows the Submit button again and the org drops
    out of the pending approval queue until the organizer resubmits.
    """
    if org.status != 'pending':
        raise ValueError(f'Cannot reject an organization in "{org.status}" status.')
    if not reason:
        raise ValueError('A rejection reason is required.')
    org.status = 'rejected'
    org.rejection_reason = reason
    org.submitted_at = None
    org.approved_at = None
    org.save(update_fields=[
        'status', 'rejection_reason', 'submitted_at', 'approved_at', 'updated_at',
    ])
    return org


def resubmit_organization(org):
    """REJECTED -> PENDING (re-stamp submission, clear reason)."""
    return submit_organization(org)