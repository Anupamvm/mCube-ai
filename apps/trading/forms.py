"""
Trading Forms - Input Validation for Trading Views
"""

from django import forms
from decimal import Decimal
from datetime import date


class ManualTriggerForm(forms.Form):
    """
    Form for manual trade trigger inputs
    """
    ALGORITHM_CHOICES = [
        ('futures', 'ICICI Futures Algorithm'),
        ('strangle', 'Nifty Strangle Generator'),
        ('verify', 'Verify Future Trade'),
    ]

    algorithm_type = forms.ChoiceField(
        choices=ALGORITHM_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True
    )

    symbol = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'RELIANCE (for verify only)'
        })
    )

    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    strike_deviation = forms.DecimalField(
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '5.0',
            'step': '0.5'
        })
    )

    def clean_expiry_date(self):
        """Ensure expiry date is in the future"""
        expiry = self.cleaned_data.get('expiry_date')
        if expiry and expiry < date.today():
            raise forms.ValidationError("Expiry date must be in the future")
        return expiry

    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        algorithm = cleaned_data.get('algorithm_type')

        # Verify algorithm requires symbol and expiry
        if algorithm == 'verify':
            if not cleaned_data.get('symbol'):
                raise forms.ValidationError("Symbol is required for Verify Future Trade")
            if not cleaned_data.get('expiry_date'):
                raise forms.ValidationError("Expiry date is required for Verify Future Trade")

        return cleaned_data


class TradeSuggestionRejectForm(forms.Form):
    """
    Form for rejecting a trade suggestion with reason
    """
    rejection_reason = forms.CharField(
        min_length=10,
        max_length=500,
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Please provide a reason for rejection (minimum 10 characters)...'
        }),
        help_text="Explain why this trade suggestion is being rejected"
    )

    def clean_rejection_reason(self):
        """Validate rejection reason is meaningful"""
        reason = self.cleaned_data.get('rejection_reason')
        if reason:
            # Check for meaningful content (not just spaces)
            if len(reason.strip()) < 10:
                raise forms.ValidationError("Rejection reason must be at least 10 characters")

            # Check it's not just repeated characters
            if len(set(reason.strip())) < 5:
                raise forms.ValidationError("Please provide a meaningful rejection reason")

        return reason.strip()
