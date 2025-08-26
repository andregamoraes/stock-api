from django.db import models
##from decimal import Decimal

class Stock(models.Model):
    company_code = models.CharField(max_length=20, db_index=True)  # sem unique
    company_name = models.CharField(max_length=100)  # novo campo null=True,
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.company_code
