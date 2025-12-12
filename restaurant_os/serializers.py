# ===============================
# serializers.py - FULLY UPDATED
# ===============================

from rest_framework import serializers
from decimal import Decimal
from .models import *


# =========================
# USER & AUTH
# =========================
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone', 'role', 'is_active']


# =========================
# RESTAURANT STRUCTURE
# =========================
class RestaurantSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Restaurant
        fields = '__all__'


class BranchSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    manager_name = serializers.CharField(source='manager.full_name', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id',
            'restaurant',
            'restaurant_name',
            'branch_name',
            'city',
            'address',
            'phone',
            'email',
            'number_of_employees',
            'opening_hours',
            'manager',
            'manager_name',
            'is_active',
            'created_at'
        ]
        read_only_fields = ['is_active', 'created_at']


class CategorySerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = Category
        fields = '__all__'


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    price_with_tax = serializers.SerializerMethodField()
    profit_margin = serializers.SerializerMethodField()

    image_file = serializers.ImageField(required=False, allow_null=True)

    # WRITE INGREDIENTS (additive only)
    ingredients = RecipeIngredientWritableSerializer(
        many=True, write_only=True, required=False
    )

    # KEEP EXISTING LOGIC
    recipe = RecipeSerializer(read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            'id', 'restaurant', 'restaurant_name', 'category', 'category_name',
            'name', 'description', 'cost_price', 'sale_price', 'price_with_tax',
            'profit_margin', 'status', 'image_url', 'image_file',
            'preparation_time', 'updated_at',
            'ingredients', 'recipe'
        ]

    def get_price_with_tax(self, obj):
        tax_rate = Decimal(obj.restaurant.tax_rate or 0) / 100
        return float(obj.sale_price + (obj.sale_price * tax_rate))

    def get_profit_margin(self, obj):
        return float(obj.sale_price - obj.cost_price)

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients", [])
        item = super().create(validated_data)

        # Only add new logic — DO NOT touch existing recipe logic
        if ingredients:
            recipe = Recipe.objects.create(
                menu_item=item,
                name=f"Recipe for {item.name}",
                preparation_time=item.preparation_time
            )
            for ing in ingredients:
                RecipeIngredient.objects.create(recipe=recipe, **ing)

        return item

    def update(self, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)
        item = super().update(instance, validated_data)

        if ingredients is not None:
            recipe, _ = Recipe.objects.get_or_create(menu_item=item)
            recipe.ingredients.all().delete()
            for ing in ingredients:
                RecipeIngredient.objects.create(recipe=recipe, **ing)

        return item

# =========================
# CUSTOMER & POS
# =========================
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
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    cashier_name = serializers.CharField(source='cashier.full_name', read_only=True)

    class Meta:
        model = POSSale
        fields = '__all__'


class CreatePOSSaleSerializer(serializers.Serializer):
    customer_name = serializers.CharField()
    customer_contact = serializers.CharField()
    payment_method = serializers.ChoiceField(choices=POSSale.PAYMENT_METHODS)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    items = serializers.ListField(child=serializers.DictField())


# =========================
# SALES ANALYTICS & DASHBOARD
# =========================
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


# =========================
# SUPPLIERS & INVENTORY
# =========================
class SupplierSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = Supplier
        fields = '__all__'


class InventoryItemSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    needs_reorder = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = '__all__'

    def get_needs_reorder(self, obj):
        return obj.quantity_in_stock <= obj.reorder_level


class InventoryTransactionSerializer(serializers.ModelSerializer):
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = '__all__'



class InventoryOrderItemSerializer(serializers.ModelSerializer):
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)

    class Meta:
        model = InventoryOrderItem
        fields = '__all__'


class InventoryOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    items = InventoryOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryOrder
        fields = '__all__'


# =========================
# RECIPES
# =========================

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
