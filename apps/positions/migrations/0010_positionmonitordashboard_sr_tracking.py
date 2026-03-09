from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("positions", "0009_add_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="positionmonitordashboard",
            name="sr_tracking",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    "Intraday S/R engine state: "
                    "{session_low, session_high, last_sr_computed_at, sr_cache, "
                    "condition_b_met_at, gap_detected}"
                ),
            ),
        ),
    ]
