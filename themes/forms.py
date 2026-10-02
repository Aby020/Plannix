"""Forms for the Plannix themes module."""

from django import forms

from .models import Feedback


class FeedbackForm(forms.ModelForm):
    """Public feedback form.

    Validation is done here rather than by reading ``request.POST`` directly.
    Every field constraint on the model (lengths, the email format, and the
    10-digit phone shape) is enforced before ``save()`` is reached, so an
    oversized name or a malformed email returns a form error instead of being
    written to the database — on PostgreSQL an over-length value raises
    ``DataError`` and would otherwise surface as an HTTP 500.
    """

    class Meta:
        model = Feedback
        fields = ['name', 'email', 'number', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_number(self):
        """Validate the optional phone number as 10 digits.

        The field is required at the model level, so an empty submission is
        rejected here too. Digits-only is enforced to match the app-wide
        convention that a phone number is a bare 10-digit string.
        """
        number = self.cleaned_data['number'].strip()
        if not number:
            raise forms.ValidationError('Please enter your 10-digit mobile number.')
        if not number.isdigit() or len(number) != 10:
            raise forms.ValidationError('Please enter a valid 10-digit mobile number.')
        return number