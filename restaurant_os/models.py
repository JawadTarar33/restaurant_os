from django.db import models
import uuid


class Menu(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable = False)
    item_name= models.CharField(max_length=200, null= False, blank= False)
    category = models.CharField(max_length=200, null=False, blank=False)
    cost_price = models.FloatField(null=False, blank = False)
    sales_price = models.FloatField(null=False, blank= False)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.item_name


class Sales(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_id = models.ForeignKey(Menu, on_delete=models.CASCADE)
    sale_date = models.DateTimeField(auto_now_add=True)
    quantity = models.IntegerField(null=False, blank=False)
    price_per_unit = models.FloatField(null=False, blank=False)
    discount = models.FloatField(default=0.0)
    is_weekend = models.BooleanField(default=False)
    total_amount = models.FloatField(null=False, blank=False)

    def __str__(self):
        return f"Sale of {self.item_id.item_name} on {self.sale_date}"
    


