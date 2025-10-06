from rest_framework import serializers
from .models import MenuItem, Sale, DailySale, Inventory, Supplier, InventoryOrder
from django.utils import timezone


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'


class InventorySerializer(serializers.ModelSerializer):
    supplier = SupplierSerializer(read_only=True)
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), source='supplier', write_only=True
    )

    class Meta:
        model = Inventory
        fields = ['id', 'item_name', 'quantity', 'reorder_level', 'unit_price', 'supplier', 'supplier_id']


class InventoryOrderSerializer(serializers.ModelSerializer):
    supplier = SupplierSerializer(read_only=True)

    class Meta:
        model = InventoryOrder
        fields = '__all__'


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = '__all__'


class SaleSerializer(serializers.ModelSerializer):
    menu_item = MenuItemSerializer(read_only=True)
    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.all(), source='menu_item', write_only=True
    )

    class Meta:
        model = Sale
        fields = ['id', 'menu_item', 'menu_item_id', 'quantity', 'total_price', 'timestamp']

    def create(self, validated_data):
        sale = super().create(validated_data)
        menu_item = sale.menu_item

        # Reduce inventory (assuming item_name matches inventory)
        try:
            inventory_item = Inventory.objects.get(item_name=menu_item.name)
            inventory_item.quantity -= sale.quantity
            inventory_item.save()

            # Trigger reorder if low
            if inventory_item.quantity <= inventory_item.reorder_level:
                InventoryOrder.objects.get_or_create(
                    supplier=inventory_item.supplier,
                    item_name=inventory_item.item_name,
                    quantity=inventory_item.reorder_level * 2,  # reorder double the threshold
                )
        except Inventory.DoesNotExist:
            pass

        # Update daily sales
        today = timezone.now().date()
        daily_sale, created = DailySale.objects.get_or_create(date=today)
        daily_sale.total_sales += sale.total_price
        daily_sale.save()

        # Update menu popularity
        menu_item.popularity_score += sale.quantity
        menu_item.save()

        return sale


class DailySaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailySale
        fields = '__all__'
