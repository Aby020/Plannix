from django import forms

from .models import Event, EventBooking


class EventForm(forms.ModelForm):
    """Organizer event/package form.

    Plannix is a package-discovery platform: the organizer offers a package,
    and the customer later specifies the preferred booking date and location
    when requesting the package. So package creation carries no start/end
    date and no venue — those are captured on the customer's booking.
    """

    class Meta:
        model = Event
        fields = [
            'title', 'description', 'category', 'price', 'location',
            'capacity', 'contact_number', 'featured_image',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class EventBookingForm(forms.ModelForm):
    class Meta:
        model = EventBooking
        fields = ['name', 'email', 'number', 'event_date']
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
        }
