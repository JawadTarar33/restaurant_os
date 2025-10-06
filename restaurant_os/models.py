from django.db import models
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings



# ============================
#  User & Role Management
# ============================

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('owner', 'Restaurant Owner'),
        ('manager', 'Manager'),
        ('staff', 'Staff'),
    ]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.full_name or self.email} ({self.role})"

    @property
    def is_owner(self):
        return self.role == 'owner'

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_admin(self):
        return self.role == 'admin' or self.is_superuser
    






# ============================
# 1. Restaurant & Menu Models
# ============================

class Restaurant(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='restaurants'
    )

    def __str__(self):
        return self.name


class MenuCategory(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_categories')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.restaurant.name} - {self.name}"


class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_items')
    category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    available = models.BooleanField(default=True)
    total_sold = models.PositiveIntegerField(default=0)  # Track popularity
    avg_daily_sales = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    predicted_demand_next_week = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


# ============================
# 2. Orders & Sales
# ============================

class Order(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(default=timezone.now)
    table_number = models.CharField(max_length=10, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"Order #{self.id} - {self.restaurant.name}"

    def calculate_total(self):
        total = sum(item.quantity * item.price for item in self.items.all())
        self.total_amount = total
        self.save()
        return total


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self.price:
            self.price = self.menu_item.price
        super().save(*args, **kwargs)

        # Update menu item popularity count
        self.menu_item.total_sold += self.quantity
        self.menu_item.save(update_fields=['total_sold'])

        # Deduct inventory based on usage (if defined)
        for usage in self.menu_item.inventory_usages.all():
            required_qty = usage.quantity_used_per_item * Decimal(self.quantity)
            inventory = usage.inventory_item
            inventory.quantity_in_stock -= required_qty
            inventory.save()

            # Trigger reorder if low
            if inventory.quantity_in_stock <= inventory.reorder_level:
                InventoryOrder.auto_reorder(inventory)

    def __str__(self):
        return f"{self.menu_item.name} x {self.quantity}"


# ============================
# 3. Inventory & Suppliers
# ============================

class Supplier(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


class InventoryItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='inventory')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_items')
    name = models.CharField(max_length=100)
    quantity_in_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="kg")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    last_restock_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.quantity_in_stock}{self.unit})"


class InventoryUsage(models.Model):
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='usages')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='inventory_usages')
    quantity_used_per_item = models.DecimalField(max_digits=10, decimal_places=2)  # e.g., 0.2kg per burger

    def __str__(self):
        return f"{self.menu_item.name} uses {self.quantity_used_per_item}{self.inventory_item.unit} of {self.inventory_item.name}"


class InventoryOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='inventory_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='orders')
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order_date = models.DateTimeField(default=timezone.now)
    received_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Order {self.id} - {self.inventory_item.name} ({self.status})"

    @classmethod
    def auto_reorder(cls, inventory_item):
        """Automatically create a reorder when stock falls below threshold."""
        if not inventory_item.supplier:
            return  # No supplier to reorder from

        existing_order = cls.objects.filter(
            inventory_item=inventory_item, status__in=['pending', 'ordered']
        ).exists()
        if existing_order:
            return  # Avoid duplicate reorders

        reorder = cls.objects.create(
            restaurant=inventory_item.restaurant,
            supplier=inventory_item.supplier,
            inventory_item=inventory_item,
            quantity_ordered=inventory_item.reorder_quantity,
            status='pending'
        )
        print(f"Auto-reorder created for {inventory_item.name} ({inventory_item.restaurant.name})")
        return reorder


# ============================
# 4. Daily Sales Aggregation
# ============================

class DailySales(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='daily_sales')
    date = models.DateField(default=timezone.now)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    most_popular_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='most_popular_days')

    temperature = models.FloatField(blank=True, null=True)
    weather = models.CharField(max_length=50, blank=True, null=True)
    is_holiday = models.BooleanField(default=False)
    promotions = models.BooleanField(default=False)

    class Meta:
        unique_together = ('restaurant', 'date')
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.total_orders > 0 and not self.avg_order_value:
            self.avg_order_value = self.total_sales / Decimal(self.total_orders)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.restaurant.name} - {self.date} - {self.total_sales}"


# ============================
# 5. Forecasting Models
# ============================

class WeeklyForecast(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField(default=timezone.now)
    start_date = models.DateField()
    end_date = models.DateField()
    model_used = models.CharField(max_length=100, default="Prophet")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Forecast ({self.model_used}) for {self.restaurant.name} [{self.start_date} - {self.end_date}]"


class ForecastResult(models.Model):
    forecast = models.ForeignKey(WeeklyForecast, on_delete=models.CASCADE, related_name='results')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    predicted_sales = models.DecimalField(max_digits=12, decimal_places=2)
    lower_bound = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        unique_together = ('forecast', 'date', 'menu_item')
        ordering = ['date']

    def __str__(self):
        return f"{self.date} → {self.predicted_sales}"


#=============================
# Staff Management
#=============================

class RestaurantStaff(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='staff_members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_restaurants')
    role = models.CharField(max_length=50, choices=[
        ('manager', 'Manager'),
        ('cashier', 'Cashier'),
        ('chef', 'Chef'),
        ('waiter', 'Waiter'),
    ])
    date_assigned = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('restaurant', 'user')

    def __str__(self):
        return f"{self.user.full_name or self.user.email} - {self.role} @ {self.restaurant.name}"