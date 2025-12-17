# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_apicredential_id_alter_brokeraccount_id'),
    ]

    operations = [
        migrations.DeleteModel(
            name='APICredential',
        ),
    ]
