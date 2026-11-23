from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    nickname = models.CharField('昵称', max_length=64, blank=True, default='')
    avatar = models.CharField('头像', max_length=512, blank=True, default='')
    balance = models.DecimalField('余额', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    score = models.IntegerField('点数', default=20)

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def display_name(self):
        return self.nickname or self.username
