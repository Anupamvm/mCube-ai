# Generated manually - Take ownership of Order and Execution models from orders app
# The database tables already exist, this just updates Django's model state

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('brokers', '0004_niftyoptionchain_call_delta_and_more'),
        ('accounts', '0001_initial'),
        ('positions', '0001_initial'),
    ]

    operations = [
        # Use SeparateDatabaseAndState to only update state, not database
        # since tables already exist from the old 'orders' app
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
            database_operations=[],  # No database changes needed - tables exist
        ),
    ]
