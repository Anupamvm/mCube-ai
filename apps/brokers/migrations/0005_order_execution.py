# Generated manually - Take ownership of Order and Execution models from orders app
# The database tables already exist in production, this just updates Django's model state.
# database_operations creates tables only when they don't exist (e.g. fresh test DBs).

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def _create_tables_if_not_exist(apps, schema_editor):
    """Create orders/executions tables only if they don't already exist.

    In production the tables exist from the old 'orders' app so this is a no-op.
    In fresh test databases (manage.py test) they must be created here.
    """
    existing = schema_editor.connection.introspection.table_names()
    if 'orders' not in existing:
        Order = apps.get_model('brokers', 'Order')
        schema_editor.create_model(Order)
    if 'executions' not in existing:
        Execution = apps.get_model('brokers', 'Execution')
        schema_editor.create_model(Execution)


class Migration(migrations.Migration):

    dependencies = [
        ('brokers', '0004_niftyoptionchain_call_delta_and_more'),
        ('accounts', '0001_initial'),
        ('positions', '0001_initial'),
    ]

    operations = [
        # Update Django's migration state to know about Order and Execution models.
        # In production, the tables were inherited from the old 'orders' app.
        # In fresh test databases, the RunPython below creates them if absent.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Order',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('order_type', models.CharField(max_length=20)),
                        ('direction', models.CharField(max_length=10)),
                        ('instrument', models.CharField(max_length=100)),
                        ('exchange', models.CharField(default='NSE', max_length=20)),
                        ('quantity', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                        ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                        ('trigger_price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                        ('status', models.CharField(db_index=True, default='PENDING', max_length=20)),
                        ('broker_order_id', models.CharField(blank=True, max_length=100)),
                        ('message', models.TextField(blank=True)),
                        ('filled_quantity', models.IntegerField(default=0)),
                        ('average_price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                        ('placed_at', models.DateTimeField(blank=True, null=True)),
                        ('filled_at', models.DateTimeField(blank=True, null=True)),
                        ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                        ('purpose', models.CharField(blank=True, max_length=50)),
                        ('notes', models.TextField(blank=True)),
                        ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='accounts.brokeraccount')),
                        ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='positions.position')),
                    ],
                    options={
                        'verbose_name': 'Order',
                        'verbose_name_plural': 'Orders',
                        'db_table': 'orders',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='Execution',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('execution_id', models.CharField(max_length=100, unique=True)),
                        ('quantity', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                        ('price', models.DecimalField(decimal_places=2, max_digits=15)),
                        ('exchange_timestamp', models.DateTimeField()),
                        ('exchange', models.CharField(blank=True, max_length=20)),
                        ('transaction_type', models.CharField(max_length=10)),
                        ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='brokers.order')),
                    ],
                    options={
                        'verbose_name': 'Execution',
                        'verbose_name_plural': 'Executions',
                        'db_table': 'executions',
                        'ordering': ['-exchange_timestamp'],
                    },
                ),
            ],
            database_operations=[],  # No schema changes — tables exist in prod
        ),
        # Create tables only when they're missing (e.g. fresh test databases).
        # In production this is a no-op because the tables already exist.
        migrations.RunPython(
            _create_tables_if_not_exist,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
