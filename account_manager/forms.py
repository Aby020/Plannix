"""Forms for the Plannix account manager."""
from django.contrib.auth.forms import PasswordResetForm

from Plannix.emails import send_password_reset_email


class PlannixPasswordResetForm(PasswordResetForm):
    """Django's built-in password reset form, routed through the Plannix email
    service so reset emails share the same branded pipeline and are testable via
    the mail outbox.

    All no-enumeration / expiring-token behaviour comes from the base form:
    the response never reveals whether an email exists, and the token is
    single-use and time-limited by ``PASSWORD_RESET_TIMEOUT``.
    """

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        send_password_reset_email(to_email, context)