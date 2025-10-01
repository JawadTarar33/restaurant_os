from rest_framework import serializers
from django.utils import timezone
from .models import Menu, Sales, SalesItem


class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Menu
        fields = '__all__'
        read_only_fields = ['id']


class SalesItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    
    class Meta:
        model = SalesItem
        fields = ['id', 'item', 'item_name', 'quantity', 'price_per_unit', 'discount', 'subtotal']
        read_only_fields = ['id', 'price_per_unit', 'subtotal']
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value


class SalesSerializer(serializers.ModelSerializer):
    sale_items = SalesItemSerializer(many=True)
    
    class Meta:
        model = Sales
        fields = ['id', 'sale_date', 'is_weekend', 'total_amount', 'discount', 'final_amount', 'sale_items']
        read_only_fields = ['id', 'sale_date', 'is_weekend', 'total_amount', 'final_amount']
    
    def create(self, validated_data):
        items_data = validated_data.pop('sale_items')
        
        # Create the sale
        sale_date = timezone.now()
        is_weekend = sale_date.weekday() >= 5
        
        sale = Sales.objects.create(
            is_weekend=is_weekend,
            discount=validated_data.get('discount', 0.0)
        )
        
        # Create sale items
        for item_data in items_data:
            menu_item = item_data['item']
            quantity = item_data['quantity']
            item_discount = item_data.get('discount', 0.0)
            
            SalesItem.objects.create(
                sale=sale,
                item=menu_item,
                quantity=quantity,
                price_per_unit=menu_item.sales_price,
                discount=item_discount
            )
        
        # Calculate totals
        sale.calculate_totals()
        
        return sale
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('sale_items', None)
        
        # Update sale-level fields
        instance.discount = validated_data.get('discount', instance.discount)
        
        if items_data is not None:
            # Clear existing items and create new ones
            instance.sale_items.all().delete()
            
            for item_data in items_data:
                menu_item = item_data['item']
                quantity = item_data['quantity']
                item_discount = item_data.get('discount', 0.0)
                
                SalesItem.objects.create(
                    sale=instance,
                    item=menu_item,
                    quantity=quantity,
                    price_per_unit=menu_item.sales_price,
                    discount=item_discount
                )
        
        # Recalculate totals
        instance.calculate_totals()
        
        return instance