from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='余额'),
        ),
        migrations.AddField(
            model_name='user',
            name='score',
            field=models.IntegerField(default=20, verbose_name='点数'),
        ),
    ]
