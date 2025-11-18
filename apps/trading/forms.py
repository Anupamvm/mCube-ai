"""
Trading Forms - Input Validation for Trading Views
"""

from django import forms
from decimal import Decimal
from datetime import date

from apps.trading.models import AutoTradeConfig


class AutoTradeConfigForm(forms.ModelForm):
    """
    Form for configuring auto-trade settings per strategy
    """

    class Meta:
        model = AutoTradeConfig
        fields = [
            'is_enabled',
            'auto_approve_threshold',
            'max_daily_positions',
            'max_daily_loss',
            'require_human_on_weekend',
            'require_human_on_high_vix',
            'vix_threshold',
        ]
        widgets = {
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_approve_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': '95.00'
            }),
            'max_daily_positions': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '10',
                'placeholder': '1'
            }),
            'max_daily_loss': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1000',
                'step': '100',
                'placeholder': '25000.00'
            }),
            'require_human_on_weekend': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_human_on_high_vix': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'vix_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '10',
                'max': '50',
                'step': '0.1',
                'placeholder': '18.0'
            }),
        }

    def clean_auto_approve_threshold(self):
        """Validate threshold is between 0 and 100"""
        threshold = self.cleaned_data.get('auto_approve_threshold')
        if threshold is not None:
            if threshold < 0 or threshold > 100:
                raise forms.ValidationError("Threshold must be between 0 and 100")
        return threshold

    def clean_max_daily_positions(self):
        """Validate max daily positions is positive"""
        max_positions = self.cleaned_data.get('max_daily_positions')
        if max_positions is not None and max_positions < 1:
            raise forms.ValidationError("Must allow at least 1 position per day")
        return max_positions

    def clean_max_daily_loss(self):
        """Validate max daily loss is positive"""
        max_loss = self.cleaned_data.get('max_daily_loss')
        if max_loss is not None and max_loss <= 0:
            raise forms.ValidationError("Max daily loss must be positive")
        return max_loss

    def clean_vix_threshold(self):
        """Validate VIX threshold is reasonable"""
        vix = self.cleaned_data.get('vix_threshold')
        if vix is not None:
            if vix < 10 or vix > 50:
                raise forms.ValidationError("VIX threshold should be between 10 and 50")
        return vix


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
