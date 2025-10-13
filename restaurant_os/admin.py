from django.contrib import admin
from .models import *

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'full_name', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    search_fields = ['email', 'full_name']

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'owner']

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'restaurant', 'manager', 'is_active']
    list_filter = ['is_active', 'city']

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'restaurant', 'category', 'price', 'available']
    list_filter = ['available', 'category']

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact', 'email']
    search_fields = ['name', 'contact']

@admin.register(POSSale)
class POSSaleAdmin(admin.ModelAdmin):
    list_display = ['id', 'branch', 'customer', 'payment_method', 'total', 'created_at']
    list_filter = ['payment_method', 'branch']

@admin.register(BranchDailySales)
class BranchDailySalesAdmin(admin.ModelAdmin):
    list_display = ['branch', 'date', 'revenue', 'transactions']
    list_filter = ['branch', 'date']

@admin.register(BranchForecast)
class BranchForecastAdmin(admin.ModelAdmin):
    list_display = ['branch', 'forecast_date', 'predicted_growth', 'confidence_score']

@admin.register(BranchComparison)
class BranchComparisonAdmin(admin.ModelAdmin):
    list_display = ['date', 'branch_1', 'branch_2', 'metric', 'severity']

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity_in_stock', 'unit', 'reorder_level']

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone']
