from rest_framework import serializers
from django.utils import timezone
from .models import Menu, Sales

class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Menu
        fields = '__all__'
        read_only_fields = ['id']


class SalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sales
        fields = '__all__'
        read_only_fields = ['id', 'sale_date', 'total_amount', 'is_weekend', 'price_per_unit']

    def create(self, validated_data):
        item = validated_data['item_id']
        quantity = validated_data['quantity']
        discount = validated_data.get('discount', 0.0)
        price_per_unit = item.sales_price

        total_amount = (price_per_unit * quantity) - discount
        sale_date = timezone.now()
        is_weekend = sale_date.weekday() >= 5

        sale = Sales.objects.create(
            item_id=item,
            quantity=quantity,
            price_per_unit=price_per_unit,
            discount=discount,
            total_amount=total_amount,
            is_weekend=is_weekend
        )
        return sale
