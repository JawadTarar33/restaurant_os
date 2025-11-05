# ===============================
# models.py - FULLY UPDATED FOR ALL VIEWSETS
# ===============================

from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from decimal import Decimal
from django.conf import settings
import uuid 
from uuid import uuid4

# =========================
# USER MODEL
# =========================
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("staff", "Staff"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="staff")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    assigned_branches = models.ManyToManyField("Branch", blank=True, related_name="staff_members")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.full_name} ({self.role})"
# =========================
# RESTAURANT STRUCTURE
# =========================
class Restaurant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="restaurants")
    is_active = models.BooleanField(default=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="PKR")

    def __str__(self):
        return self.name


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, related_name='branches')
    
    # Core branch info
    branch_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # New fields
    number_of_employees = models.PositiveIntegerField(default=0)
    opening_hours = models.CharField(max_length=100, blank=True, null=True)  # e.g. "9 AM - 11 PM"
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_branches',
        limit_choices_to={'role__in': ['manager', 'staff']},
        help_text="Assign a manager to this branch"
    )

    # Status + metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.branch_name} - {self.city}"


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"

class MenuItem(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
        ('out_of_stock', 'Out of Stock'),
        ('discontinued', 'Discontinued'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    restaurant = models.ForeignKey("Restaurant", on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey("Category", on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    # ✅ Add both cost and sale prices
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Internal cost of the item")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price shown to customers")

    # ✅ Replace 'available' boolean with more flexible 'status'
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    # ✅ Image URL
    image_url = models.URLField(blank=True, null=True)

    # ✅ Preparation time (in minutes)
    preparation_time = models.PositiveIntegerField(default=5, help_text="Time in minutes")

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def profit_margin(self):
        """Optional: Compute profit per item."""
        return self.sale_price - self.cost_price


# =========================
# CUSTOMERS & POS SALES
# =========================
class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=50, unique=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class POSSale(models.Model):
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("wallet", "Digital Wallet"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="sales")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    offline_sale_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"POS Sale #{self.id} ({self.branch.name})"


class POSSaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sale = models.ForeignKey(POSSale, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.menu_item.name} x{self.quantity}"


# =========================
# DAILY SALES & ANALYTICS
# =========================
class BranchDailySales(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="daily_sales")
    date = models.DateField(default=timezone.now)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transactions = models.PositiveIntegerField(default=0)
    customer_footfall = models.PositiveIntegerField(default=0)
    avg_ticket_size = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = ("branch", "date")

    def __str__(self):
        return f"{self.branch.name} - {self.date}"


# =========================
# FORECASTING
# =========================
class BranchForecast(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="forecasts")
    forecast_date = models.DateField()
    predicted_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    predicted_growth = models.DecimalField(max_digits=6, decimal_places=2)
    confidence_score = models.DecimalField(max_digits=4, decimal_places=2)
    factors = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.branch.name} Forecast ({self.forecast_date})"



# =========================
# BRANCH COMPARISON
# =========================
class BranchComparison(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    branch_1 = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="comparisons_as_branch1")
    branch_2 = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="comparisons_as_branch2")
    comparison_date = models.DateField(default=timezone.now)
    metric = models.CharField(max_length=50, default="revenue")  # revenue, transactions, avg_ticket_size, etc.
    branch_1_value = models.DecimalField(max_digits=12, decimal_places=2)
    branch_2_value = models.DecimalField(max_digits=12, decimal_places=2)
    difference = models.DecimalField(max_digits=12, decimal_places=2)
    percentage_change = models.DecimalField(max_digits=6, decimal_places=2)
    analysis_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Comparison: {self.branch_1.name} vs {self.branch_2.name} ({self.comparison_date})"



# =========================
# SUPPLIERS & INVENTORY
# =========================
class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


class InventoryItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="inventory")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    name = models.CharField(max_length=100)
    quantity_in_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="kg")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    last_restock_date = models.DateField(blank=True, null=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"

    def deduct_quantity(self, quantity, transaction_type="sale", user=None, pos_sale=None, notes=None):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if self.quantity_in_stock < quantity:
            raise ValueError(f"Insufficient stock: {self.name}")

        previous_qty = self.quantity_in_stock
        self.quantity_in_stock -= quantity
        self.save(update_fields=["quantity_in_stock"])

        InventoryTransaction.objects.create(
            inventory_item=self,
            transaction_type=transaction_type,
            quantity=quantity,
            unit=self.unit,
            previous_quantity=previous_qty,
            new_quantity=self.quantity_in_stock,
            performed_by=user,
            pos_sale=pos_sale,
            notes=notes,
        )


class InventoryTransaction(models.Model):
    TRANSACTION_TYPES = [
        ("sale", "Sale Deduction"),
        ("restock", "Restock"),
        ("adjustment", "Manual Adjustment"),
        ("waste", "Waste/Spoilage"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20)
    previous_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="inventory_logs")
    pos_sale = models.ForeignKey(POSSale, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_txn")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inventory_item.name} ({self.transaction_type})"


# =========================
# INVENTORY ORDERS
# =========================
class InventoryOrder(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="inventory_orders")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_orders")
    created_at = models.DateTimeField(auto_now_add=True)
    expected_delivery_date = models.DateField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Order #{self.id} - {self.supplier.name if self.supplier else 'No Supplier'}"

    def update_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save(update_fields=["total_amount"])


class InventoryOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    order = models.ForeignKey(InventoryOrder, on_delete=models.CASCADE, related_name="items")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="order_items")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        if self.order:
            self.order.update_total()

    def __str__(self):
        return f"{self.inventory_item.name} x {self.quantity} ({self.order.id})"


# =========================
# RECIPES
# =========================
class Recipe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    menu_item = models.OneToOneField(MenuItem, on_delete=models.CASCADE, related_name="recipe")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    preparation_time = models.IntegerField(default=0)
    cooking_time = models.IntegerField(default=0)
    servings = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Recipe: {self.menu_item.name}"

    def get_total_cost(self):
        total = Decimal("0")
        for ing in self.ingredients.all():
            if ing.inventory_item.unit_price:
                total += ing.quantity * ing.inventory_item.unit_price
        return total

    def check_availability(self, quantity=1):
        missing = []
        for ing in self.ingredients.all():
            required = ing.quantity * quantity
            available = ing.inventory_item.quantity_in_stock
            if available < required:
                missing.append({
                    "item": ing.inventory_item.name,
                    "required": float(required),
                    "available": float(available),
                    "unit": ing.unit,
                })
        return (len(missing) == 0, missing)


class RecipeIngredient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="used_in")
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=20)
    is_optional = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("recipe", "inventory_item")

    def __str__(self):
        return f"{self.recipe.menu_item.name} uses {self.inventory_item.name}"
