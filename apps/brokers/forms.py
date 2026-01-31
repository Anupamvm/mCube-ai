"""
Forms for brokers app
"""

from django import forms


class MultipleFileInput(forms.ClearableFileInput):
    """Custom widget for multiple file uploads."""
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Custom field for multiple file uploads."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


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

    csv_files = MultipleFileField(
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': '.csv',
            'id': 'csv-file-input',
            'multiple': True,
        }),
        help_text='Upload one or more CSV files from your broker'
    )

    def clean_csv_files(self):
        """Validate the uploaded CSV files."""
        files = self.cleaned_data.get('csv_files', [])
        validated_files = []

        for file in files:
            if file:
                # Check file extension
                if not file.name.lower().endswith('.csv'):
                    raise forms.ValidationError(f'Only CSV files are allowed. "{file.name}" is not a CSV file.')

                # Check file size (max 10MB)
                if file.size > 10 * 1024 * 1024:
                    raise forms.ValidationError(f'File "{file.name}" exceeds 10MB limit.')

                validated_files.append(file)

        if not validated_files:
            raise forms.ValidationError('Please select at least one CSV file.')

        return validated_files
