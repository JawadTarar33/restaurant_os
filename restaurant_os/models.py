# ===============================
# models.py - COMPLETE FILE
# ===============================

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
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
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


# ============================
# Restaurant & Menu Models
# ============================

class Restaurant(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='restaurants')

    def __str__(self):
        return self.name


class Branch(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.TextField()
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='managed_branches')
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Branches"

    def __str__(self):
        return f"{self.name} - {self.city}"


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
    total_sold = models.PositiveIntegerField(default=0)
    avg_daily_sales = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    predicted_demand_next_week = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


# ============================
# Orders & Sales (Existing)
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
        self.menu_item.total_sold += self.quantity
        self.menu_item.save(update_fields=['total_sold'])

    def __str__(self):
        return f"{self.menu_item.name} x {self.quantity}"


# ============================
# POS System (NEW)
# ============================

class Customer(models.Model):
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.contact}"


class POSSale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('digital', 'Digital Wallet'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='pos_sales')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # NEW: Offline support fields
    offline_id = models.CharField(max_length=100, blank=True, null=True, unique=True, db_index=True)
    synced_at = models.DateTimeField(blank=True, null=True)
    is_offline_sale = models.BooleanField(default=False)

    def __str__(self):
        return f"Sale #{self.id} - {self.branch.name}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['offline_id']),
            models.Index(fields=['branch', 'created_at']),
        ]


# NEW: Sync Log Model
class SyncLog(models.Model):
    EVENT_TYPES = [
        ('sync_start', 'Sync Started'),
        ('sync_success', 'Sync Success'),
        ('sync_failure', 'Sync Failure'),
        ('auto_sync', 'Auto Sync'),
        ('manual_sync', 'Manual Sync'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='sync_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    sales_synced = models.IntegerField(default=0)
    sales_failed = models.IntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.event_type} - {self.timestamp}"

class POSSaleItem(models.Model):
    sale = models.ForeignKey(POSSale, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)


# ============================
# Inventory & Suppliers
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
    quantity_used_per_item = models.DecimalField(max_digits=10, decimal_places=2)

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


# ============================
# Daily Sales & Analytics
# ============================

class DailySales(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='daily_sales')
    date = models.DateField(default=timezone.now)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        unique_together = ('restaurant', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.restaurant.name} - {self.date}"


class BranchDailySales(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='daily_reports')
    date = models.DateField()
    revenue = models.DecimalField(max_digits=12, decimal_places=2)
    transactions = models.IntegerField()
    customer_footfall = models.IntegerField(default=0)
    avg_ticket_size = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['branch', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.branch.name} - {self.date}"


# ============================
# AI Forecasting (NEW)
# ============================

class BranchForecast(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField()
    predicted_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    predicted_growth = models.DecimalField(max_digits=5, decimal_places=2)
    confidence_score = models.IntegerField()
    factors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['branch', 'forecast_date']

    def __str__(self):
        return f"{self.branch.name} - {self.forecast_date}"


class BranchComparison(models.Model):
    date = models.DateField()
    branch_1 = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='comparisons_as_b1')
    branch_2 = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='comparisons_as_b2')
    metric = models.CharField(max_length=50)
    branch_1_value = models.DecimalField(max_digits=12, decimal_places=2)
    branch_2_value = models.DecimalField(max_digits=12, decimal_places=2)
    difference_pct = models.DecimalField(max_digits=5, decimal_places=2)
    insight = models.TextField()
    severity = models.CharField(max_length=20, choices=[
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical')
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.branch_1.name} vs {self.branch_2.name}"


# ============================
# Staff Management
# ============================

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
        return f"{self.user.full_name or self.user.email} @ {self.restaurant.name}"
