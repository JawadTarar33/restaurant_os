# ===============================
# serializers.py - COMPLETE FILE
# ===============================

from rest_framework import serializers
from .models import *


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone', 'role', 'is_active']


class RestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = '__all__'


class BranchSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.full_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = Branch
        fields = '__all__'


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = '__all__'


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    price_with_tax = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = '__all__'

    def get_price_with_tax(self, obj):
        tax = obj.price * Decimal('0.17')
        return float(obj.price + tax)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class POSSaleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='menu_item.name', read_only=True)

    class Meta:
        model = POSSaleItem
        fields = '__all__'


class POSSaleSerializer(serializers.ModelSerializer):
    items = POSSaleItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    sync_status = serializers.SerializerMethodField()

    class Meta:
        model = POSSale
        fields = '__all__'

    def get_sync_status(self, obj):
        if obj.is_offline_sale and obj.synced_at:
            return 'synced'
        elif obj.is_offline_sale and not obj.synced_at:
            return 'pending'
        return 'online'


class SyncLogSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = SyncLog
        fields = '__all__'


class CreatePOSSaleSerializer(serializers.Serializer):
    customer_name = serializers.CharField()
    customer_contact = serializers.CharField()
    payment_method = serializers.ChoiceField(choices=POSSale.PAYMENT_METHODS)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    items = serializers.ListField(child=serializers.DictField())


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'


class InventoryItemSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    needs_reorder = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = '__all__'

    def get_needs_reorder(self, obj):
        return obj.quantity_in_stock <= obj.reorder_level


class InventoryOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryOrder
        fields = '__all__'


class DailySalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailySales
        fields = '__all__'


class BranchDailySalesSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = BranchDailySales
        fields = '__all__'


class BranchForecastSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    trend = serializers.SerializerMethodField()

    class Meta:
        model = BranchForecast
        fields = '__all__'

    def get_trend(self, obj):
        return 'up' if obj.predicted_growth > 0 else 'down'


class BranchComparisonSerializer(serializers.ModelSerializer):
    branch_1_name = serializers.CharField(source='branch_1.name', read_only=True)
    branch_2_name = serializers.CharField(source='branch_2.name', read_only=True)

    class Meta:
        model = BranchComparison
        fields = '__all__'


class RecipeIngredientSerializer(serializers.ModelSerializer):
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)
    inventory_item_stock = serializers.DecimalField(
        source='inventory_item.quantity_in_stock', 
        max_digits=10, 
        decimal_places=3,
        read_only=True
    )
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = RecipeIngredient
        fields = '__all__'

    def get_total_cost(self, obj):
        if obj.inventory_item.unit_price:
            return float(obj.quantity * obj.inventory_item.unit_price)
        return 0


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True, read_only=True)
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    total_cost = serializers.SerializerMethodField()
    availability_status = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = '__all__'

    def get_total_cost(self, obj):
        return float(obj.get_total_cost())

    def get_availability_status(self, obj):
        is_available, missing = obj.check_availability()
        return {
            'available': is_available,
            'missing_items': missing
        }


class InventoryTransactionSerializer(serializers.ModelSerializer):
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = '__all__'
