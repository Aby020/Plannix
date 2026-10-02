from django import forms
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from .models import Event, EventBooking


def _image_field():
    """An ImageField with an extension allowlist and a human-readable error."""
    return forms.ImageField(
        required=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp'],
            ),
        ],
        error_messages={
            'invalid_image': _(
                'Upload a valid image (JPG, PNG or WebP) of at most 5 MB. '
                'The file you uploaded was either not an image, was corrupted, '
                'or exceeded the maximum size.'
            ),
        },
    )


def validate_upload_size(uploaded_file):
    """Reject a file larger than settings.MAX_UPLOAD_SIZE.

    Pillow already blocks non-images and decompression bombs; this caps the
    bytes-on-disk case, which is what actually fills the volume.
    """
    if uploaded_file.size > settings.MAX_UPLOAD_SIZE:
        raise forms.ValidationError(
            _('Image must be 5 MB or smaller (got %(size).1f MB).'),
            params={'size': uploaded_file.size / (1024 * 1024)},
        )


class EventForm(forms.ModelForm):
    """Organizer event/package form.

    Plannix is a package-discovery platform: the organizer offers a package,
    and the customer later specifies the preferred booking date and location
    when requesting the package. So package creation carries no start/end
    date and no venue — those are captured on the customer's booking.
    """

    # Redefined so uploads are capped and extension-checked before they land.
    featured_image = _image_field()

    class Meta:
        model = Event
        fields = [
            'title', 'description', 'category', 'price', 'location',
            'capacity', 'contact_number', 'featured_image',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_featured_image(self):
        image = self.cleaned_data['featured_image']
        validate_upload_size(image)
        return image


class EventBookingForm(forms.ModelForm):
    class Meta:
        model = EventBooking
        fields = ['name', 'email', 'number', 'event_date']
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
        }
