from django.db import models
import uuid


class Menu(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_name = models.CharField(max_length=200, null=False, blank=False)
    category = models.CharField(max_length=200, null=False, blank=False)
    cost_price = models.FloatField(null=False, blank=False)
    sales_price = models.FloatField(null=False, blank=False)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.item_name


class Sales(models.Model):
    """
    Represents a sale/order that can contain multiple items.
    This is the main transaction model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale_date = models.DateTimeField(auto_now_add=True)
    is_weekend = models.BooleanField(default=False)
    total_amount = models.FloatField(default=0.0)
    discount = models.FloatField(default=0.0)  # Sale-level discount
    final_amount = models.FloatField(default=0.0)
    
    class Meta:
        verbose_name_plural = "Sales"
    
    def __str__(self):
        return f"Sale {self.id} - {self.sale_date.strftime('%Y-%m-%d %H:%M')}"
    
    def calculate_totals(self):
        """Calculate total amount from all sale items"""
        items = self.sale_items.all()
        self.total_amount = sum(item.subtotal for item in items)
        self.final_amount = self.total_amount - self.discount
        self.save()


class SalesItem(models.Model):
    """
    Represents individual items within a sale.
    Multiple items can be sold in a single transaction.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sales, on_delete=models.CASCADE, related_name='sale_items')
    item = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField(null=False, blank=False)
    price_per_unit = models.FloatField(null=False, blank=False)
    discount = models.FloatField(default=0.0)  # Item-level discount
    subtotal = models.FloatField(null=False, blank=False)
    
    def __str__(self):
        return f"{self.quantity}x {self.item.item_name} in Sale {self.sale.id}"
    
    def save(self, *args, **kwargs):
        """Calculate subtotal before saving"""
        self.subtotal = (self.price_per_unit * self.quantity) - self.discount
        super().save(*args, **kwargs)