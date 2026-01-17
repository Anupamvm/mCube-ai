# Generated manually for adding image_url field to NewsArticle

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0007_make_contract_fields_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='newsarticle',
            name='image_url',
            field=models.URLField(blank=True, help_text='Article image URL', max_length=1000),
        ),
    ]
