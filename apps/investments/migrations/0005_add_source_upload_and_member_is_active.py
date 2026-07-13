# Generated manually to match project migration style

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("investments", "0004_add_portfolio_type_and_products_updated"),
    ]

    operations = [
        migrations.AddField(
            model_name="familymember",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="investmentproduct",
            name="source_upload",
            field=models.ForeignKey(
                blank=True,
                help_text="Most recent upload that created or updated this holding",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sourced_products",
                to="investments.casupload",
            ),
        ),
    ]
