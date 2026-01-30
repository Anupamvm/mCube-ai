"""
Forms for brokers app
"""

from django import forms


class CSVUploadForm(forms.Form):
    """Form for uploading CSV trade history files."""

    FILE_TYPE_CHOICES = [
        ('kotak_fno', 'Kotak F&O Gain/Loss'),
        ('breeze_fno', 'Breeze FNO Portfolio'),
    ]

    file_type = forms.ChoiceField(
        choices=FILE_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'file-type-select',
        }),
        help_text='Select the type of CSV file you are uploading'
    )

    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv',
            'id': 'csv-file-input',
        }),
        help_text='Upload a CSV file from your broker'
    )

    def clean_csv_file(self):
        """Validate the uploaded CSV file."""
        file = self.cleaned_data.get('csv_file')
        if file:
            # Check file extension
            if not file.name.lower().endswith('.csv'):
                raise forms.ValidationError('Only CSV files are allowed.')

            # Check file size (max 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size must be less than 10MB.')

        return file
